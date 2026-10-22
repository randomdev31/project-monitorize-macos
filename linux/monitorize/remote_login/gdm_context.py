"""Authenticate GDM's compositor; standalone child queries its own session bus.

The root caller validates socket/process/session evidence. The demoted child
only reports the DisplayConfig owner PID, never runs configuration commands.
"""
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys


def bus_owner():
    import dbus
    bus=dbus.bus.BusConnection(os.environ['DBUS_SESSION_BUS_ADDRESS'])
    try:
        proxy=bus.get_object('org.freedesktop.DBus','/org/freedesktop/DBus',introspect=False)
        interface=dbus.Interface(proxy,'org.freedesktop.DBus')
        name=interface.GetNameOwner('org.gnome.Mutter.DisplayConfig',timeout=2)
        return int(interface.GetConnectionUnixProcessID(name,timeout=2))
    finally:bus.close()


def trusted_shell(executable):
    from .daemon import require_installed
    resolved=executable.resolve(strict=True)
    if resolved.name!='gnome-shell':
        raise PermissionError('GDM Wayland server is not GNOME Shell.')
    require_installed(resolved)


def verify(context,session,environment,helper):
    uid=context['greeter_uid']
    if session!=context['session'] or environment.get('XDG_SESSION_TYPE')!='wayland':
        raise PermissionError('GDM greeter Wayland session changed.')
    environment=dict(environment)
    if not environment.get('WAYLAND_DISPLAY'):
        environment.update(helper._session_connection_environment(uid,session))
    runtime=Path('/run/user')/str(uid)
    name=environment.get('WAYLAND_DISPLAY','')
    if not name:raise RuntimeError('GDM greeter Wayland socket is unavailable.')
    socket=Path(name)
    if not socket.is_absolute():socket=runtime/socket
    pid=helper._validate_session_socket(socket,uid,session)
    executable=Path('/proc')/str(pid)/'exe'
    trusted_shell(executable)
    args=(executable.parent/'cmdline').read_bytes().split(b'\0')
    if b'--mode=gdm' not in args and not any(a==b'--mode' and args[i+1:i+2]==[b'gdm'] for i,a in enumerate(args)):
        raise PermissionError('GNOME Shell is not running in GDM greeter mode.')
    bus=runtime/'bus'
    info=bus.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=uid:
        raise PermissionError('GDM session bus ownership is unsafe.')
    account=pwd.getpwuid(uid)
    # The Wayland socket validator has already verified the runtime directory.
    # Ignore any bus address inherited from an untrusted process environment.
    environment.update(DBUS_SESSION_BUS_ADDRESS='unix:path='+str(bus),
        XDG_RUNTIME_DIR=str(runtime),XDG_CURRENT_DESKTOP='GNOME',
        HOME=account.pw_dir,USER=account.pw_name,LOGNAME=account.pw_name,
        PATH='/usr/bin:/bin')
    child={key:value for key,value in environment.items() if key in (
        'DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','HOME','USER','LOGNAME','PATH')}
    result=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),'bus-owner'],
        env=child,user=uid,group=account.pw_gid,extra_groups=os.getgrouplist(account.pw_name,account.pw_gid),
        capture_output=True,text=True,timeout=4,check=True)
    if len(result.stdout)>128 or json.loads(result.stdout)!=pid:
        raise PermissionError('Mutter DisplayConfig does not belong to the verified GDM compositor.')
    # Revalidate after the demoted query to reject compositor replacement.
    if helper._validate_session_socket(socket,uid,session)!=pid:
        raise PermissionError('GDM compositor changed during verification.')
    return environment


if __name__=='__main__':
    if sys.argv[1:]!=['bus-owner']:raise SystemExit(2)
    print(json.dumps(bus_owner()))
