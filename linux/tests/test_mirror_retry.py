import unittest
from unittest.mock import Mock
from monitorize.desktop.mirror_retry import MirrorRetry

class Timer:
 def __init__(self):self.callback=None;self.delay=None
 def schedule(self,delay,callback):self.delay=delay;self.callback=callback
 def fire(self):callback=self.callback;self.callback=None;callback()

class MirrorRetryTests(unittest.TestCase):
 def setUp(self):
  self.timer=Timer();self.launch=Mock();self.status=Mock();self.busy=False
  self.now=0
  self.retry=MirrorRetry(self.launch,self.status,lambda:self.busy,schedule=self.timer.schedule,clock=lambda:self.now)
  self.config={'display_type':'Mirror','mirror_output':'eDP-1'}
 def test_backoff_and_verified_health_reset(self):
  self.retry.arm(self.config,True)
  for delay in (2,5,15,60,60):
   self.retry.failed('crashed');self.assertEqual(self.timer.delay,delay*1000);self.timer.fire()
   self.assertEqual(self.launch.call_args.args[0]['mirror_output'],'eDP-1')
  self.retry.healthy();self.now=60;self.retry.healthy()
  self.retry.failed('again');self.assertEqual(self.timer.delay,2000)
 def test_stop_invalidates_already_queued_callback(self):
  self.retry.arm(self.config,True);self.retry.failed('crashed');callback=self.timer.callback
  self.retry.cancel();callback();self.launch.assert_not_called();self.assertFalse(self.retry.pending)
 def test_old_engine_must_exit_before_successor(self):
  self.retry.arm(self.config,True);self.retry.failed('crashed');self.busy=True;self.timer.fire()
  self.launch.assert_not_called();self.assertTrue(self.retry.pending)
  self.busy=False;self.timer.fire();self.launch.assert_called_once()
 def test_disabled_and_extend_do_not_retry(self):
  for config,enabled in ((self.config,False),({'display_type':'Extend'},True)):
   self.retry.arm(config,enabled);self.retry.failed('crashed');self.assertFalse(self.retry.pending)
 def test_duplicate_failure_does_not_schedule_two_successors(self):
  self.retry.arm(self.config,True);self.retry.failed('a');callback=self.timer.callback
  self.retry.failed('b');self.assertIs(callback,self.timer.callback)
  self.timer.fire();self.launch.assert_called_once()
 def test_retry_arm_preserves_attempt_count_and_original_output(self):
  self.retry.arm(self.config,True)
  def launch(config):self.retry.arm(config,True)
  self.launch.side_effect=launch
  self.retry.failed('a');self.timer.fire();self.retry.failed('b');self.assertEqual(self.timer.delay,5000)
 def test_explicit_cancel_is_honored_inside_retry_launch(self):
  self.retry.arm(self.config,True)
  self.launch.side_effect=lambda config:self.retry.cancel()
  self.retry.failed('a');self.timer.fire()
  self.assertIsNone(self.retry.intent);self.assertFalse(self.retry.pending)
 def test_launch_exception_keeps_bounded_retry_and_reports_error(self):
  self.retry.arm(self.config,True);self.launch.side_effect=OSError('startup failed')
  self.retry.failed('a');self.timer.fire()
  self.assertTrue(self.retry.pending);self.assertFalse(self.retry.restarting)
  self.assertEqual(self.timer.delay,5000)
