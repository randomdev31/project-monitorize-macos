import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class Commands:
    def __init__(self):self.events=[];self.fail=False
    def capabilities(self,path):return 'cap_sys_admin=p' if path.exists() else ''
    def set_capabilities(self,path,value):self.events.append(('caps',value))
    def reload(self):
        self.events.append(('reload',))
        if self.fail:self.fail=False;raise RuntimeError('fixture')

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('deploy',ROOT/'scripts/install-remote-login-assets.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'root';self.root.mkdir()
        self.stage=self.base/'stage';self.stage.mkdir();self.commands=Commands()
        self.installer=self.module.Installer(self.root,owner_uid=os.getuid(),commands=self.commands)
    def file(self,relative,data):
        path=self.stage/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
    def test_install_and_rollback_restore_original_files_and_remove_only_new_files(self):
        relative='usr/lib/monitorize-remote-login/monitorize/remote_login/service.py'
        target=self.root/relative;target.parent.mkdir(parents=True);target.write_bytes(b'old');target.chmod(0o600)
        self.file(relative,b'new');self.file('usr/libexec/monitorize/sunshine',b'engine')
        backup=self.installer.install(self.stage)
        self.assertEqual(target.read_bytes(),b'new')
        self.assertEqual(target.stat().st_mode & 0o777,0o644)
        self.installer.rollback(backup)
        self.assertEqual(target.read_bytes(),b'old');self.assertEqual(target.stat().st_mode & 0o777,0o600)
        self.assertFalse((self.root/'usr/libexec/monitorize/sunshine').exists())
        self.assertFalse((self.root/'etc/monitorize/remote-login.json').exists())
    def test_failed_reload_rolls_back_replacements(self):
        target=self.root/'usr/libexec/monitorize/sunshine';target.parent.mkdir(parents=True);target.write_bytes(b'old')
        self.file('usr/libexec/monitorize/sunshine',b'new');self.commands.fail=True
        with self.assertRaisesRegex(RuntimeError,'rolled back'):
            self.installer.install(self.stage)
        self.assertEqual(target.read_bytes(),b'old')
    def test_unknown_path_and_symlink_are_rejected_before_mutation(self):
        self.file('etc/passwd',b'bad')
        with self.assertRaises(ValueError):self.installer.install(self.stage)
        self.assertFalse((self.root/'etc').exists())
        (self.stage/'etc/passwd').unlink()
        source=self.file('usr/libexec/monitorize/sunshine',b'new');source.unlink();source.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):self.installer.install(self.stage)
    def test_destination_symlink_is_rejected(self):
        self.file('usr/libexec/monitorize/sunshine',b'new')
        (self.root/'usr').symlink_to(self.base/'elsewhere')
        with self.assertRaises(ValueError):self.installer.install(self.stage)
    def test_rollback_rejects_untrusted_backup(self):
        backup=self.base/'untrusted';backup.mkdir()
        with self.assertRaises(ValueError):self.installer.rollback(backup)

    def test_retired_engine_assets_are_removed_and_recoverable(self):
        retired=self.root/'usr/lib/systemd/system/monitorize-remote-login-persistent@.service'
        retired.parent.mkdir(parents=True);retired.write_bytes(b'old experimental unit')
        unrelated=retired.parent/'other.service';unrelated.write_bytes(b'keep')
        self.file('usr/libexec/monitorize/sunshine',b'new')
        backup=self.installer.install(self.stage)
        self.assertFalse(retired.exists());self.assertEqual(unrelated.read_bytes(),b'keep')
        self.installer.rollback(backup)
        self.assertEqual(retired.read_bytes(),b'old experimental unit')

    def test_retired_unit_cannot_be_reintroduced_by_staging(self):
        self.file('usr/lib/systemd/system/monitorize-remote-login-persistent@.service',b'old')
        with self.assertRaises(ValueError):self.installer.install(self.stage)
