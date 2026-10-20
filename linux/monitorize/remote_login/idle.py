"""Authenticated-stream idle policy. Caller serializes request/expiry operations."""
import time


class IdleDisplay:
    def __init__(self,prepare,remove,*,clock=time.monotonic):
        self.prepare=prepare;self.remove=remove;self.clock=clock
        self.client_disconnected=False
        self.target=None;self.requests=set();self.active=set();self.frames_ready=set();self.deadline=None
    def request(self,message):
        operation=message.get('operation');client=message.get('client_id');request=message.get('request_id')
        if any(not isinstance(v,str) or not v or len(v)>256 for v in (client,request)):
            raise ValueError('Missing authenticated client/request identity.')
        key=(client,request)
        if operation=='prepare':
            if len(self.requests)>=64 and key not in self.requests:raise ValueError('Too many pending requests.')
            self.requests.add(key);self.deadline=None;self.client_disconnected=False
            try:
                if self.target is None:self.target=self.prepare()
            except Exception:
                # Preparation can reconnect the output before activation fails.
                self.requests.discard(key)
                if not self.requests and not self.active:self.deadline=self.clock()+20
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
                self.deadline=self.clock()+20
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
        if self.target is not None and self.deadline is None:self.deadline=self.clock()+20
    @property
    def state(self):
        return 'streaming' if self.active else 'disconnect_grace' if self.deadline is not None and self.client_disconnected else 'desktop_listening'
