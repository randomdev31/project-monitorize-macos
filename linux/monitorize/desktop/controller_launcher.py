"""Wait for the user manager's graphical connection before importing Qt."""
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time


DISPLAY_ENVIRONMENT = ('WAYLAND_DISPLAY', 'DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR',
                       'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP', 'DBUS_SESSION_BUS_ADDRESS')


def manager_environment():
    result = subprocess.run(['/usr/bin/systemctl', '--user', 'show-environment'],
                            capture_output=True, text=True, timeout=3, check=True)
    return {key: value for line in result.stdout.splitlines() if '=' in line
            for key, value in [line.split('=', 1)] if key in DISPLAY_ENVIRONMENT}


def _socket_ready(path, *, allow_root=False):
    try:
        info = path.stat()
        owners=(os.getuid(),0) if allow_root else (os.getuid(),)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid not in owners:return False
        with socket.socket(socket.AF_UNIX) as peer:
            peer.settimeout(.2);peer.connect(str(path))
        return True
    except OSError:return False


def wait_for_graphical_session(environment=None, *, timeout=60,
                               manager_environment=manager_environment,
                               clock=time.monotonic, sleep=time.sleep):
    environment = dict(os.environ if environment is None else environment)
    deadline = clock() + timeout
    while True:
        try:environment.update(manager_environment())
        except (OSError, subprocess.SubprocessError):pass
        wayland = environment.get('WAYLAND_DISPLAY', '')
        runtime = environment.get('XDG_RUNTIME_DIR', '')
        if wayland and runtime:
            path = Path(wayland) if wayland.startswith('/') else Path(runtime)/wayland
            if _socket_ready(path):
                environment['QT_QPA_PLATFORM']='wayland'
                return environment
        display = re.fullmatch(r':(\d+)(?:\.\d+)?', environment.get('DISPLAY',''))
        if environment.get('XDG_SESSION_TYPE') != 'wayland' and display:
            if _socket_ready(Path('/tmp/.X11-unix')/('X'+display[1]),allow_root=True):
                environment['QT_QPA_PLATFORM']='xcb'
                return environment
        if clock() >= deadline:
            raise RuntimeError('Monitorize is waiting for a usable graphical session. Check the user manager display environment.')
        sleep(min(1, deadline-clock()))


def main():
    try:environment=wait_for_graphical_session()
    except RuntimeError as error:
        print(str(error), file=sys.stderr, flush=True)
        return 1
    os.execvpe(sys.executable, [sys.executable, '-m', 'monitorize', '--start-in-tray'], environment)


if __name__ == '__main__':
    raise SystemExit(main())
