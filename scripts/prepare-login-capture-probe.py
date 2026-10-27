#!/usr/bin/env python3
"""Stage a restricted boot-capture experiment as the current user; never install it."""
import argparse
import grp
import json
import os
from pathlib import Path
import shutil
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'linux'))
from monitorize.platform.login_capture_probe import build_config, validate_identity


def read_private(path, limit=1024*1024):
    fd=os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError('Expected a regular profile file owned by your user: '+str(path))
        with os.fdopen(fd, 'rb', closefd=False) as source:
            data=source.read(limit+1)
        if len(data)>limit:
            raise ValueError('Profile file exceeds experiment size limit.')
        return data
    finally:
        os.close(fd)


def prepare(args):
    uid=os.getuid()
    if uid == 0:
        raise ValueError('Run preparation without sudo; install the generated files separately.')
    for process in Path('/proc').glob('[0-9]*'):
        try:
            if (process/'comm').read_text().strip() == 'sunshine':
                raise ValueError('Stop all Sunshine/Monitorize hosts before taking the identity snapshot.')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    repository=Path(__file__).resolve().parents[1]
    binary=Path(args.sunshine).resolve(strict=True)
    if not binary.is_file() or binary.read_bytes()[:4] != b'\x7fELF':
        raise ValueError('Select the native built Sunshine ELF binary.')
    assets=Path(args.assets).resolve(strict=True)
    if not (assets/'web').is_dir():
        raise ValueError('Choose the Sunshine build assets directory (containing web/).')
    profile=Path(args.profile).resolve(strict=True)
    raw=validate_identity(read_private(profile/'sunshine_state.json'))
    certificate=read_private(profile/'credentials/cacert.pem')
    key=read_private(profile/'credentials/cakey.pem')
    if b'BEGIN CERTIFICATE' not in certificate or b'PRIVATE KEY' not in key:
        raise ValueError('Existing Sunshine certificate/key are missing or invalid.')
    source_config={}
    for line in read_private(profile/'sunshine.conf').decode().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            name,value=line.split('=',1)
            source_config[name.strip()]=value.strip()
    hostname=source_config.get('sunshine_name','Monitorize')
    encoder=args.encoder or source_config.get('encoder') or 'vaapi'
    adapter=source_config.get('adapter_name','')
    destination=Path(args.output).absolute()
    destination.mkdir(mode=0o700)  # Refuse overwriting previous snapshots or symlinks.
    try:
        (destination/'identity').mkdir(mode=0o700)
        for name,data in [('sunshine_state.json',raw),('cacert.pem',certificate),('cakey.pem',key)]:
            path=destination/'identity'/name
            path.write_bytes(data)
            path.chmod(0o600)
        state=Path('/var/lib/monitorize-login-capture')/str(uid)
        (destination/'sunshine.conf').write_text(build_config(state,hostname,encoder,adapter))
        shutil.copyfile(repository/'scripts/remote-login-probe/capture-apps.json',destination/'apps.json')
        (destination/'settings.json').write_text(json.dumps({'uid':uid,'schema_version':1}))
        shutil.copyfile(repository/'linux/monitorize/platform/login_capture_probe.py',destination/'runner.py')
        shutil.copyfile(binary,destination/'sunshine')
        shutil.copytree(assets,destination/'assets',symlinks=False)
        # Numeric supplementary groups avoid assumptions about distro group names.
        groups=set()
        for device in [Path('/dev/uinput'),*Path('/dev/dri').glob('card*'),*Path('/dev/dri').glob('renderD*')]:
            if device.exists():
                groups.add(device.stat().st_gid)
        if not groups:
            raise ValueError('No input/DRM device groups were found.')
        unit=f'''[Unit]
Description=Experimental Monitorize KMS login-screen capture
Requires=monitorize-remote-login-probe.service
After=monitorize-remote-login-probe.service display-manager.service systemd-logind.service network.target

[Service]
Type=simple
User={uid}
Group={os.getgid()}
SupplementaryGroups={' '.join(str(g) for g in sorted(groups))}
ExecStart=/usr/local/libexec/monitorize-login-capture/runner
WorkingDirectory={state}
Environment=PYTHONDONTWRITEBYTECODE=1
CapabilityBoundingSet=CAP_SYS_ADMIN
# Capability belongs only to the root-installed Sunshine executable, not Python.
# NoNewPrivileges cannot be enabled when executing that file-capability binary.
NoNewPrivileges=no
UMask=0077
Restart=no
TimeoutStopSec=12
KillMode=control-group

[Install]
WantedBy=graphical.target
'''
        (destination/'monitorize-login-capture.service').write_text(unit)
        installer=f'''#!/bin/sh
set -eu
[ "$(id -u)" -eq 0 ] || {{ echo 'Run this installer with sudo.'; exit 1; }}
cd -- "$(dirname -- "$0")"
for path in /etc/monitorize-login-capture.json /etc/systemd/system/monitorize-login-capture.service /usr/local/libexec/monitorize-login-capture /usr/local/share/monitorize-login-capture /var/lib/monitorize-login-capture/{uid}; do
    [ ! -e "$path" ] && [ ! -L "$path" ] || {{ echo "Refusing existing installation: $path"; exit 1; }}
done
command -v setcap >/dev/null
systemctl is-enabled monitorize-remote-login-probe.service >/dev/null
# Refuse installation while a Sunshine host could mutate this pairing identity.
if pgrep -x sunshine >/dev/null; then echo 'Stop Sunshine before installation.'; exit 1; fi
install -d -o root -g root -m 0755 /usr/local/libexec/monitorize-login-capture /usr/local/share/monitorize-login-capture /var/lib/monitorize-login-capture/{uid}
install -o root -g root -m 0755 sunshine /usr/local/libexec/monitorize-login-capture/sunshine
install -o root -g root -m 0755 runner.py /usr/local/libexec/monitorize-login-capture/runner
cp -R -- assets /usr/local/share/monitorize-login-capture/
chown -R root:root /usr/local/share/monitorize-login-capture
chmod -R go-w /usr/local/share/monitorize-login-capture
install -d -o {uid} -g {os.getgid()} -m 0700 {state}/identity {state}/runtime {state}/logs
install -o {uid} -g {os.getgid()} -m 0600 identity/* {state}/identity/
install -o root -g root -m 0644 sunshine.conf apps.json {state}/
install -o root -g root -m 0644 settings.json /etc/monitorize-login-capture.json
install -o root -g root -m 0644 monitorize-login-capture.service /etc/systemd/system/monitorize-login-capture.service
setcap cap_sys_admin+p /usr/local/libexec/monitorize-login-capture/sunshine
systemctl daemon-reload
systemctl enable monitorize-login-capture.service
echo 'Installed for next boot only. No services started. Keep Monitorize autostart/listening off for the test.'
'''
        (destination/'install.sh').write_text(installer)
        (destination/'install.sh').chmod(0o700)
    except Exception:
        shutil.rmtree(destination)
        raise
    print('Prepared private experiment directory:',destination)
    print('Existing host UUID, certificate and paired clients copied without printing secrets.')
    print('Encoder:',encoder,'; original profile untouched; no services installed or started.')
    print('Review install.sh, then install with sudo sh '+str(destination/'install.sh'))
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sunshine',required=True)
    parser.add_argument('--assets',required=True)
    parser.add_argument('--profile',default=str(Path.home()/'.config/monitorize/sunshine-1'))
    parser.add_argument('--output',default='/tmp/monitorize-login-capture-stage-'+str(os.getuid()))
    parser.add_argument('--encoder',choices=['vaapi','nvenc','software'])
    args=parser.parse_args()
    try:
        prepare(args)
    except (OSError,ValueError) as exc:
        parser.exit(1,'Preparation failed: '+str(exc)+'\n')


if __name__=='__main__':
    main()
