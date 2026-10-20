import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from monitorize.remote_login.engine import EngineOwner, RetrySchedule
from monitorize.platform.remote_login_identity import acquire_identity_lock, identity_paths


class EngineTests(unittest.TestCase):
    def test_retry_is_bounded_resettable_and_cancelable(self):
        retry=RetrySchedule()
        for delay in (2,5,15,60,60):
            self.assertEqual(retry.failed(100),100+delay)
        self.assertFalse(retry.due(159));self.assertTrue(retry.due(160))
        retry.healthy();self.assertEqual(retry.failed(200),202)
        retry.cancel();self.assertFalse(retry.due(10000))

    def test_engine_owns_lock_and_stop_waits_for_exit(self):
        with tempfile.TemporaryDirectory() as d:
            paths=identity_paths(Path(d));owner=EngineOwner(paths)
            owner.start([sys.executable,'-c','import time; time.sleep(60)'],{})
            try:
                with self.assertRaises(BlockingIOError):
                    with acquire_identity_lock(paths):pass
                self.assertTrue(owner.running)
            finally:owner.stop()
            self.assertFalse(owner.running)
            with acquire_identity_lock(paths):pass

    def test_failed_launch_releases_lock(self):
        with tempfile.TemporaryDirectory() as d:
            paths=identity_paths(Path(d));owner=EngineOwner(paths)
            with self.assertRaises(FileNotFoundError):owner.start(['/missing-monitorize-fixture'],{})
            with acquire_identity_lock(paths):pass

    def test_second_engine_cannot_start(self):
        with tempfile.TemporaryDirectory() as d:
            paths=identity_paths(Path(d));first=EngineOwner(paths);second=EngineOwner(paths)
            first.start([sys.executable,'-c','import time; time.sleep(60)'],{})
            try:
                with self.assertRaises(BlockingIOError):second.start([sys.executable,'-c','pass'],{})
                self.assertIsNone(second.process)
            finally:first.stop()

    def test_child_retains_lock_after_parent_descriptor_closes(self):
        with tempfile.TemporaryDirectory() as d:
            paths=identity_paths(Path(d));owner=EngineOwner(paths)
            owner.start([sys.executable,'-c','import time; time.sleep(60)'],{})
            try:
                owner._release_parent_lock()
                with self.assertRaises(BlockingIOError):
                    with acquire_identity_lock(paths):pass
            finally:owner.stop()
            with acquire_identity_lock(paths):pass
