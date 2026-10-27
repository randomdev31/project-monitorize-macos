import unittest
from monitorize.remote_login.engine_gate import EngineGate

class Bus:
 def call(self,path,interface,method,*args):
  return {'GetConnectionUnixUser':1000,'GetConnectionUnixProcessID':123,'GetUnit':'/unit','ListSessions':[]}[method]
 def properties(self,path,interface):return {'MainPID':123}
class GateTests(unittest.TestCase):
 def gate(self,**extra):
  return EngineGate(1000,Bus(),lambda:dict(uid=1000,session='s1',generation='a'*32),
    lambda session,generation:session=='s1' and generation=='a'*32,lambda:True,
    session_check=lambda uid,session:True,**extra)
 def test_exact_runner_uid_pid_and_generation_are_required(self):
  gate=self.gate();self.assertEqual(gate.check(':1.5','a'*32)['session'],'s1')
  for generation in ('','bad','b'*32):
   with self.assertRaises(PermissionError):gate.check(':1.5',generation)
 def test_idle_requires_engine_identity_release(self):
  gate=self.gate();gate.identity_free=lambda:False
  with self.assertRaises(RuntimeError):gate.check(':1.5','a'*32,idle=True)
 def test_wrong_process_or_inactive_session_cannot_prepare(self):
  gate=self.gate();gate.bus.properties=lambda *args:{'MainPID':124}
  with self.assertRaises(PermissionError):gate.check(':1.5','a'*32)
  gate=self.gate();gate.session_check=lambda *args:False
  with self.assertRaises(PermissionError):gate.check(':1.5','a'*32)

 def test_idle_refuses_lingering_cgroup_children(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   group=Path(d)/'engine';group.mkdir();procs=group/'cgroup.procs'
   gate=self.gate(cgroup_root=d)
   gate.bus.properties=lambda path,interface:({'MainPID':123,'ControlGroup':'/engine'} if interface.endswith('.Service') else {})
   procs.write_text('123\n456\n')
   with self.assertRaises(RuntimeError):gate.check(':1.5','a'*32,idle=True)
   procs.write_text('123\n');gate.check(':1.5','a'*32,idle=True)

 def test_boot_gate_uses_only_fixed_boot_unit(self):
  from unittest.mock import Mock
  gate=self.gate(phase='boot');original=gate.bus.call;gate.bus.call=Mock(side_effect=original)
  gate.check(':1.5','a'*32)
  self.assertEqual(gate.bus.call.call_args_list[-1].args[-1],'monitorize-remote-login-boot@1000.service')
  gate.bus.properties=lambda *args:{'MainPID':999}
  with self.assertRaises(PermissionError):gate.check(':1.5','a'*32)
