import os
from pathlib import Path
import tempfile
import unittest
from monitorize.remote_login.display_managers import manager_capabilities,sddm_configuration

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'etc/systemd/system').mkdir(parents=True)
        (self.root/'etc/systemd/system/display-manager.service').symlink_to('/usr/lib/systemd/system/sddm.service')
    def write(self,path,text):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    def capabilities(self):return manager_capabilities(self.root,owner_uid=os.getuid())
    def test_x11_default_is_not_silently_supported(self):
        self.assertFalse(self.capabilities()['supported'])
    def test_local_and_final_configuration_precedence(self):
        self.write('usr/lib/sddm/sddm.conf.d/10.conf','[General]\nDisplayServer=wayland\n[Wayland]\nCompositorCommand=kwin_wayland\n')
        self.write('etc/sddm.conf.d/20.conf','[Wayland]\nCompositorCommand=start-hyprland -- --config /some/config\n')
        self.assertEqual(self.capabilities()['compositor'],'hyprland')
        self.assertTrue(self.capabilities()['supported'])
        self.assertFalse(self.capabilities()['validated'])
        self.write('etc/sddm.conf','[General]\nDisplayServer=x11-user\n')
        self.assertFalse(self.capabilities()['supported'])
    def test_wayland_default_compositor_is_weston(self):
        self.write('etc/sddm.conf','[General]\nDisplayServer=wayland\n')
        self.assertEqual(self.capabilities()['compositor'],'weston')
    def test_wrapper_is_not_executed_or_guessed(self):
        self.write('etc/sddm.conf','[General]\nDisplayServer=wayland\n[Wayland]\nCompositorCommand=sh -c "kwin_wayland; touch /tmp/no"\n')
        self.assertFalse(self.capabilities()['supported'])
    def test_unsafe_configuration_is_rejected(self):
        self.write('etc/sddm.conf','[General]\nDisplayServer=wayland\n')
        (self.root/'etc/sddm.conf').chmod(0o666)
        self.assertFalse(self.capabilities()['supported'])
    def test_plasma_remains_recognized(self):
        link=self.root/'etc/systemd/system/display-manager.service';link.unlink();link.symlink_to('/usr/lib/systemd/system/plasmalogin.service')
        self.assertTrue(self.capabilities()['supported'])

    def test_unknown_or_symlinked_config_is_not_trusted(self):
        self.write('etc/sddm.conf','[General]\nDisplayServer=wayland\n[Wayland]\nCompositorCommand=/custom/wrapper\n')
        self.assertFalse(self.capabilities()['supported'])
        path=self.root/'etc/sddm.conf';path.unlink();path.symlink_to('/etc/passwd')
        self.assertFalse(self.capabilities()['supported'])
