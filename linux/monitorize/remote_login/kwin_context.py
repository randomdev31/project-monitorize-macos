"""Verify Plasma Login Manager's KWin independently of desktop environment labels.

The caller must first authenticate an isolated, active local greeter account.
KWin's per-user service may live outside the greeter's logind session scope.
"""
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

PLASMA_GREETER_PROTOCOL = 1


def bus_owner():
    import dbus
    bus=dbus.bus.BusConnection(os.environ['DBUS_SESSION_BUS_ADDRESS'])
    try:
        interface=dbus.Interface(bus.get_object('org.freedesktop.DBus',
            '/org/freedesktop/DBus',introspect=False),'org.freedesktop.DBus')
        name=interface.GetNameOwner('org.kde.KWin',timeout=1)
        pid=int(interface.GetConnectionUnixProcessID(name,timeout=1))
        if interface.GetNameOwner('org.kde.KWin',timeout=1)!=name:
            raise PermissionError('KWin bus owner changed during verification.')
        return pid
    finally:bus.close()


def trusted_kwin(executable):
    from .daemon import require_installed
    resolved=executable.resolve(strict=True)
    if resolved.name!='kwin_wayland':raise PermissionError('Plasma greeter is not running KWin Wayland.')
    require_installed(resolved)


def verify(context,session,environment,helper):
    if session!=context['session'] or environment.get('XDG_SESSION_TYPE')!='wayland':
        raise PermissionError('Plasma greeter Wayland session changed.')
    uid=context['greeter_uid'];runtime=Path('/run/user')/str(uid)
    directory=runtime.lstat();bus=runtime/'bus';info=bus.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid!=uid or directory.st_mode & 0o022
            or not stat.S_ISSOCK(info.st_mode) or info.st_uid!=uid):
        raise PermissionError('Plasma greeter runtime/bus ownership is unsafe.')
    account=pwd.getpwuid(uid)
    verified=dict(XDG_SESSION_TYPE='wayland',XDG_SESSION_ID=session,XDG_RUNTIME_DIR=str(runtime),
        DBUS_SESSION_BUS_ADDRESS='unix:path='+str(bus),XDG_CURRENT_DESKTOP='KDE',
        HOME=account.pw_dir,USER=account.pw_name,LOGNAME=account.pw_name,PATH='/usr/bin:/bin')
    child={key:value for key,value in verified.items() if key in (
        'DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','HOME','USER','LOGNAME','PATH')}
    def owner():
        result=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),'bus-owner'],
            env=child,user=uid,group=account.pw_gid,extra_groups=os.getgrouplist(account.pw_name,account.pw_gid),
            capture_output=True,text=True,timeout=4,check=True)
        if len(result.stdout)>128:raise PermissionError('Invalid Plasma KWin owner response.')
        pid=json.loads(result.stdout)
        if type(pid) is not int or pid<=0:raise PermissionError('Invalid Plasma KWin owner PID.')
        return pid
    pid=owner();process=Path('/proc')/str(pid)
    if process.stat().st_uid!=uid:raise PermissionError('KWin owner belongs to another account.')
    trusted_kwin(process/'exe')
    from .gdm_context import socket_owner
    candidates=list(runtime.glob('wayland-*'))
    if len(candidates)>64:raise PermissionError('Too many Plasma Wayland socket candidates.')
    valid=[]
    for candidate in candidates:
        try:
            if socket_owner(candidate,uid,runtime)==pid:valid.append(candidate)
        except (OSError,PermissionError):continue
    if len(valid)!=1:raise PermissionError('Plasma KWin must own exactly one verified Wayland socket.')
    try:unchanged=owner()==pid and socket_owner(valid[0],uid,runtime)==pid
    except (OSError,PermissionError):unchanged=False
    if not unchanged:raise PermissionError('Plasma KWin changed during verification.')
    verified['WAYLAND_DISPLAY']=valid[0].name
    return verified


if __name__=='__main__':
    if sys.argv[1:]!=['bus-owner']:raise SystemExit(2)
    print(json.dumps(bus_owner()))
