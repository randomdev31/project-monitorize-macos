import time
import unittest
import uuid
from unittest.mock import patch, Mock
from types import SimpleNamespace

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtNetwork import QLocalServer
from monitorize.desktop import tray_agent


class TrayOwnershipTest(unittest.TestCase):
    def test_login_initializes_hidden_listener_but_idle_handoff_does_not(self):
        from monitorize.__main__ import _use_light_tray
        with patch('monitorize.__main__.load_general_settings', return_value={'client_listen_on_open': True}):
            self.assertFalse(_use_light_tray(['monitorize', '--tray-agent']))
            self.assertFalse(_use_light_tray(['monitorize', '--start-in-tray']))
            self.assertTrue(_use_light_tray(['monitorize', '--tray-agent', '--restore-from-tray']))
            self.assertFalse(_use_light_tray(['monitorize', '--restore-from-tray']))
        with patch('monitorize.__main__.load_general_settings', return_value={'client_listen_on_open': False}):
            self.assertTrue(_use_light_tray(['monitorize', '--tray-agent']))

    def test_login_dispatches_full_controller_hidden_when_listening_enabled(self):
        from monitorize import __main__ as entry
        argv = ['monitorize', '--tray-agent']
        with patch.object(entry.sys, 'argv', argv), patch.object(entry, 'load_general_settings', return_value={'client_listen_on_open': True}), patch('monitorize.desktop.main_window.main') as full, patch('monitorize.desktop.tray_agent.main') as light:
            entry.main()
        full.assert_called_once()
        light.assert_not_called()
        self.assertIn('--start-in-tray', argv)

    def test_restoring_tray_window_does_not_request_launch_autostart(self):
        from monitorize.desktop.main_window import _should_start_configured_listeners
        self.assertTrue(_should_start_configured_listeners(['monitorize']))
        self.assertFalse(_should_start_configured_listeners(['monitorize', '--restore-from-tray']))
        self.assertFalse(_should_start_configured_listeners(['monitorize'], restored_from_tray=True))
        agent = SimpleNamespace(_launch_and_quit=Mock())
        tray_agent.TrayAgent.show_app(agent)
        agent._launch_and_quit.assert_called_once_with(['--restore-from-tray'])

    def test_single_tray_owner_and_full_app_handoff(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        name = 'monitorize-tray-test-' + uuid.uuid4().hex
        with patch.object(tray_agent, 'TRAY_SERVER', name):
            server = tray_agent._claim_tray(app)
            self.assertIsNotNone(server)
            try:
                self.assertIsNone(tray_agent._claim_tray(app))
                with patch.object(app, 'quit') as quit_app:
                    tray_agent.dismiss_tray_agent()
                    deadline = time.monotonic() + 1
                    while not quit_app.called and time.monotonic() < deadline:
                        app.processEvents()
                    quit_app.assert_called_once()
            finally:
                server.close()
                server.deleteLater()
                QLocalServer.removeServer(name)

    def test_hidden_start_stays_hidden_before_tray_host_is_ready(self):
        from monitorize.desktop.main_window import _show_initial_window
        window=SimpleNamespace(tray=Mock(),show=Mock())
        with patch('monitorize.desktop.main_window.QSystemTrayIcon.isSystemTrayAvailable',return_value=False), patch('monitorize.desktop.main_window.QApplication.setQuitOnLastWindowClosed') as keep_alive, patch('monitorize.desktop.main_window.app_log.write'):
            self.assertFalse(_show_initial_window(window,True))
        window.show.assert_not_called();window.tray.show.assert_called_once()
        keep_alive.assert_called_once_with(False)

    def test_manual_start_shows_window(self):
        from monitorize.desktop.main_window import _show_initial_window
        window=SimpleNamespace(tray=Mock(),show=Mock())
        self.assertTrue(_show_initial_window(window,False))
        window.show.assert_called_once()
