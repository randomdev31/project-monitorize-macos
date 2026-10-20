"""Restricted boot engine lifecycle, to be hosted by the installed non-root unit.

The supervisor/service adapter supplies validated root-owned executable/config
paths. This controller accepts no client commands, desktop sockets or settings.
"""
import re
from .engine import RetrySchedule


class BootHost:
    def __init__(self,engine,paths,executable,config,assets,*,prepare=None):
        self.engine=engine;self.paths=paths;self.executable=executable
        self.config=config;self.assets=assets;self.retry=RetrySchedule()
        self.closed=False;self.output=None;self.state='waiting_for_greeter'
        self.started=False;self.prepare=prepare;self.control_environment=None

    def step(self,phase,output,now):
        if self.closed:return False
        if phase not in ('greeter','waiting'):
            self.close();self.state='stopped_for_login';return False
        if output is not None and not re.fullmatch(r'Virtual-[0-9]+',output):
            raise ValueError('Invalid exact boot output.')
        if self.control_environment is not None and output is None:output='Virtual-0'
        if self.output is not None and output!=self.output:
            self.engine.stop();self.retry.failed(now);self.output=None
            self.state='output_changed';return True
        code=self.engine.reap()
        if code is not None:
            self.retry.failed(now);self.state='retry_wait';self.output=None
        if phase!='greeter' or output is None:
            if self.engine.running:self.engine.stop()
            self.state='waiting_for_greeter';return True
        if self.engine.running:
            # Listening/capture readiness is a separate validated health signal.
            self.state='engine_running';return True
        if self.retry.deadline is not None and not self.retry.due(now):
            self.state='retry_wait';return True
        argv=[str(self.executable),str(self.config),'capture=kms','output_name='+output,
              'stream_audio=disabled','controller=disabled','upnp=disabled',
              'origin_web_ui_allowed=pc']
        argv.extend(key+'='+value for key,value in self.paths.config_overrides().items())
        environment=dict(PATH='/usr/sbin:/usr/bin:/sbin:/bin',LANG='C.UTF-8',
            HOME=str(self.paths.lock.parent),XDG_CONFIG_HOME=str(self.paths.lock.parent),
            XDG_RUNTIME_DIR=str(self.paths.lock.parent/'runtime'),XDG_SEAT='seat0',
            SUNSHINE_ASSETS_DIR=str(self.assets),MONITORIZE_REQUIRE_EXACT_OUTPUT='1',
            MONITORIZE_CAPTURE_OUTPUT=output)
        if self.control_environment is not None:
            environment.update(self.control_environment)
            environment.pop('MONITORIZE_CAPTURE_OUTPUT',None)
        try:
            if self.prepare is None:self.engine.start(argv,environment)
            else:self.engine.start(argv,environment,prepare=self.prepare)
        except (OSError,ValueError,RuntimeError):
            self.retry.failed(now);self.state='start_failed';return True
        self.output=output;self.started=True;self.state='engine_running'
        # Retry attempts reset only after an explicit, sustained health result,
        # not merely Popen success; repeated startup exits therefore back off.
        return True

    def healthy(self):
        if self.engine.running:self.retry.healthy()

    def close(self):
        self.retry.cancel();self.engine.stop();self.closed=True;self.state='stopped'
