"""Keep Linux-only initialization off the macOS launch path."""
import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


class EntrypointTests(unittest.TestCase):
    def test_macos_dispatch_never_reads_linux_settings(self):
        from monitorize import __main__ as entrypoint
        app = types.ModuleType('monitorize.macos.app')
        app.main = Mock(return_value=17)
        with patch.object(sys, 'platform', 'darwin'), \
             patch.dict(sys.modules, {'monitorize.macos.app': app}), \
             patch.object(entrypoint, '_use_light_tray', side_effect=AssertionError('Linux path imported')):
            self.assertEqual(entrypoint.main(), 17)
        app.main.assert_called_once_with()

    def test_backend_can_import_without_linux_dbus_services(self):
        with patch.dict(sys.modules, {'dbus': None, 'gi': None}):
            runtime = importlib.import_module('monitorize.macos.runtime')
            self.assertEqual(runtime.DisplayMode().arguments(1), ['1920', '1080', '60', '1'])
