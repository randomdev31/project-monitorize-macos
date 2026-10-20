"""Root policy and bounded desktop descriptor validation; no secret retrieval."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import pwd
import re
import stat

SETTINGS=Path('/etc/monitorize/remote-login.json')


@dataclass(frozen=True)
class Settings:
    enabled: bool
    uid: int
    gid: int
    username: str
    home: str
    profile: str
    encoder: str
    adapter: str

    @property
    def directory(self):return Path('/var/lib/monitorize/remote-login')/str(self.uid)
    @property
    def runtime(self):return Path('/run/monitorize-remote-login')/str(self.uid)


def read_settings(path=SETTINGS,*,owner_uid=0,account_lookup=pwd.getpwuid):
    path=Path(path)
    try:
        parent=path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=owner_uid or parent.st_mode & 0o022:
            raise ValueError()
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd) as source:
            info=os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=owner_uid or info.st_mode & 0o022 or info.st_size>4096:
                raise ValueError()
            values=json.load(source)
        if not isinstance(values,dict) or values.get('schema_version')!=1:raise ValueError()
        uid=values['uid'];gid=values['gid'];enabled=values['enabled']
        if type(uid) is not int or uid<=0 or type(gid) is not int or gid<0 or type(enabled) is not bool:raise ValueError()
        account=account_lookup(uid)
        if (account.pw_uid!=uid or account.pw_gid!=gid or account.pw_name!=values['username'] or
            account.pw_dir!=values['home']):raise ValueError()
        if values['manager']!='plasmalogin.service':raise ValueError()
        encoder=values['encoder'];adapter=values['adapter'];profile=values['profile']
        if encoder not in ('software','vaapi','nvenc'):raise ValueError()
        if not isinstance(adapter,str) or (adapter and not re.fullmatch(r'/dev/dri/renderD[0-9]+',adapter)):raise ValueError()
        if not isinstance(profile,str) or not Path(profile).is_absolute() or '\n' in profile or '\r' in profile:raise ValueError()
        # Compatibility only: retire an existing experimental enrollment without
        # losing its original encoder. There is no persistent runtime anymore.
        mode=values.get('transition_mode','reconnect')
        if mode not in ('reconnect','seamless-experimental'):raise ValueError()
        if mode=='seamless-experimental':
            encoder=values.get('reconnect_encoder','software')
            adapter=values.get('reconnect_adapter','')
            if encoder not in ('software','vaapi','nvenc'):raise ValueError()
            if not isinstance(adapter,str) or (adapter and not re.fullmatch(r'/dev/dri/renderD[0-9]+',adapter)):raise ValueError()
        return Settings(enabled,uid,gid,account.pw_name,account.pw_dir,profile,encoder,adapter)
    except (OSError,ValueError,TypeError,KeyError):
        raise ValueError('Remote-login configuration is unsafe, unsupported or no longer matches its account.') from None


def validate_descriptor(values,settings,expected_output):
    allowed={'capture','output_name','pipewire_node','wayland_display','display'}
    if not isinstance(values,dict) or set(values)-allowed:raise ValueError('Unsupported desktop descriptor fields.')
    capture=values.get('capture');output=values.get('output_name')
    if capture not in ('kms','kwin') or output!=expected_output or not isinstance(output,str) or not re.fullmatch(r'Virtual-[0-9]+',output):
        raise ValueError('Desktop capture must target the reserved virtual output.')
    result={'capture':capture,'output_name':output}
    if capture=='kwin':
        node=values.get('pipewire_node')
        if type(node) is not int or not 0<node<=2**32-1:raise ValueError('KWin capture requires a valid PipeWire node.')
        result['pipewire_node']=node
    elif 'pipewire_node' in values:raise ValueError('KMS capture does not use a PipeWire node.')
    for name,pattern in (('wayland_display',r'wayland-[0-9]+'),('display',r':[0-9]+(?:\.[0-9]+)?')):
        if name in values:
            value=values[name]
            if not isinstance(value,str) or not re.fullmatch(pattern,value):raise ValueError('Invalid graphical session endpoint.')
            result[name]=value
    return result
