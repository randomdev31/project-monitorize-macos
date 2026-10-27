"""Offline source delivery checks: an old pinned host must fail before compilation."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'packaging/common/check-client-display-protocol.py'


class ClientProtocolDeliveryTest(unittest.TestCase):
    def run_check(self, source):
        return subprocess.run([sys.executable, str(CHECK), str(source)],
                              capture_output=True, text=True, timeout=5)

    def test_old_host_source_is_rejected_with_upgrade_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_check(directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('protocol v1', result.stderr)
        self.assertIn('pin', result.stderr)

    def test_marker_without_launch_and_stream_hooks_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'src').mkdir()
            (source / 'src/monitorize_control.h').write_text('MONITORIZE_CONTROL_PROTOCOL=1')
            result = self.run_check(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('nvhttp.cpp', result.stderr)

    def test_actual_paired_host_source_passes(self):
        result = self.run_check(ROOT / 'external/sunshine')
        self.assertEqual(result.returncode, 0, result.stderr)
