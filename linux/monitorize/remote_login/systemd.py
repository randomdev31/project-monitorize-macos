"""Bounded systemd operations; engine unit names are derived from policy only."""
from pathlib import Path
import time
from .engine import RetrySchedule

SERVICE='org.freedesktop.systemd1'
MANAGER=SERVICE+'.Manager'
UNIT=SERVICE+'.Unit'
ROOT='/org/freedesktop/systemd1'


class EngineUnits:
    def __init__(self,uid,bus,identity_probe,descriptor_writer,*,cgroup_root=Path('/sys/fs/cgroup'),boot_preparer=None,health_probe=None,clock=time.monotonic):
        if type(uid) is not int or uid<=0:raise ValueError('Invalid engine account.')
        self.uid=uid;self.bus=bus;self.identity_probe=identity_probe
        self.descriptor_writer=descriptor_writer;self.cgroup_root=cgroup_root
        self.boot_preparer=boot_preparer;self.health_probe=health_probe;self.clock=clock
        self.retries={phase:RetrySchedule() for phase in ("boot","desktop")}

    def _name(self,phase):
        if phase not in ('boot','desktop'):raise ValueError('Invalid engine phase.')
        return f'monitorize-remote-login-{phase}@{self.uid}.service'

    def running(self,phase):
        try:
            path=self.bus.call(ROOT,MANAGER,'GetUnit',self._name(phase))
            values=self.bus.properties(path,UNIT)
        except Exception as error:
            name=error.get_dbus_name() if hasattr(error,'get_dbus_name') else ''
            if name=='org.freedesktop.systemd1.NoSuchUnit':return False
            raise
        if values.get('ActiveState') not in ('inactive','failed'):return True
        group=str(self.bus.properties(path,SERVICE+'.Service').get('ControlGroup',''))
        if group:
            # Even an exited unit cannot release identity while its cgroup is populated.
            if not group.startswith('/') or '..' in group.split('/'):raise ValueError('Invalid engine cgroup.')
            try:
                events=(self.cgroup_root/group.lstrip('/')/'cgroup.events').read_text()
                return any(line.split()==['populated','1'] for line in events.splitlines())
            except FileNotFoundError:return False
        return False

    def start(self,phase):
        name=self._name(phase)
        retry=self.retries[phase];now=self.clock()
        if retry.deadline is not None and not retry.due(now):return False
        try:
            if phase=='boot' and self.boot_preparer is not None:self.boot_preparer()
            return self.bus.call(ROOT,MANAGER,'StartUnit',name,'replace')
        finally:retry.failed(now)
    def stop(self,phase):return self.bus.call(ROOT,MANAGER,'StopUnit',self._name(phase),'replace')
    def identity_free(self):return self.identity_probe()
    def prepare_desktop(self,caller,generation,descriptor):return self.descriptor_writer(caller,generation,descriptor)

    def readiness(self,phase):
        self._name(phase)
        values=self.health_probe(phase) if self.health_probe is not None else {}
        if values.get('capture_ready') is True:self.retries[phase].healthy()
        return values
