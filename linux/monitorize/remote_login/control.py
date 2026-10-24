"""Bounded local control bridge: token plus exact managed Sunshine PID/UID."""
import hmac
import json
import os
from pathlib import Path
import socket
import stat
import struct
import threading


class ControlServer:
    def __init__(self,path,token,process,request,lock):
        self.path=Path(path);self.token=token;self.process=process;self.request=request;self.lock=lock
        self.stop=threading.Event();self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        if self.path.exists() or self.path.is_symlink():
            info=self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('Unsafe control socket.')
            self.path.unlink()
        self.socket.bind(str(self.path));self.path.chmod(0o600);self.socket.listen(4);self.socket.settimeout(.25)
        self.thread=threading.Thread(target=self._serve,daemon=True,name='remote-login-control');self.thread.start()
    def _serve(self):
        while not self.stop.is_set():
            try:peer,_=self.socket.accept()
            except socket.timeout:continue
            except OSError:break
            with peer:
                peer.settimeout(18)
                operation='authentication'
                try:
                    pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    child=self.process()
                    if uid!=os.getuid() or child is None or child.pid!=pid or child.poll() is not None:
                        raise ValueError('Not the managed engine.')
                    data=bytearray()
                    while b'\n' not in data and len(data)<=65536:
                        chunk=peer.recv(min(4096,65537-len(data)))
                        if not chunk:break
                        data.extend(chunk)
                    if len(data)>65536 or data.count(b'\n')!=1 or not data.endswith(b'\n'):raise ValueError('Invalid request framing.')
                    values=json.loads(data)
                    if (not isinstance(values,dict) or type(values.get('version')) is not int or values['version']!=1 or
                        type(values.get('instance')) is not int or values['instance']!=1 or
                        not isinstance(values.get('token'),str) or not hmac.compare_digest(values['token'],self.token)):
                        raise ValueError('Invalid control authentication.')
                    with self.lock:
                        operation=values.get('operation') if values.get('operation') in ('prepare','stream_started','stream_ready','stream_stopped','release','abort') else 'invalid operation'
                        result=self.request(values)
                    reply={'version':1,'ok':True,**result}
                except Exception as error:
                    # Never log the request, token, or arbitrary exception text.
                    print('Remote display control failed during '+operation+': '+type(error).__name__+
                          '. Inspect journalctl -u monitorize-remote-login.service and the engine unit journal.',flush=True)
                    reply={'version':1,'ok':False,'error':'Remote display operation failed. Inspect journalctl -u monitorize-remote-login.service and the engine unit journal, then retry.'}
                try:peer.sendall(json.dumps(reply).encode()+b'\n')
                except OSError:pass
    def close(self):
        self.stop.set();self.socket.close();self.thread.join(timeout=1)
        self.path.unlink(missing_ok=True)
