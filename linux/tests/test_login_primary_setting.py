import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from monitorize.remote_login import enrollment
from monitorize.remote_login.root_files import RootFiles

class PrimarySettingTests(unittest.TestCase):
    def test_saves_only_preference_without_starting_services_or_disabling_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            files=RootFiles(Path(directory),owner_uid=os.getuid())
            original=dict(schema_version=1,uid=1000,enabled=True,manager='gdm.service',encoder='nvenc',adapter='/dev/dri/renderD128',retained='keep')
            files.write('etc/monitorize/remote-login.json',json.dumps(original))
            settings=SimpleNamespace(uid=1000,enabled=True,manager='gdm.service')
            with patch.object(enrollment,'read_settings',return_value=settings),patch.object(enrollment,'RootFiles',return_value=files),patch.object(enrollment,'Commands') as commands:
                result=enrollment.configure_login_virtual_display(1000,True)
                self.assertTrue(result['success']);self.assertTrue(result['reboot_required'])
                saved=json.loads((Path(directory)/'etc/monitorize/remote-login.json').read_text())
                self.assertEqual(saved,dict(original,create_login_virtual_display=True))
                commands.assert_not_called()
                enrollment.configure_login_virtual_display(1000,False)
                self.assertFalse(json.loads((Path(directory)/'etc/monitorize/remote-login.json').read_text())['create_login_virtual_display'])

    def test_rejects_other_accounts_disabled_boot_unsupported_manager_and_untyped_flag(self):
        for uid,enabled,manager,flag in [(1001,True,'gdm.service',True),(1000,False,'gdm.service',True),(1000,True,'gdm.service',1)]:
            with self.subTest(uid=uid,enabled=enabled,manager=manager,flag=flag),patch.object(enrollment,'read_settings',return_value=SimpleNamespace(uid=1000,enabled=enabled,manager=manager)),patch.object(enrollment,'RootFiles') as files:
                with self.assertRaises((PermissionError,ValueError)):enrollment.configure_login_virtual_display(uid,flag)
                files.assert_not_called()

class PrimarySettingClientTests(unittest.TestCase):
    def test_fixed_privileged_actions_and_safe_cancellation(self):
        from monitorize.platform import system_setup
        status=dict(available=True,enabled=True,manager='gdm.service')
        with patch.object(system_setup,'remote_login_setup_status',return_value=status),patch.object(system_setup,'login_display_policy_available',return_value=True),patch.object(system_setup.shutil,'which',return_value='/usr/bin/pkexec'),patch.object(system_setup.subprocess,'run') as run:
            run.return_value=SimpleNamespace(returncode=0,stdout='{"success":true,"reboot_required":true}',stderr='')
            self.assertTrue(system_setup.apply_login_virtual_display(True)['success'])
            self.assertEqual(run.call_args.args[0],['/usr/bin/pkexec',str(system_setup.HELPER),'--remote-login','login-virtual-on'])
            self.assertTrue(system_setup.apply_login_virtual_display(False)['success'])
            self.assertEqual(run.call_args.args[0][-1],'login-virtual-off')
            run.return_value=SimpleNamespace(returncode=1,stdout='',stderr='Cancelled')
            self.assertFalse(system_setup.apply_login_virtual_display(True)['success'])
    def test_disabled_boot_does_not_request_admin_authorization(self):
        from monitorize.platform import system_setup
        with patch.object(system_setup,'remote_login_setup_status',return_value=dict(available=True,enabled=False)),patch.object(system_setup.subprocess,'run') as run:
            self.assertFalse(system_setup.apply_login_virtual_display(True)['success'])
            run.assert_not_called()
