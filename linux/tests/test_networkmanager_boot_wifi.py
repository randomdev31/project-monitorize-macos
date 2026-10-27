import copy
import unittest
import tempfile
from pathlib import Path
from monitorize.platform.networkmanager_boot_wifi import WifiOperations, NmProblem
from linux.tests.test_boot_wifi_settings import profile

UUID='9a984bd2-e871-4650-b0c2-060cf9cc1354'
PATH='/org/freedesktop/NetworkManager/Settings/1'


class FakeTransport:
    def __init__(self):
        self.data=profile();self.version=2;self.writes=[];self.failure=None;self.nmversion='1.56.0'
        self.deleted=False;self.unsaved=False;self.filename='/etc/NetworkManager/system-connections/test.nmconnection'
    def close(self):pass
    def properties(self,path,interface):
        if path=='/org/freedesktop/NetworkManager':return {'Version':self.nmversion,'ActiveConnections':['/active'],'WirelessEnabled':True}
        if path=='/active':return {'Type':'802-11-wireless','Connection':PATH}
        return {'VersionId':self.version,'Unsaved':self.unsaved,'Filename':self.filename}
    def call(self,path,interface,method,args=(),signature='',**kwargs):
        if method=='ListConnections':return [[] if self.deleted else [PATH]]
        if method=='GetSettings':return [copy.deepcopy(self.data)]
        if method=='Update2':
            self.writes.append((path,copy.deepcopy(args),signature,kwargs))
            if self.failure:raise self.failure
            self.data=args[0];self.version+=1
            return [{}]
        raise AssertionError(method)


class BootWifiClientTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.receipt=Path(self.temp.name)/"confirmations.json"
        self.bus=FakeTransport();self.ops=WifiOperations(lambda:self.bus,receipt_path=self.receipt)

    def test_discovery_is_readonly_and_identifies_active_uuid(self):
        result=self.ops.discover()
        self.assertEqual(result['profiles'][0]['uuid'],UUID)
        self.assertTrue(result['profiles'][0]['active'])
        self.assertEqual(self.bus.writes,[])

    def test_exact_profile_update_and_no_other_mutating_methods(self):
        result=self.ops.configure(UUID,'2','test-password')
        self.assertTrue(result['success'])
        self.assertFalse(result['boot_verified'])
        self.assertEqual(len(self.bus.writes),1)
        path,args,signature,options=self.bus.writes[0]
        self.assertEqual(path,PATH)
        self.assertEqual(signature,'a{sa{sv}}ua{sv}')
        self.assertEqual(int(args[1]),1)
        self.assertEqual(int(args[2]['version-id']),2)
        self.assertTrue(options['interactive'])
        self.assertNotIn('test-password',str(result))

    def test_stale_version_and_deleted_profile_never_write(self):
        self.assertEqual(self.ops.configure(UUID,'1','test-password')['code'],'profile_changed')
        self.bus.deleted=True
        self.assertEqual(self.ops.configure(UUID,'2','test-password')['code'],'profile_changed')
        self.assertEqual(self.bus.writes,[])

    def test_unsupported_and_unsaved_do_not_mutate(self):
        self.bus.nmversion='1.42.0'
        self.assertEqual(self.ops.discover()['status']['code'],'unsupported')
        self.assertFalse(self.ops.configure(UUID,'2','test-password')['success'])
        self.bus.nmversion='1.56.0';self.bus.unsaved=True
        self.assertFalse(self.ops.configure(UUID,'2','test-password')['success'])
        self.assertEqual(self.bus.writes,[])

    def test_unknown_outcome_is_not_retried_and_secret_is_never_emitted(self):
        self.bus.failure=NmProblem('outcome_unknown')
        result=self.ops.configure(UUID,'2','SENTINEL-password')
        self.assertEqual(result['code'],'outcome_unknown')
        self.assertEqual(len(self.bus.writes),1)
        self.assertNotIn('SENTINEL',str(result))

    def test_authorization_failure_sanitizes_even_secret_bearing_errors(self):
        self.bus.failure=RuntimeError('SENTINEL-secret in remote response')
        result=self.ops.configure(UUID,'2','SENTINEL-password')
        self.assertFalse(result['success'])
        self.assertNotIn('SENTINEL',str(result))
        self.assertEqual(len(self.bus.writes),1)

    def test_empty_secret_is_noop_and_flags_alone_never_boot_verified(self):
        result=self.ops.configure(UUID,'2','')
        self.assertFalse(result['success'])
        self.assertEqual(self.bus.writes,[])

    def test_confirmation_survives_restart_and_invalidates_changed_profile(self):
        self.assertFalse(self.ops.discover()['profiles'][0]['setup_saved'])
        self.assertTrue(self.ops.configure(UUID,'2','test-password')['success'])
        restarted=WifiOperations(lambda:self.bus,receipt_path=self.receipt)
        self.assertTrue(restarted.discover()['profiles'][0]['setup_saved'])
        self.assertNotIn('test-password',self.receipt.read_text())
        self.bus.data['connection']['autoconnect']=False
        self.assertFalse(restarted.discover()['profiles'][0]['setup_saved'])
