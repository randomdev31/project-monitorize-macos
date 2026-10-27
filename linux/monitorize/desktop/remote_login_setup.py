"""Qt-thread enrollment coordination; privileged work stays in the installed helper."""
import os
import time
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from monitorize.platform.system_setup import apply_remote_login_setup, remote_login_setup_status
from monitorize.platform.sunshine_service import is_sunshine_running
from .remote_login_controller import configure, controller_snapshot, restore_controller_snapshot


class RemoteLoginSetupCoordinator(QObject):
    finished=pyqtSignal(object)
    _worker_done=pyqtSignal(object)

    def __init__(self,backend):
        super().__init__(backend)
        self.backend=backend;self.busy=False;self._cancelled=False;self._inflight=False
        self._snapshot=None;self._paused_runtime=None;self._root_result=None
        self._observed_runtime=None;self._listener_observed=False
        self._timer=QTimer(self);self._timer.setInterval(100);self._timer.timeout.connect(self._advance)
        self._worker_done.connect(self._root_finished)

    def begin(self,enabled):
        if self.busy or self.backend._closing:return
        if not enabled:raise ValueError('Disable uses the existing explicit setup path.')
        self._cancelled=False;self._root_result=None;self._snapshot=None;self._paused_runtime=None
        try:
            status=remote_login_setup_status()
            if not status.get('live_available'):raise ValueError(status.get('live_message') or 'Install matching live-enrollment service updates first.')
            session=self.backend.session;runtime=session.client_runtime
            if is_sunshine_running(2) or getattr(self.backend.streaming,'third_streaming',False):
                raise ValueError('Stop Display 2 before enabling remote login.')
            if (session.busy or getattr(self.backend.streaming,'streaming',False)
                    or (session.active and not (runtime and runtime.active))
                    or getattr(self.backend._remote_login,'status',{}).get('capture_ready')):
                raise ValueError('Stop the current stream before enabling remote login.')
            if runtime and runtime.active:
                self._snapshot=runtime.pause_idle_for_enrollment();self._paused_runtime=runtime
            self._intent=self.backend._session_start_generation
            self.busy=True;self.backend._remote_setup_busy=True;self.backend.remoteLoginSetupChanged.emit()
            self._deadline=time.monotonic()+20
            self._timer.start();self._advance()
        except Exception as error:
            self._finish(dict(success=False,configured=False,activated=False,reboot_required=False,message=str(error)))

    def _advance(self):
        if not self.busy:return
        if self._root_result is not None:
            self._check_listener();return
        if self._inflight:return
        if self._cancelled or self.backend._closing:
            self._finish(dict(success=False,configured=False,message='Remote-login setup cancelled.'));return
        if self._paused_runtime and not self._paused_runtime.enrollment_pause_complete(self._snapshot):
            if time.monotonic()>=self._deadline:
                self._finish(dict(success=False,configured=False,message='Listener cleanup did not finish. Retry setup after stopping streaming.'))
            return
        self._inflight=True
        future=self.backend._background_executor.submit(self._work)
        def done(future):
            try:result=future.result()
            except Exception:result=dict(success=False,message='Remote-login setup did not complete. Inspect setup status before retrying.')
            try:self._worker_done.emit(result)
            except RuntimeError:pass  # GUI has been destroyed; retained root receipt permits recovery.
        future.add_done_callback(done)

    def _work(self):
        snapshot=None;controller=False
        try:
            snapshot=controller_snapshot()
            configure(True);controller=True
            result=apply_remote_login_setup(True)
            if result.get('success'):
                from monitorize.config.settings import saved_display_idle_timeout
                from monitorize.platform.system_setup import apply_display_idle_timeout
                seconds=saved_display_idle_timeout()
                if seconds is not None and remote_login_setup_status().get('display_idle_timeout_seconds') != seconds:
                    synced=apply_display_idle_timeout(seconds)
                    if not synced.get('success'):
                        result={**result,'success':False,'partial':True,
                                'message':'Remote login is saved, but its disconnect timer could not be synchronized. Retry setup.'}
        except Exception:
            result=dict(success=False,message='Remote-login setup or desktop-controller configuration failed.')
        if not result.get('success') and 'configured' not in result:
            try:result={**result,'configured':bool(remote_login_setup_status().get('enabled'))}
            except Exception:result={**result,'configured':True,'partial':True}
        if not result.get('success') and not result.get('configured') and snapshot is not None:
            try:restore_controller_snapshot(snapshot);controller=False
            except Exception:result={**result,'partial':True,'message':'Desktop controller restoration needs attention. Inspect setup status before retrying.'}
        return {**result,'controller_configured':controller}

    def _root_finished(self,result):
        if not self.busy:return
        self._inflight=False
        if self.backend._closing:
            self._finish({**result,'success':False,'activated':False});return
        self.backend._finish_remote_login_setup({**result,'_live_pending':True})
        if self._cancelled:
            runtime=self.backend._remote_login
            runtime.participant.want_running=False
            runtime.stop()
            self._finish({**result,'success':False,'partial':bool(result.get('configured')),
                          'message':'Remote-login setup stopped. Saved startup settings are retained.'});return
        if not result.get('success') or not result.get('controller_configured'):
            self._finish({**result,'success':False,'partial':bool(result.get('partial') or result.get('configured'))});return
        if result.get('uid')!=os.getuid() or not result.get('session'):
            self._finish({**result,'success':False,'partial':True,'message':'Remote login is saved, but its desktop context could not be verified. Retry setup.'});return
        self._root_result=result;self._deadline=time.monotonic()+60
        runtime=self.backend._remote_login
        self._listener_observed=False;self._observed_runtime=runtime
        runtime.changed.connect(self._listener_changed)
        if result.get('reused') and runtime.participant.want_running:
            runtime.poll()
        elif hasattr(runtime,'start'):runtime.start()
        self._check_listener()

    def _listener_changed(self):
        # Runtime dispatch also emits changed while busy. Only a completed
        # post-helper observation is proof of current listener health.
        if self._observed_runtime is not None and not getattr(self._observed_runtime,'busy',False):
            self._listener_observed=True
        self._check_listener()

    def _check_listener(self):
        if not self.busy or self._root_result is None:return
        runtime=self.backend._remote_login;status=runtime.status;result=self._root_result
        if self._cancelled:
            self._finish({**result,'success':False,'partial':True,'message':'Setup stopped; startup settings are saved.'});return
        if self._listener_observed and (status.get('startup_error') or status.get('control_error') or status.get('state') in ('error','authentication_error')):
            self._finish({**result,'success':False,'partial':True,'message':'Remote login is saved, but could not start. Retry setup.'});return
        if (self._listener_observed and status.get('uid')==os.getuid() and status.get('session')==result['session']
            and status.get('desktop_owned') is True and status.get('listening') is True
            and runtime.participant.generation and runtime.participant.epoch
            and status.get('epoch')==runtime.participant.epoch):
            self._finish({**result,'success':True,'activated':True,
                'message':'Remote login enabled. Available now and after future boots.'});return
        if time.monotonic()>=self._deadline:
            self._finish({**result,'success':False,'partial':True,'message':'Remote login is saved, but its listener did not become ready. Retry setup.'})

    def _finish(self,result):
        self._timer.stop()
        if self._observed_runtime is not None:
            self._observed_runtime.changed.disconnect(self._listener_changed)
            self._observed_runtime=None
        if self._paused_runtime is not None:
            resume=(not result.get('configured') and not self._cancelled and not self.backend._closing
                    and self._intent==self.backend._session_start_generation)
            self._paused_runtime.resume_enrollment_pause(self._snapshot,instances=(1,) if resume else ())
            self._paused_runtime=None;self._snapshot=None
        self.busy=False;self.backend._remote_setup_busy=False
        if not self.backend._closing:
            self.backend.remoteLoginSetupChanged.emit()
            self.finished.emit({'activated':False,'reboot_required':False,**result})

    def cancel(self):
        self._cancelled=True
        if not self.busy:return
        if self._root_result is not None:
            self.backend._remote_login.stop();self._check_listener()
        elif not self._inflight:self._advance()
