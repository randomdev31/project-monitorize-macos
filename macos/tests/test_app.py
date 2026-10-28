"""Qt lifecycle integration against a subprocess fixture, not a macOS emulator."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

if sys.platform != 'darwin':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from PyQt6.QtCore import QProcess, QSettings
    from PyQt6.QtWidgets import QApplication
    from monitorize.macos.app import Window
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, 'Install PyQt6 for frontend integration checks')
class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(self.root))
        self.helper = self.root / 'display-helper'
        self.helper.write_text(f'#!{sys.executable}\n' + '''import json, sys
if '--list' in sys.argv:
    print(json.dumps([{'id': 7, 'width': 1920, 'height': 1080}]), flush=True)
else:
    print(json.dumps({'id': 42}), flush=True)
    sys.stdin.read()
''')
        self.helper.chmod(0o700)
        self.patch = patch('monitorize.macos.app.helper_path', return_value=self.helper)
        self.patch.start()
        self.window = Window()
        self.wait_until(lambda: self.window.panels[0].source.count() == 2)

    def tearDown(self):
        self.window.close()
        self.patch.stop()
        self.directory.cleanup()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate(), 'Frontend did not reach expected state')

    def test_virtual_display_readiness_and_shutdown(self):
        panel = self.window.panels[0]
        panel.start()
        self.wait_until(lambda: panel.display_id == 42)
        process = panel.helper
        self.assertTrue(panel.stream_button.isEnabled())
        self.assertFalse(panel.width.isEnabled())
        panel.stop()
        self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)
        self.assertIsNone(panel.display_id)
        self.assertTrue(panel.start_button.isEnabled())

    def test_physical_display_does_not_create_helper(self):
        panel = self.window.panels[0]
        panel.source.setCurrentIndex(1)
        panel.start()
        self.assertEqual(panel.display_id, 7)
        self.assertIsNone(panel.helper)
        panel.stop()
        self.assertIsNone(panel.display_id)

    def test_helper_exit_clears_display_and_stream(self):
        panel = self.window.panels[0]
        panel.start()
        self.wait_until(lambda: panel.display_id == 42)
        panel.helper.kill()
        self.wait_until(lambda: panel.helper is None)
        self.assertIsNone(panel.display_id)
        self.assertIsNone(panel.stream)
        self.assertFalse(panel.stream_button.isEnabled())

    def test_sunshine_launch_and_window_close(self):
        panel = self.window.panels[0]
        panel.start()
        self.wait_until(lambda: panel.display_id == 42)
        executable = self.root / 'sunshine'
        executable.write_text(f'#!{sys.executable}\nimport sys\nsys.stdin.read()\n')
        executable.chmod(0o700)
        with patch.dict(os.environ, {'MONITORIZE_SUNSHINE': str(executable)}), \
             patch('monitorize.macos.runtime.state_root', return_value=self.root / 'profiles'):
            panel.start_stream()
            self.wait_until(lambda: panel.stream.state() == QProcess.ProcessState.Running)
        stream, helper = panel.stream, panel.helper
        self.window.close()
        self.assertEqual(stream.state(), QProcess.ProcessState.NotRunning)
        self.assertEqual(helper.state(), QProcess.ProcessState.NotRunning)
        self.assertIn('output_name = 42', (self.root / 'profiles/sunshine-1/sunshine.conf').read_text())


if __name__ == '__main__':
    unittest.main()
