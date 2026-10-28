import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from monitorize.macos.runtime import (DisplayMode, base_port, parse_display_event,
    prepare_sunshine, sunshine_binary)


class RuntimeTests(unittest.TestCase):
    def test_mode_limits_and_argument_safety(self):
        self.assertEqual(DisplayMode(2560, 1440, 60).arguments(2), ['2560', '1440', '60', '2'])
        for args in ((0, 1080, 60), (1920, 9000, 60), (1920, 1080, 0), (True, 1080, 60)):
            with self.assertRaises(ValueError):
                DisplayMode(*args)
        for slot in (0, 3, True, '1'):
            with self.assertRaises(ValueError):
                DisplayMode().arguments(slot)

    def test_helper_protocol_rejects_missing_or_invalid_ids(self):
        self.assertEqual(parse_display_event(b'{"id": 42}\n'), 42)
        for line in ('{}', '[]', '{"id":true}', '{"id":0}', '{"id":"42"}', '{"id":4294967296}', 'bad'):
            with self.assertRaises(ValueError):
                parse_display_event(line)

    def test_profiles_are_isolated_and_preserve_user_preferences(self):
        with tempfile.TemporaryDirectory(prefix='monitorize space ') as directory:
            root = Path(directory)
            unrelated = root / 'sunshine.conf'
            unrelated.write_text('personal config')
            first = prepare_sunshine(1, 42, root)
            second = prepare_sunshine(2, 81, root)
            self.assertNotEqual(first.parent, second.parent)
            self.assertIn('port = 47989\n', first.read_text())
            self.assertIn('port = 49089\n', second.read_text())
            self.assertIn('output_name = 42\n', first.read_text())
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(first.parent.stat().st_mode), 0o700)
            for key in ('credentials_file', 'file_state', 'pkey', 'cert', 'apps', 'log_path'):
                self.assertIn(f'{key} = {first.parent}/', first.read_text())
            apps = first.parent / 'apps.json'
            self.assertEqual(json.loads(apps.read_text())['apps'][0]['name'], 'Desktop')
            apps.write_text('{"apps": [{"name": "Custom"}]}')
            first.write_text(first.read_text() + 'encoder = software\nbitrate = 20000\n')
            prepare_sunshine(1, 99, root)
            result = first.read_text()
            self.assertEqual(result.count('output_name ='), 1)
            self.assertIn('output_name = 99\n', result)
            self.assertIn('encoder = software\nbitrate = 20000\n', result)
            self.assertIn('Custom', apps.read_text())
            self.assertEqual(unrelated.read_text(), 'personal config')

    def test_invalid_target_does_not_create_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            for target in ('1\nport=42', 0, -1, True):
                with self.assertRaises(ValueError):
                    prepare_sunshine(1, target, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_sunshine_override_requires_an_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'sunshine'
            executable.write_text('#!/bin/sh\nexit 0\n')
            with patch.dict(os.environ, {'MONITORIZE_SUNSHINE': str(executable)}):
                with self.assertRaises(RuntimeError):
                    sunshine_binary()
                executable.chmod(0o700)
                self.assertEqual(sunshine_binary(), str(executable.resolve()))
        self.assertEqual(base_port(2) + 1, 49090)


if __name__ == '__main__':
    unittest.main()
