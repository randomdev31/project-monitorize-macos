"""Boot-to-normal switch orchestration; no installed services or real display I/O."""
import contextlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from monitorize.remote_login import enrollment

class DisableSwitchTests(unittest.TestCase):
 def run_disable(self,failure=None):
  settings=SimpleNamespace(uid=1000,gid=1000,username='u',home='/home/u',profile='/home/u/profile',encoder='software',adapter='',directory='/tmp/fake-identity')
  with patch.object(enrollment,'read_settings',return_value=settings),patch.object(enrollment,'Commands') as commands,patch.object(enrollment,'RootFiles'),patch.object(enrollment,'configure_disabled') as configure,patch.object(enrollment,'restore_linger'),patch.object(enrollment,'identity_paths'),patch.object(enrollment,'acquire_identity_lock',return_value=contextlib.nullcontext()),patch.object(enrollment,'remove_reserved',side_effect=failure) as release:
   result=enrollment.disable(1000)
   self.assertFalse(configure.call_args.args[0]['enabled']);release.assert_called_once_with(1000)
   self.assertIn('monitorize-remote-login-desktop@1000.service',commands.return_value.run.call_args.args[0])
   return result
 def test_success_allows_normal_streaming_without_reboot(self):
  result=self.run_disable();self.assertTrue(result['success']);self.assertFalse(result['reboot_required'])
 def test_release_failure_reports_partial_state_and_retry(self):
  result=self.run_disable(RuntimeError('still busy'))
  self.assertFalse(result['success']);self.assertTrue(result['cleanup_pending']);self.assertIn('still busy',result['message'])
