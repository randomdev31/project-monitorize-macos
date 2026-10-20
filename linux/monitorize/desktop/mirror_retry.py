"""Cancellable retry policy for one existing-screen Mirror host; no display actions."""
import copy
import time
from PyQt6.QtCore import QTimer


class MirrorRetry:
    delays=(2,5,15,60)
    def __init__(self,launch,status,engine_alive,*,schedule=None,clock=time.monotonic):
        self.launch=launch;self.status=status;self.engine_alive=engine_alive
        self.schedule=schedule or QTimer.singleShot;self.clock=clock
        self.intent=None;self.pending=False;self.restarting=False;self.epoch=0;self.attempt=0;self.healthy_since=None
    def arm(self,config,enabled):
        if self.restarting:return
        self.cancel()
        if enabled and config.get('display_type')=='Mirror':self.intent=copy.deepcopy(config)
    def cancel(self):
        self.epoch+=1;self.intent=None;self.pending=False;self.attempt=0;self.healthy_since=None
    def bind_output(self,output):
        if self.intent is not None:self.intent['mirror_output']=output
    def healthy(self):
        if self.healthy_since is None:self.healthy_since=self.clock()
        if self.clock()-self.healthy_since>=5:self.attempt=0
    def failed(self,error):
        if self.intent is None or self.pending:return
        self.healthy_since=None;self.pending=True
        delay=self.delays[min(self.attempt,len(self.delays)-1)];self.attempt+=1
        token=self.epoch
        self.status(f'{error} Retrying Mirror in {delay} seconds.')
        self.schedule(delay*1000,lambda:self._retry(token))
    def _retry(self,token):
        if token!=self.epoch or not self.pending or self.intent is None:return
        if self.engine_alive():
            self.status('Waiting for the previous Sunshine process to exit before retrying Mirror.')
            self.schedule(1000,lambda:self._retry(token));return
        self.pending=False;self.restarting=True
        try:self.launch(copy.deepcopy(self.intent))
        except Exception as error:self.failed(f'Mirror restart failed: {error}')
        finally:self.restarting=False
