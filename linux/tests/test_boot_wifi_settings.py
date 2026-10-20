import copy
import unittest
from monitorize.platform.boot_wifi_settings import describe_profile, build_boot_wifi_update, settings_fingerprint


def profile(uuid='9a984bd2-e871-4650-b0c2-060cf9cc1354', security='wpa-psk'):
    return {'connection': {'id':'ss','uuid':uuid,'type':'802-11-wireless',
            'permissions':['user:test:'],'autoconnect':False,'autoconnect-priority':7},
        '802-11-wireless':{'ssid':b'ss','mode':'infrastructure'},
        '802-11-wireless-security':{'key-mgmt':security,'psk-flags':1},
        'ipv4':{'method':'manual','address-data':[{'address':'192.0.2.3','prefix':24}]},
        'custom':{'future':'preserve'}}


class BootWifiSettingsTest(unittest.TestCase):
    def test_narrow_change_preserves_every_other_field_and_original(self):
        original=profile()
        snapshot=copy.deepcopy(original)
        changed=build_boot_wifi_update(original,'test-password')
        self.assertEqual(original,snapshot)
        self.assertEqual(changed['connection']['permissions'],[])
        self.assertTrue(changed['connection']['autoconnect'])
        self.assertEqual(changed['802-11-wireless-security']['psk-flags'],0)
        self.assertEqual(changed['802-11-wireless-security']['psk'],'test-password')
        changed['connection']['permissions']=snapshot['connection']['permissions']
        changed['connection']['autoconnect']=False
        changed['802-11-wireless-security'].pop('psk')
        changed['802-11-wireless-security']['psk-flags']=1
        self.assertEqual(changed,snapshot)

    def test_uuid_not_duplicate_display_name_identifies_profile(self):
        a=describe_profile(profile(),active=True,version=2,persistent=True)
        b=describe_profile(profile('eba3592d-a36d-47c8-a2ba-4e3d76caa211'),active=False,version=3,persistent=True)
        self.assertEqual(a['name'],b['name'])
        self.assertNotEqual(a['uuid'],b['uuid'])
        self.assertEqual(a['version'],'2')

    def test_personal_security_only(self):
        for security,expected in [('wpa-psk',True),('sae',True),('wpa-eap',False),('none',False),('owe',False)]:
            self.assertEqual(describe_profile(profile(security=security),active=False,version=2,persistent=True)['eligible'],expected)
        data=profile();data['802-11-wireless']['mode']='ap'
        with self.assertRaises(ValueError):build_boot_wifi_update(data,'password123')

    def test_missing_uuid_enterprise_and_readonly_refuse(self):
        for mutation in ('uuid','802-1x','read-only'):
            data=profile()
            if mutation=='uuid':data['connection'].pop('uuid')
            elif mutation=='802-1x':data['802-1x']={'password':'hidden'}
            else:data['connection']['read-only']=True
            with self.assertRaises(ValueError):build_boot_wifi_update(data,'password123')

    def test_password_validation_and_no_secret_in_description(self):
        data=profile();data['802-11-wireless-security']['psk']='do-not-display'
        described=describe_profile(data,active=True,version=2,persistent=True)
        self.assertNotIn('do-not-display',str(described))
        for secret in ('','short','x'*64,'password\nvalue'):
            with self.assertRaises(ValueError):build_boot_wifi_update(profile(),secret)
        build_boot_wifi_update(profile(),'a'*64) # hexadecimal WPA2 PSK
        build_boot_wifi_update(profile(security='sae'),'a')

    def test_match_does_not_prove_saved_secret_or_boot(self):
        data=build_boot_wifi_update(profile(),'password123')
        described=describe_profile(data,active=True,version=2,persistent=True)
        self.assertEqual(described['configuration'],'configuration_matches')
        self.assertFalse(described['boot_verified'])
        self.assertNotIn('psk',described)

    def test_names_are_sanitized_and_versions_do_not_lose_uint64_precision(self):
        data=profile();data['connection']['id']='bad\nname'
        data['802-11-wireless']['ssid']=b'\xff\n'
        result=describe_profile(data,active=False,version=2**63+1,persistent=True)
        self.assertNotIn('\n',result['name'])
        self.assertEqual(result['version'],str(2**63+1))

    def test_fingerprint_excludes_password(self):
        a=profile();b=copy.deepcopy(a)
        a['802-11-wireless-security']['psk']='one'
        b['802-11-wireless-security']['psk']='two'
        self.assertEqual(settings_fingerprint(a),settings_fingerprint(b))

    def test_empty_dbus_container_signatures_survive_conversion(self):
        import dbus
        data=profile()
        data['future']={'empty':dbus.Array([],signature='u'),
                        'map':dbus.Dictionary({},signature='ss')}
        result=build_boot_wifi_update(data,'test-password')
        self.assertEqual(result['future']['empty'].signature,'u')
        self.assertEqual(result['future']['map'].signature,'ss')
