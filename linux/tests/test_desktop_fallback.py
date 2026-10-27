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

    def test_versioned_recovery_metadata_preserves_scoped_manual_permission(self):
        from monitorize.platform.sunshine_service import _enrolled_manual_identity
        from monitorize.remote_login import settings as policy
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'grant.json';config=root/'config.json';config.write_text('{}')
            uid=os.getuid();settings=SimpleNamespace(uid=uid,enabled=True,directory=root)
            names=['monitorize-remote-login.service',f'monitorize-remote-login-boot@{uid}.service',
                   f'monitorize-remote-login-desktop@{uid}.service']
            grant=dict(schema_version=1,uid=uid,session='s1',boot_id='boot1',
                       unit_enablement={name:name==names[0] for name in names},owned_runtime_masks=names)
            path.write_text(json.dumps(grant));path.chmod(0o644)
            with patch.object(identity,'fallback_grant_path',return_value=path), \
                 patch.object(identity,'_fallback_context',return_value=('boot1','s1')), \
                 patch.object(policy,'SETTINGS',config),patch.object(policy,'read_settings',return_value=settings), \
                 patch.object(identity.os,'getuid',return_value=uid):
                # Use a fixture-owned grant while exercising the real manual identity guard.
                from functools import partial
                validator=partial(identity.desktop_fallback_allowed,owner_uid=uid)
                with patch.object(identity,'desktop_fallback_allowed',side_effect=validator):
                    self.assertEqual(_enrolled_manual_identity(1),identity.identity_paths(root))
                    with patch.object(identity,'_fallback_context',return_value=('boot1','different-login')):
                        with self.assertRaisesRegex(RuntimeError,'Remote login owns'):_enrolled_manual_identity(1)
                for changes in ({'schema_version':True},{'schema_version':2},{'uid':True},
                                {'owned_runtime_masks':['display-manager.service']},
                                {'unit_enablement':{names[0]:True}}, {'extra':'unexpected'}):
                    with self.subTest(changes=changes):
                        path.write_text(json.dumps(dict(grant,**changes)))
                        self.assertFalse(identity.desktop_fallback_allowed(settings,owner_uid=uid))



class FallbackHandoffTests(unittest.TestCase):
    def test_root_handoff_never_disables_boot_and_grants_only_after_release(self):
        import sys
        from monitorize.remote_login import enrollment
        helper=SimpleNamespace(_active_session=Mock(return_value=('s1',{})))
        package=SimpleNamespace(helper=helper)
        settings=SimpleNamespace(uid=1000)
        calls=[]
        command=Mock()
        command.enabled.side_effect=lambda name:name=='monitorize-remote-login.service'
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
        grant=json.loads(calls[-1][1][1])
        self.assertEqual(grant['session'],'s1')
        self.assertTrue(grant['unit_enablement']['monitorize-remote-login.service'])
        self.assertFalse(grant['unit_enablement']['monitorize-remote-login-desktop@1000.service'])
        # Feed the real privileged writer's result into the app-side reader.
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'grant.json';path.write_text(json.dumps(grant));path.chmod(0o644)
            with patch.object(identity,'fallback_grant_path',return_value=path), \
                 patch.object(identity,'_fallback_context',return_value=(grant['boot_id'],'s1')):
                self.assertTrue(identity.desktop_fallback_allowed(settings,owner_uid=os.getuid()))


    def test_release_failure_never_publishes_fallback_permission(self):
        import sys
        from monitorize.remote_login import enrollment
        helper=SimpleNamespace(_active_session=lambda uid:('s1',{}))
        with patch.object(enrollment,'read_settings',return_value=SimpleNamespace(uid=1000)), patch.dict(sys.modules,{'monitorize_vkms':SimpleNamespace(helper=helper)}), patch.object(enrollment,'Commands',return_value=SimpleNamespace(run=lambda args:'masked',enabled=lambda name:False)), patch.object(enrollment,'RootFiles') as files, patch.object(enrollment,'remove_reserved',side_effect=RuntimeError('capture still active')):
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
        with patch.object(enrollment,'read_settings',return_value=SimpleNamespace(uid=1000)), patch.dict(sys.modules,{'monitorize_vkms':SimpleNamespace(helper=helper)}), patch.object(enrollment,'Commands',return_value=SimpleNamespace(run=run,enabled=lambda name:name==supervisor)), patch.object(enrollment,'RootFiles') as files, patch.object(enrollment,'remove_reserved',side_effect=RuntimeError('capture still active')):
            with self.assertRaisesRegex(RuntimeError,'capture still active'):enrollment.desktop_fallback(1000)
            files.assert_not_called()
        self.assertEqual(masked,{boot})
        self.assertIn(['/usr/bin/systemctl','start',supervisor],calls)
