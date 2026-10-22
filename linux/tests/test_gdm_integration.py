import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from monitorize.remote_login.display_managers import manager_capabilities
from monitorize.remote_login.gdm_context import verify
from monitorize.remote_login.session_context import desktop_context


class GdmTests(unittest.TestCase):
    def test_distro_aliases_normalize_without_claiming_validation(self):
        for name in ('gdm.service','gdm3.service'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);link=root/'etc/systemd/system/display-manager.service'
                link.parent.mkdir(parents=True);link.symlink_to('/usr/lib/systemd/system/'+name)
                result=manager_capabilities(root)
                self.assertEqual(result['manager'],'gdm.service')
                self.assertTrue(result['supported']);self.assertFalse(result['validated'])
                self.assertIn('runtime',result['display_server'])
    def test_gnome_context_and_x11_guard(self):
        self.assertEqual(desktop_context({'XDG_SESSION_TYPE':'wayland','XDG_CURRENT_DESKTOP':'ubuntu:GNOME'}),{'desktop':'GNOME'})
        with self.assertRaises(ValueError):desktop_context({'XDG_SESSION_TYPE':'x11','XDG_CURRENT_DESKTOP':'GNOME'})

    def authenticate(self,*,cmd=b'gnome-shell\0--mode=gdm\0',owner=123,replacement=123):
        helper=Mock();helper._validate_session_socket.side_effect=[123,replacement]
        helper._session_connection_environment.return_value={'WAYLAND_DISPLAY':'wayland-0'}
        environment={'XDG_SESSION_TYPE':'wayland','DBUS_SESSION_BUS_ADDRESS':'unix:path=/wrong'}
        with patch('monitorize.remote_login.gdm_context.trusted_shell'), \
             patch('monitorize.remote_login.gdm_context.Path.read_bytes',return_value=cmd), \
             patch('monitorize.remote_login.gdm_context.Path.lstat',return_value=SimpleNamespace(st_mode=0o140600,st_uid=991)), \
             patch('monitorize.remote_login.gdm_context.pwd.getpwuid',return_value=SimpleNamespace(pw_name='gdm-test',pw_gid=991,pw_dir='/var/lib/gdm')), \
             patch('monitorize.remote_login.gdm_context.os.getgrouplist',return_value=[991]), \
             patch('monitorize.remote_login.gdm_context.subprocess.run',return_value=SimpleNamespace(stdout=str(owner))) as run:
            result=verify({'session':'c1','greeter_uid':991},'c1',environment,helper)
            self.assertEqual(run.call_args.kwargs['user'],991)
            self.assertEqual(run.call_args.kwargs['env']['DBUS_SESSION_BUS_ADDRESS'],'unix:path=/run/user/991/bus')
            return result
    def test_greeter_identity_and_demoted_bus_query(self):
        self.assertEqual(self.authenticate()['XDG_CURRENT_DESKTOP'],'GNOME')
    def test_desktop_shell_is_not_a_greeter(self):
        with self.assertRaisesRegex(PermissionError,'greeter mode'):self.authenticate(cmd=b'gnome-shell\0')
    def test_other_bus_owner_rejected(self):
        with self.assertRaisesRegex(PermissionError,'DisplayConfig'):self.authenticate(owner=456)
    def test_compositor_replacement_rejected(self):
        with self.assertRaisesRegex(PermissionError,'changed'):self.authenticate(replacement=456)
    def test_session_change_rejected_before_probe(self):
        helper=Mock()
        with self.assertRaises(PermissionError):verify({'session':'c1','greeter_uid':991},'c2',{},helper)
        helper._validate_session_socket.assert_not_called()


class ProbeTests(unittest.TestCase):
    def probe(self,sessions):
        from monitorize.remote_login.gdm_probe import collect
        def run(argv):
            if argv[1]=='list-sessions':return __import__('json').dumps([{'session':name} for name in sessions])
            return sessions[argv[2]]
        with tempfile.TemporaryDirectory() as directory:
            return collect(run=run,drm=Path(directory),capability={'manager':'gdm.service'})
    def test_zero_output_without_greeter_explicitly_blocked(self):
        result=self.probe({})
        self.assertEqual(result['status'],'BLOCKED')
        self.assertIn('bootstrap',result['errors'][0])
    def test_x11_greeter_rejected(self):
        result=self.probe({'c1':'Class=greeter\nActive=yes\nRemote=no\nSeat=seat0\nType=x11\nUser=991'})
        self.assertIn('X11',result['errors'][0])
    def test_wayland_presence_never_claims_streaming_validation(self):
        result=self.probe({'c1':'Class=greeter\nActive=yes\nRemote=no\nSeat=seat0\nType=wayland\nUser=991'})
        self.assertEqual(result['status'],'PROBE_REQUIRED')
        self.assertEqual(result['live_validation'],'REQUIRED')
    def test_active_user_blocks_greeter_probe(self):
        result=self.probe({'1':'Class=user\nActive=yes\nRemote=no\nSeat=seat0\nType=wayland\nUser=1000'})
        self.assertEqual(result['status'],'BLOCKED')
    def test_untrusted_shell_executable_is_rejected(self):
        from monitorize.remote_login.gdm_context import trusted_shell
        with patch('monitorize.remote_login.gdm_context.Path.resolve',return_value=Path('/tmp/gnome-shell')), \
             patch('monitorize.remote_login.daemon.require_installed',side_effect=ValueError('untrusted')):
            with self.assertRaises(ValueError):trusted_shell(Path('/proc/123/exe'))


class ActivationTests(unittest.TestCase):
    def test_gdm_activation_uses_verified_greeter_environment(self):
        from monitorize.remote_login.wayland_greeter import activate_greeter
        helper=Mock();check=Mock()
        env={'XDG_SESSION_TYPE':'wayland'}
        with patch('monitorize.remote_login.wayland_greeter.require_manager',return_value={'manager':'gdm.service','compositor':'gnome'}), \
             patch('monitorize.remote_login.gdm_context.verify',return_value={'WAYLAND_DISPLAY':'wayland-2','XDG_SESSION_TYPE':'wayland','XDG_CURRENT_DESKTOP':'GNOME'}) as verify_context:
            activate_greeter(SimpleNamespace(manager='gdm.service'),{'session':'c1','greeter_uid':991},'c1',env,
                {'name':'Virtual-1','card':'card2','connector_id':41},5,helper,check)
        self.assertEqual(verify_context.call_count,2)
        self.assertEqual(helper._run_worker.call_args.args[0],991)
        self.assertEqual(helper._run_worker.call_args.args[1]['XDG_CURRENT_DESKTOP'],'GNOME')
        self.assertEqual(helper._run_worker.call_args.args[2]['connector_id'],41)
        self.assertEqual(check.call_count,2)
