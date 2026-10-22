"""Private, atomic identity provisioning and engine-lifetime ownership.

Provisioning is invoked only by explicit setup after legacy engines are stopped.
A lock cannot stop old Sunshine versions that do not participate in this protocol;
setup must independently verify those processes exited before calling migration.
No credential values are returned in status or exception text.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import ctypes
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

FILES=('sunshine_state.json','cacert.pem','cakey.pem')


@dataclass(frozen=True)
class IdentityPaths:
    directory: Path
    state: Path
    cert: Path
    key: Path
    lock: Path

    def config_overrides(self):
        return {'file_state':str(self.state),'credentials_file':str(self.state),
                'cert':str(self.cert),'pkey':str(self.key)}


def identity_paths(directory, *, flat=False):
    directory=Path(directory)
    identity=directory if flat else directory/'identity'
    return IdentityPaths(identity,identity/FILES[0],identity/FILES[1],identity/FILES[2],directory/'engine.lock')


def _directory(path,uid,*,private=True):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=uid or info.st_mode & (0o077 if private else 0o022):
        raise ValueError('Identity directory must be private and owned by the selected account.')


@contextmanager
def acquire_identity_lock(paths, *, uid=None, private_directory=True):
    uid=os.geteuid() if uid is None else uid
    _directory(paths.lock.parent,uid,private=private_directory)
    try:
        fd=os.open(paths.lock,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
        if os.geteuid()==0:os.fchown(fd,uid,-1)
    except FileExistsError:
        fd=os.open(paths.lock,os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=uid or info.st_nlink!=1 or info.st_mode & 0o077:
            raise ValueError('Unsafe remote-login engine lock.')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield fd
    finally:
        os.close(fd)


def _read_private(path,uid):
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as source:
            info=os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=uid or info.st_nlink!=1 or info.st_mode & 0o022 or info.st_size>1024*1024:
                raise ValueError('Unsafe source identity file.')
            result=source.read(1024*1024+1)
            if not result or len(result)>1024*1024:raise ValueError('Invalid source identity file.')
            return result
    except OSError:
        raise ValueError('Source identity is missing or unsafe.') from None


def _rename_exclusive(source,destination):
    # Linux renameat2 makes publication atomic without replacing a raced destination.
    libc=ctypes.CDLL(None,use_errno=True)
    rename=libc.renameat2
    rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    if rename(-100,os.fsencode(source),-100,os.fsencode(destination),1):
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code))


def migrate_identity(source,destination, *, uid):
    """Copy complete identity once; keep the source untouched as rollback backup.

    Caller supplies a trusted, root-managed destination parent in production and
    verifies legacy engines are stopped. Destination must not already exist.
    """
    source=Path(source);destination=Path(destination)
    _directory(source,uid,private=False)
    with acquire_identity_lock(identity_paths(source,flat=True),uid=uid,private_directory=False):
        credentials=source/'credentials'
        if credentials.exists() or credentials.is_symlink():
            _directory(credentials,uid,private=False)
        else:
            credentials=source
        raw={name:_read_private((source if name==FILES[0] else credentials)/name,uid) for name in FILES}
        try:
            root=json.loads(raw[FILES[0]])['root']
            if not isinstance(root,dict) or not isinstance(root.get('uniqueid'),str) or not root['uniqueid'].strip():
                raise ValueError()
            if not any(isinstance(root.get(k),list) for k in ('named_devices','devices')):raise ValueError()
        except (ValueError,KeyError,TypeError):
            raise ValueError('A complete paired Sunshine identity is required.') from None
        stage=Path(tempfile.mkdtemp(prefix='.'+destination.name+'.',dir=destination.parent))
        try:
            identity=stage/'identity';identity.mkdir(mode=0o700)
            for name,data in raw.items():
                fd=os.open(identity/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as target:
                    target.write(data);target.flush();os.fsync(target.fileno())
                if os.geteuid()==0:os.chown(identity/name,uid,-1)
            for path in (identity,stage):
                if os.geteuid()==0:os.chown(path,uid,-1)
                fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
            _rename_exclusive(stage,destination)
            fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return {'changed':True,'directory':str(destination),'backup':str(source)}


def fallback_grant_path(uid):
    return Path('/run/monitorize/desktop-fallback')/(str(uid)+'.json')


def _fallback_context():
    import subprocess
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    session=os.environ.get('XDG_SESSION_ID','')
    if not session:
        session=subprocess.run(['loginctl','show-user',str(os.getuid()),'--property=Display','--value'],
            capture_output=True,text=True,timeout=3,check=True).stdout.strip()
    return boot,session


def desktop_fallback_allowed(settings, *, owner_uid=0):
    """Root grants desktop ownership only for this boot/account/login session."""
    path=fallback_grant_path(settings.uid)
    try:
        parent=path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=owner_uid or parent.st_mode & 0o022:return False
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd) as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=owner_uid or info.st_mode & 0o022 or info.st_size>4096:return False
            grant=json.load(stream)
        boot,session=_fallback_context()
        return bool(session and grant==dict(uid=settings.uid,session=session,boot_id=boot))
    except (OSError,ValueError,TypeError):return False
