"""Exercise recovery through the host facade with a real non-reentrant flock."""
import contextlib
import fcntl
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from monitorize.remote_login import enrollment

class RecoveryLockTests(unittest.TestCase):
    def test_recovery_uses_host_transaction_as_the_only_identity_lock_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            lockpath=Path(directory)/'engine.lock'
            @contextlib.contextmanager
            def lock(*args,**kwargs):
                with lockpath.open('a') as stream:
                    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    yield
            def release(*args,**kwargs):
                # The installed host facade acquires this itself around the
                # release, together with lifecycle + engine-cgroup checks.
                with lock():pass
            package=SimpleNamespace(helper=SimpleNamespace(_active_session=lambda uid:('s1',{})))
            facade=SimpleNamespace(__file__='/usr/lib/monitorize-vkms/monitorize_vkms/boot_display.py',desktop_operation_installed=Mock(side_effect=release))
            connection=Mock()
            transport=Mock()
            transport.properties.return_value={'ActiveState':'inactive','ControlGroup':''}
            units=Mock();units.running.return_value=False
            with patch.dict(sys.modules,{'monitorize_vkms':package,'monitorize_vkms.boot_display':facade}), \
                 patch.object(enrollment,'read_settings',return_value=SimpleNamespace(uid=os.getuid(),directory=Path(directory),enabled=True)), \
                 patch.object(enrollment,'require_installed'),patch.object(enrollment,'identity_paths',return_value={}), \
                 patch.object(enrollment,'acquire_identity_lock',side_effect=lock), \
                 patch('dbus.SystemBus',return_value=connection), \
                 patch('monitorize.remote_login.dbus_service.SystemTransport',return_value=transport), \
                 patch('monitorize.remote_login.systemd.EngineUnits',return_value=units):
                self.assertTrue(enrollment.remove_reserved(os.getuid(),release=True)['success'])
            facade.desktop_operation_installed.assert_called_once_with(os.getuid(),'s1','release',engines_stopped=True)
