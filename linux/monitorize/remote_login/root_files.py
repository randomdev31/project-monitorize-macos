"""Small rollback journal for fixed root configuration paths, never user homes."""
import os
from pathlib import Path
import secrets
import stat


class RootFiles:
    def __init__(self,base=Path('/'),owner_uid=0):
        self.base=Path(base);self.owner_uid=owner_uid;self.snapshots={}

    def _path(self,relative):
        relative=Path(relative)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid setup path.')
        return self.base/relative

    def _parents(self,path):
        directory=self.base
        for part in path.relative_to(self.base).parts[:-1]:
            directory=directory/part
            try:
                directory.mkdir(mode=0o755);directory.chmod(0o755)
            except FileExistsError:pass
            info=directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode & 0o022:
                raise ValueError('Unsafe system configuration directory.')

    def _read(self,path):
        try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:return None
        with os.fdopen(fd,'rb') as source:
            info=os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_nlink!=1 or info.st_mode & 0o022 or info.st_size>65536:
                raise ValueError('Unsafe preexisting setup file.')
            return source.read(65537),stat.S_IMODE(info.st_mode)

    def _write(self,path,data,mode):
        temporary=path.parent/('.monitorize.'+secrets.token_hex(8))
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
            with os.fdopen(fd,'wb') as stream:
                os.fchmod(stream.fileno(),mode);stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if temporary.exists():temporary.unlink()

    def write(self,relative,data,mode=0o644):
        path=self._path(relative);self._parents(path)
        if path not in self.snapshots:self.snapshots[path]=self._read(path)
        self._write(path,data.encode() if isinstance(data,str) else data,mode)

    def rollback(self):
        for path,snapshot in reversed(list(self.snapshots.items())):
            if snapshot is None:
                try:path.unlink()
                except FileNotFoundError:pass
            else:self._write(path,*snapshot)
