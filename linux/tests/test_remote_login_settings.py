import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from monitorize.remote_login.settings import read_settings, validate_descriptor


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'settings.json'
        self.values=dict(schema_version=1,enabled=True,uid=1000,gid=1000,username='account',home='/home/account',
                         profile='/home/account/.config/monitorize/sunshine-1',manager='plasmalogin.service',encoder='software',adapter='')
        self.account=SimpleNamespace(pw_uid=1000,pw_gid=1000,pw_name='account',pw_dir='/home/account')
    def load(self):
        self.path.write_text(json.dumps(self.values));self.path.chmod(0o600)
        return read_settings(self.path,owner_uid=os.getuid(),account_lookup=lambda uid:self.account)

    def test_account_binding_and_fixed_paths(self):
        settings=self.load()
        self.assertEqual(settings.directory,Path('/var/lib/monitorize/remote-login/1000'))
        self.assertEqual(settings.runtime,Path('/run/monitorize-remote-login/1000'))

    def test_uid_reuse_and_unsupported_manager_rejected(self):
        for field,value in (('username','other'),('home','/home/other'),('uid',True),('gid',123),('manager','gdm.service')):
            original=self.values[field];self.values[field]=value
            with self.assertRaises(ValueError):self.load()
            self.values[field]=original

    def test_unsafe_settings_file_rejected(self):
        self.load();self.path.chmod(0o666)
        with self.assertRaises(ValueError):read_settings(self.path,owner_uid=os.getuid(),account_lookup=lambda uid:self.account)
        self.path.unlink();self.path.symlink_to('/missing')
        with self.assertRaises(ValueError):read_settings(self.path,owner_uid=os.getuid(),account_lookup=lambda uid:self.account)

    def test_descriptor_has_only_bounded_typed_capture_values(self):
        settings=self.load()
        descriptor=validate_descriptor({'capture':'kms','output_name':'Virtual-4'},settings,'Virtual-4')
        self.assertEqual(descriptor['capture'],'kms')
        for descriptor in ({'capture':'portal','output_name':'Virtual-4'},
                           {'capture':'kms','output_name':'eDP-1'},
                           {'capture':'kms','output_name':'Virtual-4','command':'evil'},
                           {'capture':'kwin','output_name':'Virtual-4','pipewire_node':True}):
            with self.assertRaises(ValueError):validate_descriptor(descriptor,settings,'Virtual-4')

    def test_kwin_node_and_session_environment_are_constrained(self):
        settings=self.load()
        result=validate_descriptor({'capture':'kwin','output_name':'Virtual-4','pipewire_node':42,'wayland_display':'wayland-0'},settings,'Virtual-4')
        self.assertEqual(result['pipewire_node'],42)
        for name in ('../../other','wayland-0\nLD_PRELOAD=evil'):
            with self.assertRaises(ValueError):validate_descriptor({'capture':'kms','output_name':'Virtual-4','wayland_display':name},settings,'Virtual-4')



    def test_retired_experimental_enrollment_restores_original_encoder(self):
        self.values.update(transition_mode='seamless-experimental', encoder='software',
                           reconnect_encoder='vaapi', reconnect_adapter='/dev/dri/renderD128')
        result=self.load()
        self.assertEqual((result.encoder,result.adapter),('vaapi','/dev/dri/renderD128'))
        self.assertFalse(hasattr(result,'transition_mode'))
        self.values['reconnect_adapter']='../../unsafe'
        with self.assertRaises(ValueError):self.load()
