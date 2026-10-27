"""Authenticated-stream idle policy. Caller serializes request/expiry operations."""
import time
from pathlib import Path

PACKAGE_RECEIPT = Path("/var/lib/monitorize/remote-login-package.json")


class IdleDisplay:
    def __init__(self,prepare,remove,*,clock=time.monotonic,timeout_seconds=20,timeout_provider=None,prepare_mode=None):
        from .settings import validate_idle_timeout
        self.timeout_seconds=validate_idle_timeout(timeout_seconds)
        self.prepare_mode=prepare_mode
        self.timeout_provider=timeout_provider
        self.configuration_error=''
        self.prepare=prepare;self.remove=remove;self.clock=clock
        self.client_disconnected=False
        self.error=''
        self.target=None;self.requests=set();self.active=set();self.frames_ready=set();self.deadline=None
    def schedule_cleanup(self):
        from .settings import validate_idle_timeout
        if self.timeout_provider is not None:
            try:
                self.timeout_seconds=validate_idle_timeout(self.timeout_provider())
                self.configuration_error=''
            except (ValueError,OSError):
                self.configuration_error='Display timeout configuration could not be refreshed; using the last valid value.'
        self.deadline=self.clock()+self.timeout_seconds
    def request(self,message):
        operation=message.get('operation');client=message.get('client_id');request=message.get('request_id')
        if any(not isinstance(v,str) or not v or len(v)>256 for v in (client,request)):
            raise ValueError('Missing authenticated client/request identity.')
        key=(client,request)
        if operation=='prepare':
            if PACKAGE_RECEIPT.exists():
                raise RuntimeError('Remote login is paused for a package transaction; retry after maintenance completes.')
            if len(self.requests)>=64 and key not in self.requests:raise ValueError('Too many pending requests.')
            mode=None
            if self.prepare_mode is not None:
                from .settings import validate_display_mode
                mode=validate_display_mode([message.get('width'),message.get('height'),message.get('fps')])
                different=self.target is not None and mode!=[self.target.get('width'),self.target.get('height'),self.target.get('fps')]
                if different and (self.active or self.requests-{key}):
                    raise ValueError('Another client is using the current display mode; disconnect it before changing resolution.')
            self.requests.add(key);self.deadline=None;self.client_disconnected=False
            try:
                if self.prepare_mode is not None:
                    if self.target is None or different:self.target=self.prepare_mode(mode)
                elif self.target is None:self.target=self.prepare()
                self.error=''
            except Exception:
                # Preparation can reconnect the output before activation fails.
                self.requests.discard(key)
                if not self.requests and not self.active:self.schedule_cleanup()
                self.error='Remote display preparation failed. Check the monitorize-remote-login.service journal, then retry the connection.'
                raise
            return {'target':self.target}
        if operation in ('stream_started','stream_ready'):
            if key not in self.requests or self.target is None:raise ValueError('Stale stream request.')
            self.active.add(key);self.deadline=None
            if operation=='stream_ready':self.frames_ready.add(key)
        elif operation in ('stream_stopped','release','abort'):
            was_active=key in self.active
            known=key in self.requests or was_active
            self.requests.discard(key);self.active.discard(key);self.frames_ready.discard(key)
            if known and not self.requests and not self.active and self.deadline is None:
                self.schedule_cleanup()
                self.client_disconnected=was_active
        else:raise ValueError('Unsupported stream operation.')
        return {}
    def due(self):return self.deadline is not None and self.clock()>=self.deadline and not self.requests and not self.active
    def expire(self):
        if not self.due():return False
        self.remove();self.target=None;self.deadline=None
        return True
    def reset_engine(self):
        # Engine/cgroup exit is verified by caller before clearing live requests.
        self.requests.clear();self.active.clear();self.frames_ready.clear()
        if self.target is not None and self.deadline is None:self.schedule_cleanup()
    def health(self, *, listening, startup_error=''):
        error=startup_error or self.error or self.configuration_error
        return dict(package_paused=PACKAGE_RECEIPT.exists(),package_busy=bool(self.requests or self.active),display_idle_timeout_seconds=self.timeout_seconds,listening=bool(listening),capture_ready=bool(listening and self.frames_ready and not error),
                    startup_error=error,state=self.state)
    @property
    def state(self):
        return 'error' if self.error else 'streaming' if self.active else 'disconnect_grace' if self.deadline is not None and self.client_disconnected else 'desktop_listening'
