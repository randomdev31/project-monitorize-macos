import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch, Mock
from monitorize.platform import remote_login_identity as identity


class FallbackGrantTests(unittest.TestCase):
    def test_grant_is_boot_session_and_account_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=SimpleNamespace(uid=os.getuid())
            path=Path(directory)/'grant.json'
            path.write_text(json.dumps(dict(uid=os.getuid(),session='s1',boot_id='boot1')))
            path.chmod(0o644)
            with patch.object(identity,'fallback_grant_path',return_value=path), patch.object(identity,'_fallback_context',return_value=('boot1','s1')):
                self.assertTrue(identity.desktop_fallback_allowed(settings,owner_uid=os.getuid()))
                with patch.object(identity,'_fallback_context',return_value=('boot2','s1')):
                    self.assertFalse(identity.desktop_fallback_allowed(settings,owner_uid=os.getuid()))
                path.chmod(0o666)
                self.assertFalse(identity.desktop_fallback_allowed(settings,owner_uid=os.getuid()))

    def test_missing_grant_does_not_probe_or_allow_enabled_identity(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(identity,'fallback_grant_path',return_value=Path(directory)/'missing'), patch.object(identity,'_fallback_context') as context:
            self.assertFalse(identity.desktop_fallback_allowed(SimpleNamespace(uid=os.getuid())))
            context.assert_not_called()


class FallbackHandoffTests(unittest.TestCase):
    def test_root_handoff_never_disables_boot_and_grants_only_after_release(self):
        import sys
        from monitorize.remote_login import enrollment
        helper=SimpleNamespace(_active_session=Mock(return_value=('s1',{})))
        package=SimpleNamespace(helper=helper)
        settings=SimpleNamespace(uid=1000)
        calls=[]
        command=Mock()
        def run(args):
            calls.append(('command',args))
            return 'masked' if args[1]=='show' else ''
        command.run.side_effect=run
        files=Mock();files.write.side_effect=lambda *args:calls.append(('grant',args))
        def release(uid,**kwargs):calls.append(('release',uid,kwargs))
        with patch.object(enrollment,'read_settings',return_value=settings), patch.dict(sys.modules,{'monitorize_vkms':package}), patch.object(enrollment,'Commands',return_value=command), patch.object(enrollment,'RootFiles',return_value=files), patch.object(enrollment,'remove_reserved',side_effect=release), patch.object(enrollment,'configure_disabled') as disable:
            result=enrollment.desktop_fallback(1000)
            self.assertTrue(result['success']);disable.assert_not_called()
        mutations=[item for item in calls if item[0]=='command' and item[1][1] in ('mask','stop')]
        self.assertEqual(mutations[0][1][1:3],['mask','--runtime'])
        self.assertEqual(mutations[1][1][1],'stop')
        self.assertEqual(calls[-2],('release',1000,{'release':True}))
        self.assertEqual(calls[-1][0],'grant')
        self.assertEqual(json.loads(calls[-1][1][1])['session'],'s1')

    def test_release_failure_never_publishes_fallback_permission(self):
        import sys
        from monitorize.remote_login import enrollment
        helper=SimpleNamespace(_active_session=lambda uid:('s1',{}))
        with patch.object(enrollment,'read_settings',return_value=SimpleNamespace(uid=1000)), patch.dict(sys.modules,{'monitorize_vkms':SimpleNamespace(helper=helper)}), patch.object(enrollment,'Commands',return_value=SimpleNamespace(run=lambda args:'masked')), patch.object(enrollment,'RootFiles') as files, patch.object(enrollment,'remove_reserved',side_effect=RuntimeError('capture still active')):
            with self.assertRaisesRegex(RuntimeError,'capture still active'):enrollment.desktop_fallback(1000)
            files.assert_not_called()

    def test_failed_handoff_restores_only_its_own_masks_and_running_coordinator(self):
        import sys
        from monitorize.remote_login import enrollment
        supervisor='monitorize-remote-login.service'
        boot='monitorize-remote-login-boot@1000.service'
        desktop='monitorize-remote-login-desktop@1000.service'
        masked={boot}
        calls=[]
        def run(args):
            calls.append(args)
            if args[1]=='show':
                if '--property=ActiveState' in args:return 'active' if args[2]==supervisor else 'inactive'
                return 'masked' if args[2] in masked else 'loaded'
            if args[1]=='mask':masked.update(args[3:])
            if args[1]=='unmask':masked.difference_update(args[3:])
            return ''
        helper=SimpleNamespace(_active_session=lambda uid:('s1',{}))
        with patch.object(enrollment,'read_settings',return_value=SimpleNamespace(uid=1000)), patch.dict(sys.modules,{'monitorize_vkms':SimpleNamespace(helper=helper)}), patch.object(enrollment,'Commands',return_value=SimpleNamespace(run=run)), patch.object(enrollment,'RootFiles') as files, patch.object(enrollment,'remove_reserved',side_effect=RuntimeError('capture still active')):
            with self.assertRaisesRegex(RuntimeError,'capture still active'):enrollment.desktop_fallback(1000)
            files.assert_not_called()
        self.assertEqual(masked,{boot})
        self.assertIn(['/usr/bin/systemctl','start',supervisor],calls)
