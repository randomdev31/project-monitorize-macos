import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from monitorize.remote_login.kwin_context import verify,trusted_kwin
from monitorize.remote_login.wayland_greeter import greeter_environment,activate_greeter


class KwinGreeterTests(unittest.TestCase):
    def setUp(self):
        self.context=dict(session='c1',greeter_uid=971,session_type='wayland')
        self.helper=Mock()
        self.helper._active_session.side_effect=RuntimeError('No desktop label/session-scoped compositor')

    def check_context(self,*,owners=('123','123'),process_uid=971,paths=('wayland-0',),peers=(123,123)):
        with patch('monitorize.remote_login.kwin_context.Path.lstat',autospec=True,
                side_effect=lambda path:SimpleNamespace(st_mode=0o40700 if str(path)=='/run/user/971' else 0o140600,st_uid=971)), \
             patch('monitorize.remote_login.kwin_context.Path.stat',return_value=SimpleNamespace(st_uid=process_uid)), \
             patch('monitorize.remote_login.kwin_context.Path.glob',return_value=[Path('/run/user/971')/p for p in paths]), \
             patch('monitorize.remote_login.kwin_context.pwd.getpwuid',return_value=SimpleNamespace(pw_name='greeter',pw_gid=971,pw_dir='/var/lib/plasmalogin')), \
             patch('monitorize.remote_login.kwin_context.os.getgrouplist',return_value=[971]), \
             patch('monitorize.remote_login.kwin_context.trusted_kwin') as trusted, \
             patch('monitorize.remote_login.gdm_context.socket_owner',side_effect=peers), \
             patch('monitorize.remote_login.kwin_context.subprocess.run',side_effect=[SimpleNamespace(stdout=o) for o in owners]) as run:
            result=verify(self.context,'c1',{'XDG_SESSION_TYPE':'wayland','DBUS_SESSION_BUS_ADDRESS':'unix:path=/untrusted'},self.helper)
            trusted.assert_called_once_with(Path('/proc/123/exe'))
            self.assertEqual(run.call_args.kwargs['user'],971)
            self.assertEqual(run.call_args.kwargs['group'],971)
            self.assertEqual(run.call_args.kwargs['env']['DBUS_SESSION_BUS_ADDRESS'],'unix:path=/run/user/971/bus')
            return result

    def test_empty_desktop_label_and_user_service_compositor_are_supported(self):
        result=self.check_context()
        self.assertEqual(result['WAYLAND_DISPLAY'],'wayland-0')
        self.assertEqual(result['XDG_CURRENT_DESKTOP'],'KDE')
        self.helper._active_session.assert_not_called()

    def test_socket_and_bus_must_have_same_owner(self):
        with self.assertRaisesRegex(PermissionError,'exactly one'):self.check_context(peers=(456,))

    def test_ambiguous_sockets_refused(self):
        with self.assertRaisesRegex(PermissionError,'exactly one'):
            self.check_context(paths=('wayland-0','wayland-1'),peers=(123,123))

    def test_compositor_replacement_refused(self):
        with self.assertRaisesRegex(PermissionError,'changed'):self.check_context(owners=('123','456'))
        with self.assertRaisesRegex(PermissionError,'changed'):self.check_context(peers=(123,456))

    def test_other_uid_refused(self):
        with self.assertRaisesRegex(PermissionError,'another account'):self.check_context(process_uid=1000)

    def test_untrusted_owner_responses_refused(self):
        for owner in ('true','0','-1','"123"','not-json','1'*129):
            with self.assertRaises((ValueError,PermissionError)):self.check_context(owners=(owner,))

    def test_actual_session_type_required_without_generic_discovery(self):
        settings=SimpleNamespace(manager='plasmalogin.service')
        with patch('monitorize.remote_login.wayland_greeter.require_manager',return_value={'manager':settings.manager,'compositor':'kde'}):
            session,environment=greeter_environment(settings,self.context,self.helper)
            self.assertEqual((session,environment),('c1',{'XDG_SESSION_TYPE':'wayland'}))
            for session_type in ('x11',None):
                with self.assertRaisesRegex(RuntimeError,'Wayland'):
                    greeter_environment(settings,dict(self.context,session_type=session_type),self.helper)
        self.helper._active_session.assert_not_called()

    def test_session_change_refused_before_bus_query(self):
        with self.assertRaises(PermissionError):verify(self.context,'other',{'XDG_SESSION_TYPE':'wayland'},self.helper)

    def test_executable_must_be_kwin_and_root_trusted(self):
        with patch('monitorize.remote_login.kwin_context.Path.resolve',return_value=Path('/usr/bin/Hyprland')):
            with self.assertRaises(PermissionError):trusted_kwin(Path('/proc/123/exe'))
        with patch('monitorize.remote_login.kwin_context.Path.resolve',return_value=Path('/tmp/kwin_wayland')), \
             patch('monitorize.remote_login.daemon.require_installed',side_effect=ValueError('untrusted')):
            with self.assertRaises(ValueError):trusted_kwin(Path('/proc/123/exe'))

    def test_activation_uses_verified_environment_and_rechecks(self):
        settings=SimpleNamespace(manager='plasmalogin.service');check=Mock()
        verified=dict(XDG_SESSION_TYPE='wayland',WAYLAND_DISPLAY='wayland-1',XDG_CURRENT_DESKTOP='KDE')
        with patch('monitorize.remote_login.wayland_greeter.require_manager',return_value={'manager':settings.manager,'compositor':'kde'}), \
             patch('monitorize.remote_login.kwin_context.verify',return_value=verified) as verification:
            activate_greeter(settings,self.context,'c1',{'XDG_SESSION_TYPE':'wayland'},
                dict(name='Virtual-1',card='card2',connector_id=49),5,self.helper,check)
        self.assertEqual(verification.call_count,2)
        self.assertEqual(self.helper._run_worker.call_args.args[0],971)
        self.assertEqual(self.helper._run_worker.call_args.args[1]['WAYLAND_DISPLAY'],'wayland-1')
        self.assertEqual(check.call_count,2)
