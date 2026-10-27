"""Authenticate GDM's compositor; standalone child queries its own session bus.

The root caller validates socket/process/session evidence. The demoted child
only reports the DisplayConfig owner PID, never runs configuration commands.
"""
import json
import os
from pathlib import Path
import pwd
import stat
import socket as unix_socket
import struct
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


def socket_owner(path,uid,runtime):
    """Verify a direct, private-runtime socket and return its kernel peer PID.

    GDM's systemd user service is not necessarily inside session-N.scope. Its
    identity is checked against Mutter's bus owner by verify(), not inferred
    from a process's inherited session environment.
    """
    if not path.is_absolute() or path.parent!=runtime:
        raise PermissionError('GDM Wayland socket must be directly inside its runtime directory.')
    directory=runtime.lstat();info=path.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid!=uid or directory.st_mode & 0o022
            or not stat.S_ISSOCK(info.st_mode) or info.st_uid!=uid):
        raise PermissionError('GDM Wayland runtime/socket ownership is unsafe.')
    with unix_socket.socket(unix_socket.AF_UNIX,unix_socket.SOCK_STREAM) as connection:
        connection.settimeout(1);connection.connect(str(path))
        pid,peer_uid,_=struct.unpack('3i',connection.getsockopt(unix_socket.SOL_SOCKET,unix_socket.SO_PEERCRED,12))
    if peer_uid!=uid or pid<=0:raise PermissionError('GDM Wayland peer belongs to another account.')
    return pid


def verify(context,session,environment,helper):
    uid=context['greeter_uid']
    if session!=context['session'] or environment.get('XDG_SESSION_TYPE')!='wayland':
        raise PermissionError('GDM greeter Wayland session changed.')
    runtime=Path('/run/user')/str(uid)
    directory=runtime.lstat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid!=uid or directory.st_mode & 0o022:
        raise PermissionError('GDM runtime directory ownership is unsafe.')
    bus=runtime/'bus'
    info=bus.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=uid:
        raise PermissionError('GDM session bus ownership is unsafe.')
    account=pwd.getpwuid(uid)
    # Derive connection context exclusively from the authenticated greeter UID.
    # GDM's shell may have no session ID or WAYLAND_DISPLAY in /proc/environ.
    environment=dict(XDG_SESSION_TYPE='wayland',DBUS_SESSION_BUS_ADDRESS='unix:path='+str(bus),
        XDG_RUNTIME_DIR=str(runtime),XDG_CURRENT_DESKTOP='GNOME',
        HOME=account.pw_dir,USER=account.pw_name,LOGNAME=account.pw_name,
        PATH='/usr/bin:/bin')
    child={key:value for key,value in environment.items() if key in (
        'DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','HOME','USER','LOGNAME','PATH')}
    def owner():
        result=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),'bus-owner'],
            env=child,user=uid,group=account.pw_gid,extra_groups=os.getgrouplist(account.pw_name,account.pw_gid),
            capture_output=True,text=True,timeout=4,check=True)
        if len(result.stdout)>128:raise PermissionError('Invalid GDM DisplayConfig owner.')
        pid=json.loads(result.stdout)
        if type(pid) is not int or pid<=0:raise PermissionError('Invalid GDM DisplayConfig owner.')
        return pid
    pid=owner()
    process=Path('/proc')/str(pid)
    if process.stat().st_uid!=uid:raise PermissionError('GDM DisplayConfig owner belongs to another account.')
    trusted_shell(process/'exe')
    args=(process/'cmdline').read_bytes().split(b'\0')
    if b'--mode=gdm' not in args and not any(a==b'--mode' and args[i+1:i+2]==[b'gdm'] for i,a in enumerate(args)):
        raise PermissionError('GNOME Shell is not running in GDM greeter mode.')
    candidates=list(runtime.glob('wayland-*'))
    if len(candidates)>64:raise PermissionError('Too many GDM Wayland socket candidates.')
    valid=[]
    for candidate in candidates:
        try:
            if socket_owner(candidate,uid,runtime)==pid:valid.append(candidate)
        except (OSError,PermissionError):continue
    if len(valid)!=1:
        raise PermissionError('GDM DisplayConfig owner must have exactly one verified Wayland socket; found '+str(len(valid))+'.')
    socket=valid[0]
    if owner()!=pid:
        raise PermissionError('Mutter DisplayConfig does not belong to the verified GDM compositor.')
    # Revalidate after the demoted query to reject compositor replacement.
    if socket_owner(socket,uid,runtime)!=pid:
        raise PermissionError('GDM compositor changed during verification.')
    environment['WAYLAND_DISPLAY']=socket.name
    return environment


if __name__=='__main__':
    if sys.argv[1:]!=['bus-owner']:raise SystemExit(2)
    print(json.dumps(bus_owner()))
