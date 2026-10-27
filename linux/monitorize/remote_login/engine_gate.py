"""Authenticate engine-unit requests independently of graphical GUI senders."""
import hmac
from pathlib import Path


class EngineGate:
    def __init__(self,uid,bus,descriptor,owner_check,identity_free,*,session_check,cgroup_root=Path('/sys/fs/cgroup'),phase='desktop'):
        if phase not in ('desktop','boot'):raise ValueError('Invalid engine phase.')
        self.phase=phase
        self.uid=uid;self.bus=bus;self.descriptor=descriptor;self.owner_check=owner_check
        self.identity_free=identity_free;self.session_check=session_check;self.cgroup_root=Path(cgroup_root)
    def check(self,sender,generation,*,idle=False):
        if not isinstance(sender,str) or not sender.startswith(':') or not isinstance(generation,str):
            raise PermissionError('Invalid engine request.')
        uid=int(self.bus.call('/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixUser',sender))
        pid=int(self.bus.call('/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixProcessID',sender))
        unit=self.bus.call('/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager','GetUnit',
                           f'monitorize-remote-login-{self.phase}@{self.uid}.service')
        main=int(self.bus.properties(unit,'org.freedesktop.systemd1.Service').get('MainPID',0))
        descriptor=self.descriptor()
        if (uid!=self.uid or pid<=0 or pid!=main or descriptor.get('uid')!=uid or
            not hmac.compare_digest(generation,descriptor.get('generation','')) or
            not self.owner_check(descriptor['session'],generation) or
            not self.session_check(uid,descriptor['session'])):
            raise PermissionError('Engine no longer owns the selected desktop.')
        if idle:
            if not self.identity_free():raise RuntimeError('Capture still owns the display; removal deferred.')
            group=str(self.bus.properties(unit,'org.freedesktop.systemd1.Service').get('ControlGroup',''))
            if not group.startswith('/') or '..' in group.split('/'):
                raise RuntimeError('Cannot verify capture cgroup exit.')
            directory=self.cgroup_root/group.lstrip('/')
            processes=set()
            for path in (directory/'cgroup.procs',*directory.rglob('cgroup.procs')):
                processes.update(int(value) for value in path.read_text().split())
            if processes!={pid}:raise RuntimeError('Capture processes remain; removal deferred.')
        return descriptor
