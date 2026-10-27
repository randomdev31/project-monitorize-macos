import json
import unittest
from unittest.mock import Mock,patch
from monitorize.desktop.remote_login_runtime import Participant
from monitorize.remote_login.service import HandoffService


class DiagnosticsTests(unittest.TestCase):
    def test_control_errors_deduplicated_and_recovery_recorded_without_secrets(self):
        interface=Mock();interface.PrepareDesktop.side_effect=RuntimeError('secret request and TOKEN')
        participant=Participant(factory=lambda:interface,output_finder=lambda:None)
        with patch('monitorize.desktop.remote_login_runtime.app_log.write') as log:
            for _ in range(2):
                with self.assertRaises(RuntimeError):participant._call('PrepareDesktop','TOKEN','secret request')
            self.assertEqual(log.call_count,1)
            self.assertIn('PrepareDesktop failed',str(log.call_args))
            self.assertNotIn('TOKEN',str(log.call_args));self.assertNotIn('secret request',str(log.call_args))
            interface.PrepareDesktop.side_effect=None;interface.PrepareDesktop.return_value=json.dumps({'state':'desktop_starting'})
            participant._call('PrepareDesktop','TOKEN','secret request')
            self.assertIn('recovered',str(log.call_args));self.assertEqual(log.call_count,2)

    def test_state_transitions_logged_once_without_raw_error(self):
        participant=Participant(factory=Mock(),output_finder=lambda:None)
        status=dict(state='error',listening=False,capture_ready=False,startup_error='TOKEN SECRET')
        with patch.object(participant,'_poll',return_value=status),patch('monitorize.desktop.remote_login_runtime.app_log.write') as log:
            participant.poll();participant.poll()
            self.assertEqual(log.call_count,1)
            self.assertIn('operation_error=True',str(log.call_args));self.assertNotIn('TOKEN',str(log.call_args))
            status.update(state='desktop_listening',listening=True,startup_error='')
            participant.poll();self.assertEqual(log.call_count,2)

    def test_coordinator_records_changes_without_tokens_or_poll_spam(self):
        service=HandoffService(1000,Mock(),Mock())
        service.epoch='EPOCH_SECRET';service.model.generation='TOKEN_SECRET'
        with patch('builtins.print') as log:
            service.status();service.status()
            self.assertEqual(log.call_count,1)
            self.assertNotIn('SECRET',str(log.call_args))
            service.model.state='waiting_for_desktop'
            service.status();self.assertEqual(log.call_count,2)
