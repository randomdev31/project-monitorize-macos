"""Real isolated session-bus wire test; never uses the host system bus."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

PROGRAM=r'''
import json
import multiprocessing
import dbus
from dbus.mainloop import NULL_MAIN_LOOP
from monitorize.remote_login.dbus_service import NAME,PATH,INTERFACE

def serve(pipe):
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    from monitorize.remote_login.dbus_service import ExportedService
    from monitorize.remote_login.service import HandoffService
    DBusGMainLoop(set_as_default=True)
    class Sessions:
        def authenticate(self,sender,uid):return dict(uid=uid,pid=1234,session='s1')
        def snapshot(self):return dict(greeter_ready=False,sessions=[dict(id='s1',uid=1000,seat='seat0',active=True,remote=False,type='wayland')])
    class Units:
        desktop=False
        def running(self,phase):return phase=='desktop' and self.desktop
        def start(self,phase):assert phase=='desktop';self.desktop=True
        def stop(self,phase):self.desktop=False
        def identity_free(self):return not self.desktop
        def prepare_desktop(self,caller,generation,descriptor):assert descriptor=={'capture':'kms'}
    bus=dbus.SessionBus(private=True)
    core=HandoffService(1000,Sessions(),Units())
    core.engine_display=lambda sender,generation,operation:dict(output_name='Virtual-4',operation=operation)
    core.remove_display=lambda sender:dict(success=True,changed=True)
    core.boot_context=lambda sender:dict(generation='boot-fixture',session='g1')
    exported=ExportedService(bus,core)
    GLib.timeout_add(50,exported.tick)
    pipe.send('ready');GLib.MainLoop().run()

context=multiprocessing.get_context('fork')
parent,child=context.Pipe();process=context.Process(target=serve,args=(child,));process.start()
try:
    assert parent.poll(5) and parent.recv()=='ready'
    first=dbus.SessionBus(private=True,mainloop=NULL_MAIN_LOOP)
    interface=dbus.Interface(first.get_object(NAME,PATH,introspect=False),INTERFACE)
    result=json.loads(interface.AcquireDesktop(timeout=3));assert result['granted']
    token=result['generation']
    assert json.loads(interface.BootContext(timeout=3))['session']=='g1'
    assert json.loads(interface.EngineDisplay(token,'prepare',timeout=3))['output_name']=='Virtual-4'
    assert json.loads(interface.RemoveDisplay(timeout=3))['success']
    result=json.loads(interface.PrepareDesktop(token,json.dumps({'capture':'kms'}),timeout=3))
    assert result['state']=='desktop_starting'
    result=json.loads(interface.DesktopReady(token,timeout=3));assert result['capture_ready']
    second=dbus.SessionBus(private=True,mainloop=NULL_MAIN_LOOP)
    other=dbus.Interface(second.get_object(NAME,PATH,introspect=False),INTERFACE)
    try:other.AcquireDesktop(timeout=3);raise AssertionError('second owner granted')
    except dbus.DBusException as error:assert error.get_dbus_name()==NAME+'.Rejected'
    try:interface.PrepareDesktop(token,'private-secret-invalid-json',timeout=3);raise AssertionError('invalid json accepted')
    except dbus.DBusException as error:assert 'private-secret' not in str(error)
    result=json.loads(interface.Stop(token,timeout=3));assert result['state']=='stopped'
    assert not json.loads(interface.AcquireDesktop(timeout=3))['granted']
    interface.Start(timeout=3);assert json.loads(interface.AcquireDesktop(timeout=3))['granted']
    first.close();second.close()
    print('Isolated remote-login D-Bus ownership and sanitized errors passed')
finally:
    process.terminate();process.join(5)
    if process.is_alive():process.kill();process.join(5)
'''


@unittest.skipUnless(shutil.which('dbus-run-session'),'dbus-run-session unavailable')
class DbusIntegrationTest(unittest.TestCase):
    def test_real_wire_ownership_without_host_services(self):
        result=subprocess.run(['dbus-run-session','--',sys.executable,'-c',PROGRAM],
            cwd=Path(__file__).resolve().parents[2],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('sanitized errors passed',result.stdout)
