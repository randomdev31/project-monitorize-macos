import json
import os
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
from monitorize.remote_login.control import ControlServer

class ControlTests(unittest.TestCase):
 def test_failed_operation_logs_context_without_disclosing_private_exception(self):
  import contextlib,io
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'control.sock'
   process=SimpleNamespace(pid=os.getpid(),poll=lambda:None)
   def fail(message):raise RuntimeError('private-token-fixture')
   output=io.StringIO()
   with contextlib.redirect_stdout(output):
    server=ControlServer(path,'secret',lambda:process,fail,threading.RLock())
    try:
     with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
      client.settimeout(2);client.connect(str(path))
      client.sendall(json.dumps(dict(version=1,instance=1,token='secret',operation='prepare')).encode()+b'\n')
      reply=json.loads(client.recv(4096))
    finally:server.close()
   self.assertFalse(reply['ok'])
   self.assertIn('monitorize-remote-login.service',reply['error'])
   self.assertIn('prepare',output.getvalue())
   self.assertIn('RuntimeError',output.getvalue())
   self.assertNotIn('private-token-fixture',output.getvalue()+str(reply))

 def test_peer_token_framing_and_close(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'control.sock';seen=[]
   process=SimpleNamespace(pid=os.getpid(),poll=lambda:None)
   server=ControlServer(path,'secret',lambda:process,lambda message:seen.append(message['operation']) or {},threading.RLock())
   def request(message):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
     client.settimeout(2);client.connect(str(path));client.sendall(json.dumps(message).encode()+b'\n')
     return json.loads(client.recv(4096))
   try:
    message=dict(version=1,instance=1,token='secret',operation='prepare')
    self.assertTrue(request(message)['ok']);self.assertEqual(seen,['prepare'])
    message['token']='wrong';self.assertFalse(request(message)['ok']);self.assertEqual(seen,['prepare'])
    message['token']='secret';process.pid+=100000
    self.assertFalse(request(message)['ok']);self.assertEqual(seen,['prepare'])
   finally:server.close()
   self.assertFalse(path.exists())
