import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from monitorize.remote_login.descriptors import DescriptorStore,read_descriptor


class DescriptorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'runtime'
        self.settings=SimpleNamespace(uid=os.getuid(),gid=os.getgid())
        self.adopt=Mock(return_value={'connector':'Virtual-4'})
        self.store=DescriptorStore(self.settings,lambda:'Virtual-4',self.adopt,root=self.root,owner_uid=os.getuid())
        self.caller={'uid':os.getuid(),'session':'s1'};self.token='a'*32

    def test_private_descriptor_is_atomic_and_bound_to_session(self):
        self.store.write(self.caller,self.token,{'capture':'kms','output_name':'Virtual-4'})
        path=self.root/str(os.getuid())/'desktop.json'
        result=read_descriptor(path,os.getuid(),owner_uid=os.getuid())
        self.assertEqual(result['session'],'s1');self.assertEqual(result['generation'],self.token)
        self.assertEqual(path.stat().st_mode & 0o777,0o640)
        self.assertEqual(list(path.parent.glob('.desktop.*')),[])

    def test_restrictive_service_umask_still_allows_selected_account_read(self):
        previous=os.umask(0o077)
        try:self.store.write(self.caller,self.token,{'capture':'kms','output_name':'Virtual-4'})
        finally:os.umask(previous)
        directory=self.root/str(os.getuid())
        self.assertEqual(directory.stat().st_mode & 0o777,0o750)
        self.assertEqual((directory/'desktop.json').stat().st_mode & 0o777,0o640)

    def test_invalid_capture_never_reaches_compositor(self):
        with self.assertRaises(ValueError):self.store.write(self.caller,self.token,{'capture':'kms','output_name':'eDP-1'})
        self.adopt.assert_not_called();self.assertFalse(self.root.exists())

    def test_symlink_runtime_directory_is_rejected(self):
        self.root.symlink_to(Path(self.temp.name),target_is_directory=True)
        with self.assertRaises(ValueError):self.store.write(self.caller,self.token,{'capture':'kms','output_name':'Virtual-4'})

    def test_wrong_output_after_adoption_is_not_published(self):
        self.adopt.return_value={'connector':'Virtual-5'}
        with self.assertRaises(RuntimeError):self.store.write(self.caller,self.token,{'capture':'kms','output_name':'Virtual-4'})
        self.assertFalse(self.root.exists())
