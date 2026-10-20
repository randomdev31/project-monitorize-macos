import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from monitorize.platform import sunshine_service as service
from monitorize.platform.remote_login_identity import identity_paths


class ManagedSunshineTests(unittest.TestCase):
    def test_managed_start_uses_engine_owner_and_explicit_identity_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            paths=identity_paths(Path(directory));owner=Mock();owner.process=Mock(pid=4321)
            owner.process.poll.return_value=None
            with patch.object(service,'is_sunshine_running',return_value=False), \
                 patch.object(service,'get_sunshine_candidates',return_value=[['/fixed/engine','/fixed/config']]), \
                 patch.object(service,'get_sunshine_config_dir',return_value=directory), \
                 patch.object(service,'get_sunshine_assets_dir',return_value=None), \
                 patch.object(service,'ensure_sunshine_tray_disabled'), \
                 patch.object(service,'set_sunshine_pipewire_node'), \
                 patch('monitorize.remote_login.engine.EngineOwner',return_value=owner), \
                 patch.object(service.time,'sleep'):
                try:
                    ok,_=service.start_sunshine(managed_identity=paths)
                    self.assertTrue(ok)
                    argv,env=owner.start.call_args.args
                    self.assertIn('file_state='+str(paths.state),argv)
                    self.assertIn('cert='+str(paths.cert),argv)
                    self.assertIs(service._SUNSHINE_ENGINE_OWNERS[1],owner)
                    service.stop_sunshine(1)
                    owner.stop.assert_called_once()
                    self.assertNotIn(1,service._SUNSHINE_ENGINE_OWNERS)
                finally:
                    service._SUNSHINE_PROCESSES.clear();service._SUNSHINE_PROCESS=None
                    service._SUNSHINE_ENGINE_OWNERS.clear()

    def test_failed_stop_never_drops_owner_or_reports_success(self):
        owner=Mock();owner.stop.side_effect=TimeoutError('fixture');owner.process=Mock()
        service._SUNSHINE_ENGINE_OWNERS[1]=owner
        service._SUNSHINE_PROCESSES[1]=owner.process
        try:
            ok,message=service.stop_sunshine(1)
            self.assertFalse(ok);self.assertIn('exit',message)
            self.assertIs(service._SUNSHINE_ENGINE_OWNERS[1],owner)
        finally:
            service._SUNSHINE_ENGINE_OWNERS.clear();service._SUNSHINE_PROCESSES.clear()

class ManualIdentityTests(unittest.TestCase):
    def test_disabled_feature_keeps_authoritative_pairing_identity(self):
        from types import SimpleNamespace
        from monitorize.remote_login import settings
        record=SimpleNamespace(uid=os.getuid(),enabled=False,directory=Path('/private/managed'))
        with patch.object(settings.SETTINGS.__class__,'exists',return_value=True),patch.object(settings,'read_settings',return_value=record):
            paths=service._enrolled_manual_identity(1)
            self.assertEqual(paths.state,Path('/private/managed/identity/sunshine_state.json'))
            self.assertIsNone(service._enrolled_manual_identity(2))
            record.enabled=True
            with self.assertRaisesRegex(RuntimeError,'owns instance 1'):service._enrolled_manual_identity(1)
