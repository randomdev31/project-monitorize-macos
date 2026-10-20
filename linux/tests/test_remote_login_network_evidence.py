import json
import unittest
from monitorize.remote_login.network_evidence import collect_network_evidence


class EvidenceTests(unittest.TestCase):
    def run_fixture(self,phases=('greeter','greeter'),failure=False):
        phases=iter(phases)
        def query(argv):
            if failure:raise OSError('fixture secret must not escape')
            if argv[0]=='/usr/bin/nmcli':return '9a984bd2-e871-4650-b0c2-060cf9cc1354:802-11-wireless:wlo1'
            return json.dumps([{'ifname':'wlo1','addr_info':[{'family':'inet','local':'192.0.2.1'},{'family':'inet6','local':'fe80::1'}]}])
        return collect_network_evidence(query=query,phase_reader=lambda:next(phases),boot_reader=lambda:'boot-fixture')

    def test_records_uuid_and_ip_at_greeter_without_ssid_or_secret(self):
        result=self.run_fixture()
        self.assertTrue(result['observed_before_login'])
        self.assertEqual(result['connections'][0]['uuid'],'9a984bd2-e871-4650-b0c2-060cf9cc1354')
        self.assertEqual(result['connections'][0]['addresses'],['192.0.2.1','fe80::1'])
        self.assertFalse(result['remote_reachability_verified'])

    def test_login_during_snapshot_is_inconclusive(self):
        self.assertFalse(self.run_fixture(('greeter','user'))['observed_before_login'])

    def test_desktop_snapshot_cannot_prove_boot_connection(self):
        self.assertFalse(self.run_fixture(('user','user'))['observed_before_login'])

    def test_errors_do_not_leak_exception_or_block_shutdown(self):
        result=self.run_fixture(failure=True)
        self.assertEqual(result['status'],'unknown');self.assertNotIn('secret',json.dumps(result))
        self.assertFalse(result['observed_before_login'])
