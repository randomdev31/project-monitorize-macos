import unittest
from unittest.mock import Mock
from monitorize.remote_login.idle import IdleDisplay

class IdleTests(unittest.TestCase):
 def setUp(self):
  self.now=0;self.prepare=Mock(return_value={'output_name':'Virtual-1'});self.remove=Mock()
  self.display=IdleDisplay(self.prepare,self.remove,clock=lambda:self.now)
 def event(self,operation,client='c1',request='r1'):
  return self.display.request({'operation':operation,'client_id':client,'request_id':request})
 def test_last_disconnect_expires_at_twenty_and_recreates(self):
  self.event('prepare');self.event('stream_started');self.event('stream_stopped')
  self.now=19;self.assertFalse(self.display.due())
  self.now=20;self.assertTrue(self.display.due())
  self.display.expire();self.remove.assert_called_once()
  self.event('prepare',request='r2');self.assertEqual(self.prepare.call_count,2)
 def test_reconnect_cancels_grace_and_duplicate_disconnect_does_not_extend_it(self):
  self.event('prepare');self.event('stream_started');self.event('stream_stopped')
  self.now=19;self.event('stream_stopped');self.now=20;self.assertTrue(self.display.due())
  self.event('prepare',request='r2');self.assertFalse(self.display.due())
 def test_second_client_prevents_removal(self):
  for c,r in (('c1','r1'),('c2','r2')):self.event('prepare',c,r);self.event('stream_started',c,r)
  self.event('stream_stopped');self.now=100;self.assertFalse(self.display.due())
  self.event('stream_stopped','c2','r2');self.now=120;self.assertTrue(self.display.due())
 def test_failed_removal_retains_display_and_actionable_error(self):
  self.event('prepare');self.event('abort');self.now=20;self.remove.side_effect=RuntimeError('busy')
  with self.assertRaises(RuntimeError):self.display.expire()
  self.assertIsNotNone(self.display.target)
 def test_stale_stream_event_is_rejected(self):
  with self.assertRaises(ValueError):self.event('stream_started')

 def test_partial_prepare_failure_still_schedules_cleanup(self):
  self.prepare.side_effect=RuntimeError('activation failed after reconnect')
  with self.assertRaises(RuntimeError):self.event('prepare')
  self.event('abort');self.now=20
  self.assertTrue(self.display.expire());self.remove.assert_called_once()
 def test_only_encoded_frame_event_marks_capture_ready(self):
  self.event('prepare');self.event('stream_started')
  self.assertFalse(self.display.frames_ready)
  self.event('stream_ready');self.assertTrue(self.display.frames_ready)
  self.event('stream_stopped');self.assertFalse(self.display.frames_ready)

 def test_carried_output_cleanup_is_not_a_client_disconnect(self):
  self.display.deadline=20
  self.assertEqual(self.display.state,'desktop_listening')

 def test_preparation_failure_health_is_not_hidden_by_a_listening_engine(self):
  self.prepare.side_effect=RuntimeError('failed')
  with self.assertRaises(RuntimeError):self.event('prepare')
  health=self.display.health(listening=True)
  self.assertTrue(health['listening'])
  self.assertFalse(health['capture_ready'])
  self.assertIn('preparation failed',health['startup_error'])
  self.prepare.side_effect=None;self.event('prepare');self.event('stream_ready')
  health=self.display.health(listening=True)
  self.assertTrue(health['capture_ready'])
  self.assertEqual(health['startup_error'],'')
  self.event('prepare');self.event('stream_started');self.event('stream_stopped')
  self.assertEqual(self.display.state,'disconnect_grace')

 def test_prepare_failure_is_visible_until_a_successful_retry(self):
  self.prepare.side_effect=RuntimeError('private details')
  with self.assertRaises(RuntimeError):self.event('prepare')
  self.assertIn('display preparation failed',self.display.error.lower())
  self.assertNotIn('private details',self.display.error)
  self.assertEqual(self.display.state,'error')
  self.prepare.side_effect=None
  self.event('prepare')
  self.assertEqual(self.display.error,'')
  self.assertEqual(self.display.state,'desktop_listening')
