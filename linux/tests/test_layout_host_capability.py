import unittest
from unittest.mock import patch
from monitorize.platform.monitorize_vkms_dbus import MonitorizeVkmsClient,VkmsProtocolError


class ManagedBackendCapabilityTests(unittest.TestCase):
    def test_only_explicit_host_capabilities_allow_managed_backend(self):
        client=MonitorizeVkmsClient()
        with patch.object(client,'get_capabilities',return_value={'success':True,'managed_layout_backends':['x11','hyprland']}):
            client.require_managed_backend('x11');client.require_managed_backend('hyprland')
        for data in ({'success':True},{'success':True,'managed_layout_backends':[]},{'success':True,'managed_layout_backends':'hyprland'}):
            with self.subTest(data=data),patch.object(client,'get_capabilities',return_value=data):
                with self.assertRaises(VkmsProtocolError):client.require_managed_backend('hyprland')
