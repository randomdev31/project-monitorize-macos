"""User-visible listener state and automatic-start contracts."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from monitorize.desktop.backend import MonitorizeBackend


class ClientSessionIntegrationTest(unittest.TestCase):
    def test_general_listener_options_are_available_in_mirror_without_client_cards(self):
        backend=SimpleNamespace(streamingBackend='sunshine')
        with patch('monitorize.desktop.backend.load_display_settings',return_value={'display_type':'Mirror'}), \
             patch('monitorize.desktop.backend.load_second_display_settings',return_value={}):
            self.assertTrue(MonitorizeBackend.clientDisplaySettingsAvailable.fget(backend))
            backend.streamingBackend='none'
            self.assertFalse(MonitorizeBackend.clientDisplaySettingsAvailable.fget(backend))

    def test_mirror_launch_uses_normal_session_start_once(self):
        backend=SimpleNamespace(_listen_on_open_attempted=False,_closing=False,
            _streaming_backend='sunshine',session=SimpleNamespace(mode='Mirror',has_client_cards=lambda:False),
            _start_session_checked=Mock())
        with patch('monitorize.desktop.backend.load_general_settings',return_value={'client_listen_on_open':True}):
            MonitorizeBackend.startConfiguredListeners(backend)
            MonitorizeBackend.startConfiguredListeners(backend)
        backend._start_session_checked.assert_called_once()
        self.assertFalse(backend._pending_listeners_only)

    def test_remote_login_never_launches_a_competing_mirror_host(self):
        backend=SimpleNamespace(remoteLoginEnabled=True,_start_session_checked=Mock())
        MonitorizeBackend.startConfiguredListeners(backend)
        backend._start_session_checked.assert_not_called()

    def test_restart_routes_owned_slot_through_private_runtime(self):
        runtime = SimpleNamespace(slots={1: object()}, restart_slot=Mock(return_value=True))
        backend = SimpleNamespace(session=SimpleNamespace(client_runtime=runtime))
        with patch('monitorize.desktop.backend.restart_sunshine') as generic:
            result = MonitorizeBackend.restartSunshine(backend, 1)
        self.assertTrue(result['success'])
        runtime.restart_slot.assert_called_once_with(1)
        generic.assert_not_called()

    def test_waiting_listener_counts_as_active_session_for_stop_and_tray(self):
        backend = SimpleNamespace(session=SimpleNamespace(active=True, ready=True, client_runtime=SimpleNamespace(active=True)),
                                  streaming=SimpleNamespace(streaming=False, primary_ready=False))
        self.assertTrue(MonitorizeBackend.isStreaming.fget(backend))
        self.assertTrue(MonitorizeBackend.sessionRunning.fget(backend))

    def test_waiting_listener_configuration_can_be_saved_as_preset(self):
        backend = SimpleNamespace(session=SimpleNamespace(active=True, ready=True, busy=False, client_runtime=SimpleNamespace(active=True)),
                                  streaming=SimpleNamespace(streaming=False, primary_ready=False))
        self.assertTrue(MonitorizeBackend.canSavePreset.fget(backend))

    def test_start_on_open_runs_once_and_only_when_enabled(self):
        backend = SimpleNamespace(_listen_on_open_attempted=False, _closing=False,
                                  _streaming_backend='sunshine',
                                  session=SimpleNamespace(has_client_cards=lambda: True),
                                  _start_session_checked=Mock())
        with patch('monitorize.desktop.backend.load_general_settings',
                   return_value={'client_listen_on_open': True}):
            MonitorizeBackend.startConfiguredListeners(backend)
            MonitorizeBackend.startConfiguredListeners(backend)
        backend._start_session_checked.assert_called_once()
        self.assertTrue(backend._pending_listeners_only)

    def test_start_on_open_does_not_start_manual_cards(self):
        backend = SimpleNamespace(_listen_on_open_attempted=False, _closing=False,
                                  _streaming_backend='sunshine',
                                  session=SimpleNamespace(has_client_cards=lambda: False),
                                  _start_session_checked=Mock())
        with patch('monitorize.desktop.backend.load_general_settings',
                   return_value={'client_listen_on_open': True}):
            MonitorizeBackend.startConfiguredListeners(backend)
        backend._start_session_checked.assert_not_called()
