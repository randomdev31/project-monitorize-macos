import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication, QProcess
from monitorize.desktop.session import Session
from monitorize.desktop.streaming_controller import StreamingController


class SessionTest(unittest.TestCase):
    def test_mirror_crash_retry_keeps_output_and_stop_cancels_it(self):
        self.config.update(display_type='Mirror',mirror_output='eDP-1')
        scheduled=[]
        self.c.mirror_retry.schedule=lambda delay,callback:scheduled.append((delay,callback))
        with patch('monitorize.desktop.streaming_controller.load_general_settings',return_value={'client_restart_on_crash':True}), \
             patch('monitorize.desktop.streaming_controller.check_sunshine_health',return_value=(False,1,'')), \
             patch('monitorize.desktop.streaming_controller.is_sunshine_running',return_value=False):
            self.s.start()
            self.c._check_sunshine_health()
            QCoreApplication.processEvents()
            self.assertTrue(self.s.active)
            self.assertTrue(self.c.mirror_retry.pending)
            self.assertEqual(scheduled[0][0],2000)
            scheduled.pop(0)[1]()
            self.assertEqual(self.c.mirror_output,'eDP-1')
            self.assertEqual(self.c._start_instance.call_count,2)
            self.c._check_sunshine_health()
            QCoreApplication.processEvents()
            callback=scheduled[-1][1]
            self.s.stop();callback()
            self.assertFalse(self.s.active)
            self.assertEqual(self.c._start_instance.call_count,2)
            self.c._start_display_process.assert_not_called()

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        general = patch('monitorize.desktop.session.load_general_settings', return_value={'display_behavior': 'extend'})
        general.start()
        self.addCleanup(general.stop)
        readiness = patch("monitorize.desktop.streaming_controller.get_sunshine_startup_status",
                          return_value=("ready", ""))
        readiness.start()
        self.addCleanup(readiness.stop)
        p = patch(
            "monitorize.platform.mirror_outputs.active_outputs",
            return_value=[
                {"id": "eDP-1", "native_width": 2560, "native_height": 1600}
            ],
        )
        p.start()
        self.addCleanup(p.stop)
        self.config = {"display_type": "Extend", "resolution": "1920x1080", "fps": "60"}
        p = patch("monitorize.desktop.session.load_display_settings", side_effect=lambda: self.config.copy())
        p.start()
        self.addCleanup(p.stop)
        self.second_config = {
            "enabled": False, "resolution": "1920x1080", "fps": "60",
            "custom_w": "", "custom_h": "", "custom_fps": "",
        }
        p = patch(
            "monitorize.desktop.session.load_second_display_settings",
            side_effect=lambda: self.second_config.copy(),
        )
        p.start()
        self.addCleanup(p.stop)
        p = patch("monitorize.desktop.streaming_controller.stop_sunshine")
        self.stop_sunshine = p.start()
        self.addCleanup(p.stop)
        self.c = StreamingController("hyprland", "192.0.2.1")
        self.c._start_display_process = Mock(side_effect=self.process)
        self.c._start_instance = Mock(return_value=True)
        self.s = Session(self.c)
        self.s.count = 0
        self.addCleanup(self.c.sunshine_watchdog_timer.stop)

    @staticmethod
    def process(*_args):
        p = Mock()
        p.state.return_value = QProcess.ProcessState.NotRunning
        return p

    def ready(self, slot="primary", **extra):
        self.c._display_ready(slot, dict(name="Monitorize-1" if slot == "primary" else "Monitorize-2",
                                       width=1920, height=1080, fps=60, **extra))
        QCoreApplication.processEvents()

    def launch_one(self):
        self.s.add()
        self.s.start()
        self.ready()

    def launch_two(self):
        self.launch_one()
        self.s.add()
        self.s.start()
        self.ready("additional")

    def fake_client_runtime(self):
        from types import SimpleNamespace
        runtime = Mock()
        runtime.slots = {}
        runtime.active = False
        runtime.busy = False
        runtime.retiring = False
        runtime.cards = []
        def start_slot(instance, config):
            runtime.slots[instance] = SimpleNamespace(status="Waiting for client", config=config)
            runtime.active = True
            return True
        runtime.start_slot.side_effect = start_slot
        runtime.start_manual_slot.side_effect = start_slot
        self.s.client_runtime = runtime
        return runtime

    def test_preserved_client_preference_does_not_break_display_only_mode(self):
        self.config["use_client_display_settings"] = True
        self.c.streaming_backend = "none"
        self.s.configuration_changed()
        self.s.start()
        self.c._start_display_process.assert_called_once()
        self.assertIsNone(self.s.client_runtime)

    def test_client_preset_snapshot_resolves_custom_manual_dimensions(self):
        self.config.update(use_client_display_settings=True, resolution="Custom...",
                           custom_w="2304", custom_h="1440", fps="90")
        self.s.configuration_changed()
        snapshot = self.s.configured_snapshot()
        self.assertEqual(snapshot["primary"]["resolution"], "2304x1440")

    def test_second_client_preset_inherits_primary_vkms_backend(self):
        self.s.preset_configuration = {
            "primary": {"resolution": "2560x1600", "fps": "120", "virtual_display_creator": "vkms",
                        "use_client_display_settings": True},
            "second": {"enabled": True, "resolution": "1920x1080", "fps": "60",
                       "use_client_display_settings": True}}
        self.assertEqual(self.s.second_configuration()["virtual_display_creator"], "vkms")

    def test_client_cards_start_two_independent_hosts_without_creating_displays(self):
        self.config["use_client_display_settings"] = True
        self.second_config.update(enabled=True, use_client_display_settings=True)
        self.s.configuration_changed()
        runtime = self.fake_client_runtime()
        self.s.start()
        self.assertEqual([call.args[0] for call in runtime.start_slot.call_args_list], [1, 2])
        self.c._start_display_process.assert_not_called()
        self.c._start_instance.assert_not_called()
        self.assertTrue(self.s.active)
        self.assertFalse(self.s.busy)

    def test_mixed_cards_delegate_both_slots_without_primary_readiness_dependency(self):
        self.config["use_client_display_settings"] = True
        self.second_config.update(enabled=True, use_client_display_settings=False)
        self.s.configuration_changed()
        runtime = self.fake_client_runtime()
        self.s.start()
        self.assertEqual(set(runtime.slots), {1, 2})
        self.assertTrue(runtime.slots[1].config["use_client_display_settings"])
        self.assertFalse(runtime.slots[2].config["use_client_display_settings"])
        self.c._start_display_process.assert_not_called()

    def test_listener_auto_start_skips_manual_cards(self):
        self.config["use_client_display_settings"] = False
        self.second_config.update(enabled=True, use_client_display_settings=True)
        self.s.configuration_changed()
        runtime = self.fake_client_runtime()
        self.s.start(listeners_only=True)
        self.assertEqual([call.args[0] for call in runtime.start_slot.call_args_list], [2])
        self.assertTrue(self.s.pending_displays)
        self.s.start()
        runtime.start_manual_slot.assert_called_once()
        self.assertEqual(set(runtime.slots), {1, 2})

    def test_listener_stop_cancels_runtime_before_legacy_cleanup(self):
        runtime = self.fake_client_runtime()
        self.s.stop()
        runtime.stop.assert_called_once()

    def test_failed_listener_remains_stoppable_without_claiming_host_ready(self):
        from types import SimpleNamespace
        runtime = self.fake_client_runtime()
        runtime.active = True
        runtime.slots = {1: SimpleNamespace(status="error")}
        self.assertTrue(self.s.active)
        self.assertFalse(self.s.ready)
        runtime.slots[1].status = "waiting"
        self.assertTrue(self.s.ready)

    def test_client_preset_snapshot_retains_manual_modes_before_connection(self):
        self.config.update(use_client_display_settings=True, resolution="2560x1600", fps="120")
        self.second_config.update(enabled=True, use_client_display_settings=True)
        self.s.configuration_changed()
        self.fake_client_runtime()
        snapshot = self.s.configured_snapshot()
        self.assertTrue(snapshot["primary"]["use_client_display_settings"])
        self.assertEqual(snapshot["primary"]["resolution"], "2560x1600")
        self.assertTrue(snapshot["second"]["use_client_display_settings"])

    def test_add_only_creates_cards_in_both_backend_modes(self):
        for backend in ("sunshine", "none"):
            self.c.streaming_backend = backend
            self.s.count = 0
            self.s.add()
            self.s.add()
            self.s.add()
            self.assertEqual(self.s.count, 2)
            self.assertFalse(self.s.busy)
            self.assertFalse(self.c.streaming)
            self.c._start_display_process.assert_not_called()
            self.c._start_instance.assert_not_called()

    def test_vkms_configuration_allows_two_cards(self):
        self.config["virtual_display_creator"] = "vkms"
        self.s.add()
        self.s.add()
        self.assertEqual(self.s.max_displays, 2)
        self.assertEqual(self.s.count, 2)
        self.s.start()
        self.assertEqual(self.c.virtual_display_creator, "vkms")
        self.ready()
        self.assertTrue(self.c.third_streaming)
        self.ready("additional")
        self.assertEqual(
            [call.args[0] for call in self.c._start_display_process.call_args_list],
            ["primary", "additional"],
        )

    def test_persisted_second_display_has_its_own_mode_configuration(self):
        self.second_config.update(
            enabled=True,
            resolution="1920x1080",
            fps="75",
        )
        self.s.configuration_changed()
        self.assertEqual(self.s.count, 2)
        self.config.update(resolution="2560x1600", fps="120")
        primary = self.s.configuration()
        second = self.s.second_configuration()
        self.assertEqual((primary["res"], primary["fps"]), ("2560x1600", "120"))
        self.assertEqual((second["res"], second["fps"]), ("1920x1080", "75"))

    def test_two_configured_display_modes_reach_their_own_holders(self):
        self.config.update(resolution="2560x1600", fps="120")
        self.second_config.update(enabled=True, resolution="1920x1080", fps="75")
        self.s.configuration_changed()

        self.s.start()
        self.assertEqual(
            self.c._start_display_process.call_args.args[:4],
            ("primary", 2560, 1600, 120),
        )
        self.ready()
        self.assertEqual(
            self.c._start_display_process.call_args.args[:4],
            ("additional", 1920, 1080, 75),
        )

    @patch("monitorize.desktop.session.os.path.isfile", return_value=True)
    def test_flatpak_runtime_keeps_explicit_vkms_creator(self, _isfile):
        self.config["virtual_display_creator"] = "vkms"
        self.assertEqual(
            self.s.configuration()["virtual_display_creator"],
            "vkms",
        )

    def test_start_creates_display_and_streams_only_after_ready(self):
        self.config.update(streaming_customized=True, sunshine_codec="AV1", sunshine_encoder="NVIDIA")
        self.s.add()
        self.s.start()
        self.assertTrue(self.s.busy)
        self.c._start_instance.assert_not_called()
        self.ready()
        self.assertTrue(self.s.running)
        self.assertEqual(self.c.codec, "AV1")
        self.c._start_instance.assert_called_once()
        self.assertEqual(self.c._start_display_process.call_count, 1)

    def test_stop_removes_resources_but_keeps_cards_and_restart_recreates(self):
        self.launch_one()
        self.s.stop()
        self.assertFalse(self.c.streaming)
        self.assertIsNone(self.c.streamer)
        self.assertEqual(self.s.count, 1)
        self.assertEqual(self.s.cards()[0]["state"], "Not started")
        self.s.start()
        self.ready()
        self.assertTrue(self.s.running)
        self.assertEqual(self.c._start_display_process.call_count, 2)

    def test_second_card_added_while_running_waits_for_explicit_start(self):
        self.launch_one()
        self.s.add()
        self.assertTrue(self.s.pending_displays)
        self.assertFalse(self.c.third_streaming)
        self.assertEqual(self.c._start_display_process.call_count, 1)
        self.s.start()
        self.ready("additional")
        self.assertFalse(self.s.pending_displays)
        self.assertEqual(self.c._start_instance.call_args.args[0], 2)
        self.assertEqual(self.s.cards()[1]["address"], "192.0.2.1:49089")

    def test_two_cards_start_and_restart_in_order(self):
        self.s.add()
        self.s.add()
        self.s.start()
        self.ready()
        self.assertTrue(self.c.third_streaming)
        self.ready("additional")
        self.assertTrue(self.s.running)
        self.s.stop()
        self.s.start()
        self.ready()
        self.ready("additional")
        self.assertTrue(self.s.running)
        self.assertEqual(self.c._start_display_process.call_count, 4)

    def test_remove_pending_card_never_touches_resources(self):
        self.s.add()
        self.s.remove(0)
        self.assertEqual(self.s.count, 0)
        self.stop_sunshine.assert_not_called()
        self.c._start_display_process.assert_not_called()

    def test_remove_second_leaves_primary_running(self):
        self.launch_two()
        self.s.remove(1)
        self.assertTrue(self.s.running)
        self.assertTrue(self.c.streaming)
        self.assertEqual(self.s.count, 1)
        self.assertFalse(self.c.third_streaming)

    def test_remove_first_stops_before_renumbering_remaining_card(self):
        self.launch_two()
        self.s.remove(0)
        self.assertFalse(self.c.streaming)
        self.assertEqual(self.s.cards()[0]["number"], 1)

    def test_mirror_rejects_add_and_starts_without_virtual_outputs(self):
        self.config["display_type"] = "Mirror"
        self.config["mirror_output"] = "eDP-1"
        self.s.add()
        self.assertEqual(self.s.count, 0)
        cards = self.s.cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["title"], "eDP-1")
        self.assertTrue(cards[0]["mirror"])
        self.assertFalse(cards[0]["live"])
        self.s.start()
        self.assertTrue(self.s.running)
        cards = self.s.cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["title"], "eDP-1")
        self.assertTrue(cards[0]["live"])
        self.assertEqual(cards[0]["address"], "192.0.2.1:47989")
        self.c._start_display_process.assert_not_called()

    def test_mirror_card_exists_when_no_monitor_is_selected(self):
        self.config["display_type"] = "Mirror"
        self.config["mirror_output"] = ""

        self.assertEqual(
            self.s.cards()[0]["title"],
            "No monitor selected",
        )

    def test_virtual_only_creates_on_start_without_sunshine(self):
        self.c.streaming_backend = "none"
        self.s.add()
        self.c._start_display_process.assert_not_called()
        self.s.start()
        self.ready()
        self.c._start_instance.assert_not_called()
        self.assertFalse(self.s.running)
        self.assertTrue(self.c.streaming)
        self.s.add()
        self.assertFalse(self.c.third_streaming)
        self.s.start()
        self.ready("additional")
        self.assertTrue(self.c.third_streaming)
        self.c._start_instance.assert_not_called()
        self.s.stop()
        self.assertFalse(self.c.streaming)

    def test_late_ready_after_stop_is_ignored(self):
        self.s.add()
        self.s.start()
        process = self.c.streamer
        generation = self.c.generation
        self.s.stop()
        self.c._read_display_process("primary", generation, process)
        process.readAllStandardOutput.assert_not_called()
        self.assertFalse(self.s.running)

    def test_portal_node_is_retained_for_start(self):
        self.s.add()
        self.s.start()
        self.ready(portal=True, node_id=42)
        self.assertEqual(self.c._start_instance.call_args.kwargs["pipewire_node"], 42)

    def test_stopped_extend_can_be_switched_to_mirror(self):
        self.launch_one()
        self.s.stop()
        self.config["display_type"] = "Mirror"
        self.assertEqual(self.s.mode, "Mirror")
        self.s.start()
        self.assertEqual(self.s.count, 0)
        self.assertTrue(self.s.running)

    def test_failed_process_start_clears_busy_and_emits_failure(self):
        failed = Mock()
        self.c.startFailed.connect(failed)
        self.s.add()
        self.s.start()
        process = self.c.streamer
        process.error.return_value = QProcess.ProcessError.FailedToStart
        self.c._process_error("primary", self.c.generation, process)
        QCoreApplication.processEvents()
        failed.assert_called_once()
        self.assertFalse(self.s.busy)
        self.assertEqual(self.s.cards()[0]["state"], "Not started")

    def test_second_creation_failure_does_not_retry_forever(self):
        self.s.count = 2
        self.s.start()
        self.ready()
        process = self.c.third_streamer
        process.error.return_value = QProcess.ProcessError.FailedToStart
        self.c._process_error("additional", self.c.third_generation, process)
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        self.assertFalse(self.s.start_requested)
        self.assertFalse(self.s.busy)
        self.assertEqual(self.c._start_display_process.call_count, 2)

    def test_preset_restart_retains_independent_second_settings(self):
        self.s.preset_configuration = {
            "primary": {"resolution": "2560x1440", "fps": "90", "sunshine_codec": "AV1"},
            "second": {"enabled": True, "resolution": "1280x800", "fps": "30", "sunshine_codec": "HEVC"},
        }
        self.s.count = 2
        self.s.start()
        self.ready()
        self.assertEqual(self.c.third_width, 1280)
        self.assertEqual(self.c.third_fps, 30)
        self.ready("additional")
        self.assertEqual(self.c.codec, "AV1")
        self.assertEqual(self.c.third_codec, "HEVC")

    def test_queued_preset_second_display_is_cancelled_after_stop(self):
        self.c.start(
            "1920x1080", "60", options={"second": {
                "enabled": True, "resolution": "1280x800", "fps": "60",
            }},
        )
        self.c._display_ready("primary", {"name": "Monitorize-1", "width": 1920,
                                           "height": 1080, "fps": 60})
        self.c.stop()
        QCoreApplication.processEvents()
        self.assertFalse(self.c.third_streaming)
        self.assertEqual(self.c._start_display_process.call_count, 1)

    def test_queued_preset_second_display_clears_pending_options(self):
        self.c.start(
            "1920x1080", "60", options={"second": {
                "enabled": True, "resolution": "1280x800", "fps": "60",
            }},
        )
        self.ready()
        self.assertTrue(self.c.third_streaming)
        self.assertIsNone(self.c.pending_options)

    def test_stop_sequences_vkms_holders_to_avoid_host_lock_collision(self):
        self.c.virtual_display_creator = "vkms"
        self.c.streaming = True
        self.c.primary_ready = True
        self.c.third_streaming = True
        primary = self.process(); additional = self.process()
        for process in (primary,additional):
            process.state.return_value = QProcess.ProcessState.Running
            process.readAllStandardOutput.return_value = b""
        self.c.streamer = primary;self.c.third_streamer = additional
        self.s.stop()
        additional.write.assert_called_once_with(b"quit\n")
        primary.write.assert_not_called()
        self.c._vkms_cleanup_finished(additional,0)
        primary.write.assert_called_once_with(b"quit\n")
        self.c._vkms_cleanup_finished(primary,0)
        self.assertFalse(self.s.busy)

    def test_vkms_additional_mode_keeps_fractional_refresh(self):
        self.c.virtual_display_creator = "vkms"
        self.c.streaming = True
        self.c.primary_ready = True
        self.c.start_third("2340x1080", "59.94")
        self.assertEqual(self.c._start_display_process.call_args.args[:4],
                         ("additional",2340,1080,59.94))

    def test_vkms_invalid_second_mode_preserves_primary(self):
        self.c.virtual_display_creator = "vkms"
        self.c.streaming = True
        self.c.primary_ready = True
        self.c.start_third("9000x1080", "60")
        self.assertFalse(self.c.third_streaming)
        self.assertTrue(self.c.streaming)
        self.c._start_display_process.assert_not_called()

    def test_second_vkms_stop_does_not_block_or_kill_primary(self):
        self.c.virtual_display_creator = "vkms"
        self.c.streaming = True
        self.c.primary_ready = True
        self.c.third_streaming = True
        primary=self.process();self.c.streamer=primary
        process=self.process();process.state.return_value=QProcess.ProcessState.Running
        process.readAllStandardOutput.return_value=b""
        self.c.third_streamer=process
        self.c.stop_third()
        process.write.assert_called_once_with(b"quit\n")
        process.waitForFinished.assert_not_called()
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        self.assertIs(self.c.streamer,primary)
        self.assertTrue(self.s.busy)
        self.c._vkms_cleanup_finished(process,0)
        self.assertFalse(self.s.busy)

    @patch("monitorize.desktop.session.app_log.write")
    def test_custom_vkms_resolution_configuration_and_logging(self, mock_log_write):
        self.config.update(
            resolution="Custom...",
            custom_w="2340",
            custom_h="1080",
            fps="60",
            virtual_display_creator="vkms",
            display_type="Extend",
        )
        primary = self.s.configuration()
        self.assertEqual(primary["res"], "2340x1080")
        self.assertEqual(primary["fps"], "60")
        self.assertNotIn("vkms_custom_mode", primary)

        self.s._prepare_primary()
        mock_log_write.assert_called_once()
        log_args = mock_log_write.call_args[0]
        self.assertEqual(log_args[0], "DISPLAY")
        self.assertIn("res=2340x1080", log_args[1])
        self.assertIn("fps=60", log_args[1])
        self.assertIn("vkms=True", log_args[1])

        # Preset resolutions use the same VKMS backend as custom ones.
        self.config.update(
            resolution="2560x1600 (16:10)",
            custom_w="",
            custom_h="",
        )
        preset_config = self.s.configuration()
        self.assertEqual(preset_config["res"], "2560x1600")
        self.assertNotIn("vkms_custom_mode", preset_config)
