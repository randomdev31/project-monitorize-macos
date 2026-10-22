"""Serialized engine lifetime and bounded retry scheduling; no startup on import."""
import os
import signal
import subprocess
from monitorize.platform.remote_login_identity import acquire_identity_lock


class RetrySchedule:
    delays=(2,5,15,60)

    def __init__(self):self.attempt=0;self.deadline=None;self.cancelled=False

    def failed(self,now):
        if self.cancelled:return None
        delay=self.delays[min(self.attempt,len(self.delays)-1)]
        self.attempt+=1;self.deadline=now+delay
        return self.deadline

    def due(self,now):return not self.cancelled and self.deadline is not None and now>=self.deadline

    def healthy(self):self.attempt=0;self.deadline=None;self.cancelled=False

    def cancel(self):self.cancelled=True;self.deadline=None


class EngineOwner:
    """Trusted caller supplies fixed installed argv and a restricted environment.

    Lock FD is inherited by the child so an unexpected controller exit does not
    free identity ownership while the old Sunshine process is still exiting.
    Supervisor must additionally await unit/process exit before granting a new owner.
    """
    def __init__(self,paths):
        self.paths=paths;self.process=None;self._lock=None

    @property
    def running(self):return self.process is not None and self.process.poll() is None

    def start(self,argv,environment,*,prepare=None,diagnostics=None):
        if self.running:raise RuntimeError('An engine is already running.')
        self.reap()
        self._lock=acquire_identity_lock(self.paths)
        try:
            fd=self._lock.__enter__()
        except Exception:
            self._lock=None;raise
        try:
            if prepare is not None:prepare()
            output=None
            try:
                if diagnostics is not None:
                    import stat
                    fd_output=os.open(diagnostics,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
                    output=os.fdopen(fd_output,'w')
                    info=os.fstat(output.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1:
                        raise ValueError('Unsafe engine diagnostic log.')
                    os.fchmod(output.fileno(),0o600);os.ftruncate(output.fileno(),0)
                self.process=subprocess.Popen(argv,env=environment,stdin=subprocess.DEVNULL,
                    stdout=output if output is not None else subprocess.DEVNULL,
                    stderr=subprocess.STDOUT if output is not None else subprocess.DEVNULL,
                    start_new_session=True,pass_fds=(fd,))
            finally:
                if output is not None:output.close()

        except Exception:
            self._release_parent_lock();raise
        return self.process.pid

    def _release_parent_lock(self):
        if self._lock is not None:
            context=self._lock;self._lock=None;context.__exit__(None,None,None)

    def reap(self):
        if self.process is not None and self.process.poll() is not None:
            code=self.process.wait();self.process=None;self._release_parent_lock();return code
        return None

    def stop(self):
        if self.running:
            try:os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                self.process.wait(timeout=5)
        # If wait fails, retain process/lock; never report a successful handoff.
        self.reap()
