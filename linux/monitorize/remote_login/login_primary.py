"""Read-only capture selection for GDM's existing primary login-screen output."""
import json
import math
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys


def validate_target(target):
    if not isinstance(target,dict):raise ValueError('GDM primary display response is invalid.')
    name=target.get('output_name');width=target.get('width');height=target.get('height');rate=target.get('fps')
    if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',name)
            or type(width) is not int or not 0<width<=16384
            or type(height) is not int or not 0<height<=16384
            or type(rate) not in (int,float) or not math.isfinite(rate) or not 0<rate<=1000
            or target.get('capture')!='kms'):
        raise ValueError('GDM primary display has an invalid connector or mode.')
    return dict(output_name=name,capture='kms',width=width,height=height,fps=rate)


def select_primary(state):
    try:
        physical,logical=state[1:3]
        if len(physical)>64 or len(logical)>64:raise ValueError()
        primary=[row for row in logical if row[4]]
        if len(primary)!=1 or not primary[0][5]:raise ValueError()
        # Mirrored outputs share the login form. Capture the first physical
        # member of that primary logical monitor, never an unrelated secondary.
        name=str(primary[0][5][0][0])
        matches=[row for row in physical if str(row[0][0])==name]
        if len(matches)!=1:raise ValueError()
        modes=[mode for mode in matches[0][1] if mode[6].get('is-current')]
        if len(modes)!=1:raise ValueError()
        mode=modes[0]
        return validate_target(dict(output_name=name,capture='kms',width=int(mode[1]),height=int(mode[2]),fps=float(mode[3])))
    except (IndexError,KeyError,TypeError,AttributeError,ValueError,OverflowError):
        raise ValueError('GDM has no unique enabled primary display. Connect or enable a primary display before streaming the login screen.') from None


def query():
    """Demoted child: read one immutable bus owner's display state."""
    import dbus
    bus=dbus.bus.BusConnection(os.environ['DBUS_SESSION_BUS_ADDRESS'])
    try:
        daemon=dbus.Interface(bus.get_object('org.freedesktop.DBus','/org/freedesktop/DBus',introspect=False),'org.freedesktop.DBus')
        name=daemon.GetNameOwner('org.gnome.Mutter.DisplayConfig',timeout=2)
        pid=int(daemon.GetConnectionUnixProcessID(name,timeout=2))
        interface=dbus.Interface(bus.get_object(name,'/org/gnome/Mutter/DisplayConfig',introspect=False),'org.gnome.Mutter.DisplayConfig')
        target=select_primary(interface.GetCurrentState(timeout=2))
        if daemon.GetNameOwner('org.gnome.Mutter.DisplayConfig',timeout=2)!=name:
            raise PermissionError('GDM compositor changed while selecting the primary display.')
        return dict(pid=pid,target=target)
    finally:bus.close()


def verify_drm(target,*,root=Path('/sys/class/drm')):
    target=validate_target(target)
    candidates=[]
    for path in root.glob('card*-*'):
        match=re.fullmatch(r'card[0-9]+-([A-Za-z][A-Za-z0-9_-]{0,63})',path.name)
        if not match:continue
        canonical=match[1]
        # Mutter and libdrm use different names for HDMI type A. Keep type B
        # distinct, and always return the libdrm name to Sunshine's KMS mapper.
        mutter='HDMI-'+canonical.removeprefix('HDMI-A-') if canonical.startswith('HDMI-A-') else canonical
        if mutter==target['output_name']:candidates.append(path)
    enabled=[path for path in candidates if (path/'status').read_text().strip()=='connected'
             and (path/'enabled').read_text().strip()=='enabled']
    if len(enabled)!=1:
        raise PermissionError('GDM primary display does not resolve to one enabled DRM connector.')
    return enabled[0]


def operation(settings,context,operation,helper,check):
    if settings.manager!='gdm.service' or operation not in ('prepare','idle'):
        raise ValueError('Primary login-screen capture requires GDM and a prepare or idle request.')
    check()
    if operation=='idle':
        # The physical display belongs to GDM. Never disconnect or reconfigure it.
        return {}
    from .gdm_context import verify,socket_owner
    session=context['session'];uid=context['greeter_uid']
    environment=verify(context,session,{'XDG_SESSION_TYPE':'wayland'},helper)
    runtime=Path(environment['XDG_RUNTIME_DIR']);socket=runtime/environment['WAYLAND_DISPLAY']
    expected_pid=socket_owner(socket,uid,runtime)
    account=pwd.getpwuid(uid)
    def read():
        result=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),'query'],
            env=environment,user=uid,group=account.pw_gid,extra_groups=os.getgrouplist(account.pw_name,account.pw_gid),
            capture_output=True,text=True,timeout=8,check=False)
        if result.returncode:
            raise RuntimeError('GDM primary display could not be read. Ensure the login screen has an enabled primary display.')
        if len(result.stdout)>4096:raise ValueError('GDM primary display response is too large.')
        value=json.loads(result.stdout)
        if not isinstance(value,dict) or type(value.get('pid')) is not int or value['pid']!=expected_pid:
            raise PermissionError('Primary display state came from a different GDM compositor.')
        return validate_target(value.get('target'))
    target=read()
    connector=verify_drm(target)
    check()
    verify(context,session,environment,helper)
    if socket_owner(socket,uid,runtime)!=expected_pid:
        raise PermissionError('GDM compositor changed during primary display selection.')
    if read()!=target:
        raise PermissionError('GDM primary display changed during capture selection; retry the connection.')
    check()
    if verify_drm(target)!=connector:
        raise PermissionError('Primary DRM connector changed during capture selection.')
    return validate_target(dict(target,output_name=connector.name.split('-',1)[1]))


if __name__=='__main__':
    if sys.argv[1:]!=['query']:raise SystemExit(2)
    if os.geteuid()==0:raise SystemExit('Primary display query must run as the greeter.')
    print(json.dumps(query()))
