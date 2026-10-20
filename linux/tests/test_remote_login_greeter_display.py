import unittest
from unittest.mock import patch
from monitorize.remote_login.greeter_display import greeter_context

class Bus:
    def call(self,*args):return [('g1',42,'greeter','seat0','/greeter')]
    def properties(self,*args):return dict(Class='greeter',Active=True,Remote=False,Seat=('seat0','/seat'),Type='wayland',Id='g1',User=(42,'/user'))

class GreeterContextTests(unittest.TestCase):
    def test_exact_graphical_greeter_is_selected(self):
        self.assertEqual(greeter_context(Bus()),dict(session='g1',greeter_uid=42))
    def test_user_session_or_missing_greeter_refuses_preparation(self):
        for snapshot in (dict(sessions=[{'uid':1000}],greeter_ready=True),dict(sessions=[],greeter_ready=False)):
            with patch('monitorize.remote_login.greeter_display.LogindSessions.snapshot',return_value=snapshot):
                with self.assertRaises(PermissionError):greeter_context(Bus())
    def test_remote_inactive_or_non_graphical_greeter_is_rejected(self):
        for changed in ({'Active':False},{'Remote':True},{'Type':'tty'}):
            bus=Bus();base=bus.properties();bus.properties=lambda *args:dict(base,**changed)
            with self.assertRaises(PermissionError):greeter_context(bus)
