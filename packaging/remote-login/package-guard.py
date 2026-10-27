#!/usr/bin/python3 -I
"""Fixed root entry point for native-package remote-login preparation/recovery."""
import json
import os
from pathlib import Path
import stat
import sys


def _read(path,root,owner_uid):
    try:
        # Inspect existing ancestors even if the final file is absent.
        for parent in (path.parent,*path.parent.parents):
            if not parent.is_relative_to(root):break
            try:info=parent.lstat()
            except FileNotFoundError:continue
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=owner_uid or info.st_mode & 0o022:
                raise ValueError('Unsafe remote-login state directory; repair before package changes.')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    except FileNotFoundError:return None
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=owner_uid or info.st_mode & 0o022 or info.st_nlink!=1 or info.st_size>65536:
            raise ValueError('Unsafe remote-login state; repair before package changes.')
        raw=source.read(65537)
    if len(raw)>65536:raise ValueError('Remote-login state exceeds its size bound.')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('Invalid remote-login state.')
    return value


def validate_state(root=Path('/'), *, owner_uid=0):
    root = Path(root).absolute()
    settings = _read(root/'etc/monitorize/remote-login.json', root, owner_uid)
    lease = _read(root/'run/monitorize-vkms/primary.json', root, owner_uid)
    if settings is not None and type(settings.get('enabled')) is not bool:
        raise ValueError('Invalid remote-login enablement state.')
    return settings, lease


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Pause remote login safely for native package transactions; pairing is retained.')
    parser.add_argument('--prepare', choices=('upgrade', 'remove'), default='upgrade')
    parser.add_argument('--allow-disconnect', action='store_true', help='Explicitly allow disconnecting remote-login clients before retrying the package command')
    parser.add_argument('--resume', action='store_true', help='Restore remote login after an upgrade or an interrupted package transaction')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise PermissionError('Package lifecycle requires root.')
        # Validate state with the standalone reader before importing service code.
        validate_state()
        sys.path.insert(0, '/usr/lib/monitorize-remote-login')
        from monitorize.remote_login.daemon import require_installed
        from monitorize.remote_login import package_lifecycle
        require_installed(package_lifecycle.__file__)
        from monitorize.remote_login.live_setup import setup_lock
        with setup_lock():
            lifecycle = package_lifecycle.PackageLifecycle(package_lifecycle.InstalledBackend())
            if args.resume:
                lifecycle.resume()
            else:
                lifecycle.prepare(args.prepare, allow_disconnect=args.allow_disconnect)
        return 0
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
