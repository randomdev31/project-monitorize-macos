"""Run on an Intel Mac. Creation requires a logged-in WindowServer session."""
import json
import os
import selectors
import subprocess
import sys
import unittest
from monitorize.macos.runtime import helper_path, parse_display_event


@unittest.skipUnless(sys.platform == 'darwin', 'Requires macOS CoreGraphics')
class NativeTests(unittest.TestCase):
    def test_lists_displays(self):
        result = subprocess.run([str(helper_path()), '--list'], capture_output=True, check=True, timeout=10)
        displays = json.loads(result.stdout)
        self.assertIsInstance(displays, list)
        for display in displays:
            self.assertIsInstance(display['id'], int)
            self.assertGreater(display['width'], 0)

    def test_rejects_invalid_arguments(self):
        for args in (['0', '1080', '60', '1'], ['1920', '1080', '60', '3']):
            result = subprocess.run([str(helper_path()), *args], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)

    @unittest.skipUnless(os.environ.get('MONITORIZE_TEST_VIRTUAL') == '1', 'Opt-in: requires desktop session')
    def test_display_lifetime_follows_owner(self):
        process = subprocess.Popen([str(helper_path()), '1920', '1080', '60', '1'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=10), 'Helper failed to report readiness')
                display_id = parse_display_event(process.stdout.readline())
            listed = json.loads(subprocess.check_output([str(helper_path()), '--list'], timeout=10))
            self.assertIn(display_id, [display['id'] for display in listed])
            process.stdin.close()
            self.assertEqual(process.wait(timeout=10), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()


if __name__ == '__main__':
    unittest.main()
