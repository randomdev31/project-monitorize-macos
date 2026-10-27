import os
from pathlib import Path
import tempfile
import unittest
from monitorize.remote_login.root_files import RootFiles


class RootFilesTests(unittest.TestCase):
    def test_rollback_restores_existing_bytes_and_removes_only_new_files(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);files=RootFiles(base,os.getuid())
            files.write('etc/monitorize/settings','old',0o600)
            files=RootFiles(base,os.getuid());files.write('etc/monitorize/settings','new')
            files.write('etc/monitorize/new','new')
            files.rollback()
            self.assertEqual((base/'etc/monitorize/settings').read_text(),'old')
            self.assertEqual((base/'etc/monitorize/settings').stat().st_mode & 0o777,0o600)
            self.assertFalse((base/'etc/monitorize/new').exists())

    def test_symlink_directory_file_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);files=RootFiles(base,os.getuid())
            (base/'etc').symlink_to(base,target_is_directory=True)
            with self.assertRaises(ValueError):files.write('etc/settings','bad')
            with self.assertRaises(ValueError):files.write('../settings','bad')
            with self.assertRaises(ValueError):files.write('/etc/settings','bad')
