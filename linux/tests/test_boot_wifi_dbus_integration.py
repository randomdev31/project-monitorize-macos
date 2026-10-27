"""Typed update round trip on an isolated bus, never the host NetworkManager."""
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

PROGRAM=r'''
import copy
import multiprocessing
import dbus
import dbus.service
from dbus.mainloop import NULL_MAIN_LOOP
from dbus.mainloop.glib import DBusGMainLoop, threads_init
from gi.repository import GLib
from monitorize.platform.networkmanager_boot_wifi import WifiOperations,NmTransport,SERVICE,ROOT,CONNECTION
threads_init()
UUID='9a984bd2-e871-4650-b0c2-060cf9cc1354'
PATH=ROOT+'/Settings/1'

def server(ready):
    DBusGMainLoop(set_as_default=True)
    bus=dbus.SessionBus(private=True)
    name=dbus.service.BusName(SERVICE,bus=bus,do_not_queue=True)
    data={'connection':{'id':'same-name','uuid':UUID,'type':'802-11-wireless','autoconnect':False,'permissions':dbus.Array(['user:test:'],signature='s')},
          '802-11-wireless':{'mode':'infrastructure','ssid':dbus.ByteArray(b'test')},
          '802-11-wireless-security':{'key-mgmt':'wpa-psk','psk-flags':dbus.UInt32(1)},
          'ipv4':{'method':'auto'},'future-setting':{'preserved':dbus.UInt32(77)}}
    class Manager(dbus.service.Object):
        @dbus.service.method('org.freedesktop.DBus.Properties',in_signature='s',out_signature='a{sv}')
        def GetAll(self,interface):
            return {'Version':'1.56.0','ActiveConnections':dbus.Array([],signature='o'),'WirelessEnabled':True}
    class Settings(dbus.service.Object):
        @dbus.service.method(SERVICE+'.Settings',in_signature='',out_signature='ao')
        def ListConnections(self):return [PATH]
    class Profile(dbus.service.Object):
        version=2
        @dbus.service.method('org.freedesktop.DBus.Properties',in_signature='s',out_signature='a{sv}')
        def GetAll(self,interface):
            return {'VersionId':dbus.UInt64(self.version),'Unsaved':False,'Filename':'/fake/test.nmconnection'}
        @dbus.service.method(CONNECTION,in_signature='',out_signature='a{sa{sv}}')
        def GetSettings(self):
            result={section:dict(values) for section,values in data.items()}
            result['802-11-wireless-security'].pop('psk',None)
            return result
        @dbus.service.method(CONNECTION,in_signature='a{sa{sv}}ua{sv}',out_signature='a{sv}',message_keyword='message')
        def Update2(self,settings,flags,args,message):
            assert message.get_allow_interactive_authorization()
            assert int(flags)==1
            assert isinstance(args['version-id'],dbus.UInt64) and int(args['version-id'])==self.version
            assert isinstance(settings['connection']['permissions'],dbus.Array)
            assert settings['connection']['permissions'].signature=='s'
            assert not settings['connection']['permissions']
            assert settings['future-setting']['preserved']==77
            assert settings['ipv4']['method']=='auto'
            assert settings['802-11-wireless-security']['psk']=='secret-for-fixture'
            data.clear();data.update(settings);self.version+=1
            return {}
    objects=[Manager(bus,ROOT),Settings(bus,ROOT+'/Settings'),Profile(bus,PATH)]
    ready.send(True)
    GLib.MainLoop().run()

context=multiprocessing.get_context('fork')
parent,child=context.Pipe()
process=context.Process(target=server,args=(child,),daemon=True)
process.start()
try:
    assert parent.poll(5) and parent.recv() is True
    def factory():return NmTransport(dbus.SessionBus(private=True,mainloop=NULL_MAIN_LOOP))
    operations=WifiOperations(factory)
    discovered=operations.discover()
    assert discovered['profiles'][0]['uuid']==UUID, discovered['status']['code']
    result=operations.configure(UUID,'2','secret-for-fixture')
    assert result['success'],result['code']
    assert not result['boot_verified']
    assert 'secret-for-fixture' not in str(result)
    stale=operations.configure(UUID,'2','secret-for-fixture')
    assert stale['code']=='profile_changed'
    print('Typed NetworkManager fixture discovery/update/version guard passed')
finally:
    process.terminate();process.join(5)
'''


class BootWifiDbusIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('dbus-run-session'),'dbus-run-session unavailable')
    def test_typed_round_trip_with_interactive_authorization(self):
        result=subprocess.run(['dbus-run-session','--',sys.executable,'-c',PROGRAM],
            cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('version guard passed',result.stdout)
