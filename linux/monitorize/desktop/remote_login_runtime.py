"""Qt desktop participant using one stable private D-Bus sender per lifetime."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from PyQt6.QtCore import QObject,QTimer,pyqtSignal
from monitorize.platform.login_capture_probe import find_boot_output
from monitorize.remote_login.settings import SETTINGS,read_settings
from monitorize.remote_login.dbus_service import NAME,PATH,INTERFACE

MESSAGES={
    'greeter_idle':'Login host is listening; the virtual display is disconnected until a client connects.',
    'greeter_preparing':'Preparing the login-screen display.',
    'greeter_disconnect_grace':'Client disconnected; removing the login-screen display after 20 seconds.',
    'waiting_for_greeter':'Waiting for the login screen.',
    'greeter_listening':'Session is starting.',
    'login_available':'Login screen available.',
    'handoff_to_desktop':'Session is starting.',
    'waiting_for_desktop':'Session is starting.',
    'desktop_listening':'Waiting for a client.',
    'streaming':'Client connected.',
    'disconnect_grace':'Client disconnected; removing the display after 20 seconds.',
    'removing':'Releasing capture and removing the virtual display.',
    'desktop_starting':'Session is starting.',
    'desktop_available':'Client connected.',
    'stopped':'Session is not running.',
    'stopping_desktop':'Stopping desktop streaming.',
    'suspended':'Streaming paused because another session owns the seat.',
    'error':'Remote-login service needs attention. Inspect its journal.',
    'unavailable':'Remote-login service is not running or cannot be reached. If you just enabled Start Monitorize After Boot, reboot to activate it.',
}


class Participant:
    def __init__(self,*,factory=None,output_finder=None):
        # A fresh compositor may leave the boot connector disabled until the
        # privileged adoption worker activates it. Capture still requires enabled.
        self.factory=factory;self.output_finder=output_finder or (lambda:find_boot_output(require_enabled=False));self.bus=None;self.interface=None
        self.generation='';self.want_running=True;self.epoch=None

    def _connect(self):
        if self.interface is not None:return
        if self.factory is not None:self.interface=self.factory();return
        import dbus
        from dbus.mainloop import NULL_MAIN_LOOP
        self.bus=dbus.SystemBus(private=True,mainloop=NULL_MAIN_LOOP)
        self.interface=dbus.Interface(self.bus.get_object(NAME,PATH,introspect=False),INTERFACE)

    def _call(self,method,*args):
        self._connect()
        return json.loads(getattr(self.interface,method)(*args,timeout=60 if method=='PrepareDesktop' else 5))

    def poll(self):
        try:
            status=self._call('GetStatus')
            epoch=status.get('epoch')
            if epoch!=self.epoch:self.generation='';self.epoch=epoch
            if not self.want_running and status.get('state')=='waiting_for_desktop':
                return dict(status,state='stopped')
            if status.get('state')=='stopped':self.want_running=False
            if self.want_running:
                if status.get('state') not in ('waiting_for_desktop','handoff_to_desktop','desktop_starting','desktop_available'):
                    return status
                if not self.generation:
                    grant=self._call('AcquireDesktop')
                    if not grant.get('granted'):return dict(status,state=grant.get('state',status['state']))
                    self.generation=grant['generation']
                if status.get('state') in ('waiting_for_desktop','handoff_to_desktop'):
                    output=self.output_finder() or status.get('output_name')
                    if output is None:return dict(state='waiting_for_desktop',capture_ready=False)
                    status=self._call('PrepareDesktop',self.generation,json.dumps({'capture':'kms','output_name':output}))
            return status
        except Exception:
            # Keep the stable sender across a transient timeout. Do not replay a
            # write immediately: next poll observes status before considering start.
            return dict(state='unavailable',capture_ready=False)

    def stop(self):
        self.want_running=False
        try:
            if self.generation:return self._call('Stop',self.generation)
        except Exception:pass
        return self.poll()

    def start(self):
        try:
            self._call('Start');self.want_running=True
        except Exception:return dict(state='unavailable',capture_ready=False)
        return self.poll()

    def close(self):
        try:
            if self.generation:self._call('ReleaseDesktop',self.generation)
        except Exception:pass
        if self.bus is not None:self.bus.close()
        self.bus=None;self.interface=None;self.generation=''


class RemoteLoginRuntime(QObject):
    changed=pyqtSignal()
    _finished=pyqtSignal(object)
    def __init__(self,parent=None,*,participant=None,enabled=None):
        super().__init__(parent)
        if enabled is None:
            enabled=False
            try:
                if SETTINGS.exists():
                    settings=read_settings();enabled=settings.enabled and settings.uid==os.getuid()
            except ValueError:pass
        self.enabled=bool(enabled);self.status={'state':'waiting_for_desktop','capture_ready':False}
        self.participant=participant or Participant();self.closed=False;self.busy=False
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='monitorize-handoff')
        self._finished.connect(self._finish)
        self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.poll)
        if self.enabled:self.timer.start();QTimer.singleShot(0,self.poll)

    @property
    def active(self):
        # Enrollment is not proof that a streaming service is running.
        return self.enabled and self.status.get('state') not in ('stopped','disabled','unavailable','error')
    @property
    def message(self):
        return MESSAGES.get(self.status.get('state'),'Waiting for remote-login ownership.')

    def _submit(self,method):
        if self.closed or self.busy or not self.enabled:return
        self.busy=True;self.changed.emit()
        future=self.executor.submit(method)
        def done(result):
            if not self.closed:
                try:self._finished.emit(result.result())
                except Exception:self._finished.emit({'state':'unavailable','capture_ready':False})
        future.add_done_callback(done)

    def _finish(self,result):
        if self.closed:return
        self.busy=False;self.status=result;self.changed.emit()
    def poll(self):self._submit(self.participant.poll)
    def start(self):self._submit(self.participant.start)
    def stop(self):
        # Queue behind an already dispatched PrepareDesktop; a user Stop must
        # never be dropped just because the ownership worker is currently busy.
        if self.closed or not self.enabled:return
        self.executor.submit(self.participant.stop).add_done_callback(
            lambda f:self._finished.emit(f.result()) if not self.closed else None)
    def close(self):
        if self.closed:return
        self.closed=True;self.timer.stop()
        if self.enabled:self.executor.submit(self.participant.close)
        self.executor.shutdown(wait=False,cancel_futures=not self.enabled)
