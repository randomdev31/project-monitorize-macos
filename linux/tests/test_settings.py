import copy
import json
import os
import tempfile
import unittest
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch, Mock

from PyQt6.QtCore import QSettings

from monitorize.config import settings
from monitorize.desktop.backend import MonitorizeBackend


class SettingsTest(unittest.TestCase):
    def draft_backend(self):
        """Exercise the real draft methods without starting platform services."""
        from monitorize.desktop.configuration_state import ConfigurationState
        state = ConfigurationState(settings.load_display_settings(),
            settings.load_second_display_settings(), settings.load_general_settings())
        backend = SimpleNamespace(
            applyingConfiguration=False, isStreaming=False, sessionBusy=False,
            _closing=False, _web_settings_enabled=False, _sunshine_settings_revision=0,
            configuration_state=state,
            configurationChanged=SimpleNamespace(emit=Mock()),
            sunshineSettingsRevisionChanged=SimpleNamespace(emit=Mock()),
            clientDisplaySettingsChanged=SimpleNamespace(emit=Mock()),
            streaming=SimpleNamespace(third_streaming=False),
            session=SimpleNamespace(preset_configuration=None, configuration_changed=Mock()),
        )
        backend.loadDisplaySettings = lambda: copy.deepcopy(state.draft['primary'])
        backend.loadSecondDisplaySettings = lambda: copy.deepcopy(state.draft['second'])
        backend._update_draft = lambda group, values: MonitorizeBackend._update_draft(backend, group, values)
        backend._prepare_sunshine_choices = lambda instance, values: MonitorizeBackend._prepare_sunshine_choices(backend, instance, values)
        backend.saveSunshineDisplaySettings = Mock(side_effect=lambda instance, values, sync_adapter=True:
            MonitorizeBackend.saveSunshineDisplaySettings(backend, instance, values, sync_adapter))
        return backend

    def test_general_preferences_survive_fresh_process_legacy_group_migration(self):
        from pathlib import Path
        Path(self.config_file).write_text('[%General]\nminimize_to_tray=true\nsystem_setup_decided=false\n')
        code = (
            'from monitorize.config import settings as s; import sys,json; '
            's.CONFIG_DIR=sys.argv[1]; s.CONFIG_FILE=sys.argv[2]; '
        )
        subprocess.run([sys.executable, '-c', code +
            "s.save_general_settings(client_listen_on_open=True,client_restart_on_crash=True,display_behavior='virtual_only',sunshine_web_settings_enabled=True)",
            self.tmp.name, self.config_file], check=True, capture_output=True, timeout=5)
        for _ in range(2):
            result = subprocess.run([sys.executable, '-c', code +
                'print(json.dumps(s.load_general_settings()))', self.tmp.name, self.config_file],
                check=True, capture_output=True, text=True, timeout=5)
            saved = json.loads(result.stdout)
            for key in ('minimize_to_tray', 'client_listen_on_open', 'client_restart_on_crash', 'sunshine_web_settings_enabled'):
                self.assertTrue(saved[key], key)
            self.assertEqual(saved['display_behavior'], 'virtual_only')

    def test_shared_display_behavior_is_validated_and_persisted(self):
        self.assertEqual(settings.load_general_settings()['display_behavior'], 'extend')
        for mode in ('primary', 'virtual_only', 'extend'):
            settings.save_general_settings(display_behavior=mode)
            self.assertEqual(settings.load_general_settings()['display_behavior'], mode)
        with self.assertRaises(ValueError):
            settings.save_general_settings(display_behavior='invalid')

    def test_preset_retains_shared_display_behavior_and_old_presets_default_extend(self):
        preset = dict(version=2, name='Remote', primary=settings.load_display_settings(), second={'enabled': False})
        self.assertEqual(settings._normalize_preset(preset)['display_behavior'], 'extend')
        preset['display_behavior'] = 'virtual_only'
        settings.save_presets([preset])
        self.assertEqual(settings.load_presets()[0]['display_behavior'], 'virtual_only')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_file = os.path.join(self.tmp.name, "settings.ini")
        self.patches = (
            patch.object(settings, "CONFIG_DIR", self.tmp.name),
            patch.object(settings, "CONFIG_FILE", self.config_file),
        )
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_client_display_settings_are_opt_in_and_preserve_manual_modes(self):
        self.assertFalse(settings.load_display_settings()["use_client_display_settings"])
        self.assertFalse(settings.load_second_display_settings()["use_client_display_settings"])
        settings.save_display_settings(resolution="Custom...", custom_w="2304", custom_h="1440",
                                       fps="90", use_client_display_settings=True)
        settings.save_second_display_settings(enabled=True, resolution="2560x1600", fps="120",
                                              use_client_display_settings=False)
        primary = settings.load_display_settings()
        self.assertTrue(primary["use_client_display_settings"])
        self.assertEqual((primary["custom_w"], primary["custom_h"], primary["fps"]),
                         ("2304", "1440", "90"))
        primary["use_client_display_settings"] = False
        settings.save_display_settings(**primary)
        self.assertEqual(settings.load_display_settings()["custom_w"], "2304")
        self.assertFalse(settings.load_second_display_settings()["use_client_display_settings"])

    def test_client_listener_general_settings_round_trip(self):
        for key in ("client_listen_on_open", "client_restart_on_crash"):
            self.assertFalse(settings.load_general_settings()[key])
        settings.save_general_settings(client_listen_on_open=True, client_restart_on_crash=True)
        settings.save_general_settings(minimize_to_tray=True)
        saved = settings.load_general_settings()
        self.assertTrue(saved["client_listen_on_open"])
        self.assertTrue(saved["client_restart_on_crash"])

    def test_preset_retains_independent_client_request_flags(self):
        settings.save_presets([{"version": 2, "name": "Listeners",
                               "primary": {"resolution": "2560x1600", "fps": "120",
                                           "use_client_display_settings": True},
                               "second": {"enabled": True, "resolution": "1920x1080",
                                          "use_client_display_settings": False}}])
        preset = settings.load_presets()[0]
        self.assertTrue(preset["primary"]["use_client_display_settings"])
        self.assertFalse(preset["second"]["use_client_display_settings"])
        self.assertEqual(preset["primary"]["resolution"], "2560x1600")

    def test_backend_card_round_trip_preserves_independent_listener_selection(self):
        fake = self.draft_backend()
        MonitorizeBackend.saveVirtualDisplaySettings(fake, [
            {"id": 1, "resolution": "2560x1440", "fps": "90", "use_client_display_settings": True},
            {"id": 2, "resolution": "1920x1080", "fps": "60", "use_client_display_settings": False}])
        cards = MonitorizeBackend.loadVirtualDisplaySettings(fake)
        self.assertTrue(cards[0]["use_client_display_settings"])
        self.assertFalse(cards[1]["use_client_display_settings"])
        before = copy.deepcopy(fake.configuration_state.applied)
        fake.isStreaming = True
        MonitorizeBackend.saveVirtualDisplaySettings(fake, [{"use_client_display_settings": False}])
        self.assertFalse(fake.configuration_state.draft['primary']['use_client_display_settings'])
        self.assertEqual(fake.configuration_state.applied, before)
        self.assertFalse(settings.load_display_settings()['use_client_display_settings'])
        self.assertFalse(settings.load_second_display_settings()['enabled'])
        fake.applyingConfiguration = True
        draft = copy.deepcopy(fake.configuration_state.draft)
        MonitorizeBackend.saveVirtualDisplaySettings(fake, [{"use_client_display_settings": True}])
        self.assertEqual(fake.configuration_state.draft, draft)

    def test_display_settings_round_trip(self):
        settings.save_display_settings(
            resolution="2560x1440",
            fps="90",
            display_type="Extend",
            virtual_display_creator="vkms",
            sunshine_encoder="NVIDIA",
            sunshine_gpu="0000:03:00.0",
            sunshine_codec="AV1",
            sunshine_capture="kms",
            streaming_customized=True,
            sunshine_native_pen_touch=False,
            enable_audio=True,
        )
        saved = settings.load_display_settings()
        self.assertEqual(saved["resolution"], "2560x1440")
        self.assertEqual(saved["virtual_display_creator"], "vkms")
        self.assertEqual(saved["sunshine_codec"], "AV1")
        self.assertEqual(saved["sunshine_capture"], "kms")
        self.assertEqual(saved["sunshine_gpu"], "0000:03:00.0")
        self.assertTrue(saved["streaming_customized"])
        self.assertFalse(saved["sunshine_native_pen_touch"])
        self.assertTrue(saved["enable_audio"])

    def test_legacy_stock_vkms_connector_is_ignored_and_removed_on_save(self):
        store = QSettings(self.config_file, QSettings.Format.IniFormat)
        store.setValue("display/vkms_connector", "card2-Virtual-1")
        store.setValue("display/virtual_display_creator", "vkms")
        store.setValue("display/resolution", "2560x1440")
        store.setValue("display/fps", "60")
        store.sync()
        saved = settings.load_display_settings()
        self.assertNotIn("vkms_connector", saved)
        self.assertEqual(saved["resolution"], "2560x1440")
        settings.save_display_settings(**saved)
        self.assertFalse(QSettings(self.config_file, QSettings.Format.IniFormat)
                         .contains("display/vkms_connector"))

    def test_legacy_stock_vkms_preset_uses_same_mode_without_connector(self):
        normalized = settings._normalize_session({
            "resolution": "2560x1440", "fps": "90",
            "display_type": "Extend", "virtual_display_creator": "vkms",
            "vkms_custom_mode": False, "vkms_connector": "card2-Virtual-1",
        })
        self.assertEqual((normalized["resolution"], normalized["fps"]),
                         ("2560x1440", "90"))
        self.assertNotIn("vkms_custom_mode", normalized)
        self.assertNotIn("vkms_connector", normalized)

    def test_second_display_mode_is_persisted_independently(self):
        settings.save_display_settings(resolution="2560x1600", fps="120", sunshine_capture="kwin")
        settings.save_second_display_settings(
            enabled=True,
            resolution="1920x1080",
            fps="75",
            sunshine_capture="portal",
        )

        primary = settings.load_display_settings()
        second = settings.load_second_display_settings()
        self.assertEqual((primary["resolution"], primary["fps"]), ("2560x1600", "120"))
        self.assertTrue(second["enabled"])
        self.assertEqual((second["resolution"], second["fps"]), ("1920x1080", "75"))
        self.assertEqual(primary["sunshine_capture"], "kwin")
        self.assertEqual(second["sunshine_capture"], "portal")

        settings.save_second_display_settings(enabled=False)
        self.assertFalse(settings.load_second_display_settings()["enabled"])

    def test_old_and_invalid_capture_settings_use_monitorize_auto(self):
        self.assertEqual(settings.load_display_settings()["sunshine_capture"], "auto")
        settings.save_display_settings(resolution="1920x1080", sunshine_capture="invalid")
        self.assertEqual(settings.load_display_settings()["sunshine_capture"], "auto")

    def test_backend_stages_each_sunshine_instance_independently(self):
        settings.save_display_settings(resolution="1920x1080")
        settings.save_second_display_settings(enabled=True, resolution="1920x1080")
        backend = self.draft_backend()
        before = copy.deepcopy(backend.configuration_state.applied)
        with patch("monitorize.desktop.backend.save_sunshine_config") as write:
            backend.saveSunshineDisplaySettings(1, {"sunshine_capture": "portal", "sunshine_encoder": "NVIDIA"})
            backend.saveSunshineDisplaySettings(2, {"sunshine_capture": "kms", "sunshine_encoder": "VA-API"})
        primary = backend.loadDisplaySettings()
        second = backend.loadSecondDisplaySettings()
        self.assertEqual((primary['sunshine_capture'], primary['sunshine_encoder']), ('portal', 'NVIDIA'))
        self.assertEqual((second['sunshine_capture'], second['sunshine_encoder']), ('kms', 'VA-API'))
        self.assertEqual(backend.configuration_state.applied, before)
        self.assertEqual(settings.load_display_settings()['sunshine_encoder'], 'Auto')
        self.assertEqual(settings.load_second_display_settings()['sunshine_encoder'], 'Auto')
        write.assert_not_called()

    def test_sunshine_choices_update_draft_without_writing_engine_config(self):
        settings.save_display_settings(resolution="1920x1080", sunshine_encoder="Auto",
            sunshine_codec="Auto", sunshine_native_pen_touch=True, enable_audio=False)
        backend = self.draft_backend()
        choices = dict(sunshine_encoder="NVIDIA", sunshine_codec="HEVC", sunshine_capture="kwin",
            sunshine_gpu="", streaming_customized=True, sunshine_native_pen_touch=True, enable_audio=False)
        before = copy.deepcopy(backend.configuration_state.applied)
        with patch("monitorize.desktop.backend.save_sunshine_config") as write:
            for _ in range(2):
                result = MonitorizeBackend.saveSunshineChoices(backend, 1, choices)
                self.assertTrue(result['success'])
                self.assertEqual({key: backend.loadDisplaySettings()[key] for key in choices}, choices)
            write.assert_not_called()
        self.assertEqual(backend.configuration_state.applied, before)
        self.assertEqual(settings.load_display_settings()['sunshine_encoder'], 'Auto')
        backend.applyingConfiguration = True
        self.assertFalse(MonitorizeBackend.saveSunshineChoices(backend, 1, choices)['success'])

    def test_v1_wifi_preset_migrates_and_usb_preset_is_dropped(self):
        store = QSettings(self.config_file, QSettings.Format.IniFormat)
        store.setValue(
            "presets/items",
            json.dumps(
                [
                    {
                        "version": 1,
                        "name": "Wi-Fi",
                        "mode": "wifi",
                        "primary": {
                            "resolution": "1920x1080",
                            "fps": "60",
                            "display_type": "Extend",
                        },
                        "third": {"enabled": False},
                    },
                    {
                        "version": 1,
                        "name": "USB",
                        "mode": "usb",
                        "primary": {},
                        "third": {"enabled": False},
                    },
                ]
            ),
        )
        store.sync()
        presets = settings.load_presets()
        self.assertEqual([preset["name"] for preset in presets], ["Wi-Fi"])
        self.assertEqual(presets[0]["version"], 2)
        self.assertIn("sunshine_encoder", presets[0]["primary"])
        self.assertEqual(presets[0]["primary"]["sunshine_capture"], "auto")
        self.assertNotIn("mode", presets[0])

    def test_gpu_selection_round_trips_through_presets_and_rejects_bad_ids(self):
        settings.save_presets([{
            "version": 2,
            "name": "Hybrid",
            "primary": {
                "resolution": "1920x1080",
                "fps": "60",
                "display_type": "Extend",
                "virtual_display_creator": "vkms",
                "sunshine_encoder": "VA-API",
                "sunshine_gpu": "0000:03:00.0",
                "sunshine_capture": "kms",
            },
            "second": {
                "enabled": True,
                "resolution": "1280x720",
                "fps": "60",
                "sunshine_capture": "portal",
            },
        }])
        self.assertEqual(
            settings.load_presets()[0]["primary"]["sunshine_gpu"],
            "0000:03:00.0",
        )
        self.assertEqual(settings.load_presets()[0]["primary"]["sunshine_capture"], "kms")
        self.assertEqual(settings.load_presets()[0]["second"]["sunshine_capture"], "portal")
        self.assertEqual(
            settings.load_presets()[0]["primary"]["virtual_display_creator"],
            "vkms",
        )

        settings.save_display_settings(
            resolution="1920x1080",
            sunshine_encoder="VA-API",
            sunshine_gpu="../../dev/dri/renderD128",
        )
        self.assertEqual(settings.load_display_settings()["sunshine_gpu"], "")

    def test_malformed_second_display_does_not_crash_preset_loading(self):
        store = QSettings(self.config_file, QSettings.Format.IniFormat)
        store.setValue("presets/items", json.dumps([
            {"version": 2, "name": "Broken", "primary": {}, "second": "invalid"},
            {"version": 2, "name": "Valid", "primary": {}, "second": {"enabled": False}},
        ]))
        store.sync()
        self.assertEqual([preset["name"] for preset in settings.load_presets()], ["Valid"])

    def test_custom_resolution_round_trip(self):
        settings.save_display_settings(
            resolution="Custom...",
            custom_w="2340",
            custom_h="1080",
            fps="60",
            virtual_display_creator="vkms",
        )
        saved = settings.load_display_settings()
        self.assertEqual(saved["resolution"], "Custom...")
        self.assertEqual(saved["custom_w"], "2340")
        self.assertEqual(saved["custom_h"], "1080")


if __name__ == "__main__":
    unittest.main()
