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

    def test_isolated_gdm_uid_rejects_another_seat_or_overlapping_greeter(self):
        for seat in ('seat1','seat0'):
            bus=Bus();base=bus.properties()
            bus.call=lambda *args:[('g1',42,'greeter','seat0','/greeter'),('g2',42,'greeter',seat,'/other')]
            bus.properties=lambda path,*args:dict(base,Id='g2',Seat=(seat,'/seat')) if path=='/other' else base
            with self.assertRaises(PermissionError):greeter_context(bus,isolate_uid=True)

    def test_isolated_gdm_uid_allows_its_non_graphical_user_manager(self):
        bus=Bus();base=bus.properties()
        bus.call=lambda *args:[('g1',42,'greeter','seat0','/greeter'),('m1',42,'greeter','','/manager')]
        bus.properties=lambda path,*args:dict(base,Id='m1',Class='manager-early',Type='unspecified',Seat=('','/')) if path=='/manager' else base
        self.assertEqual(greeter_context(bus,isolate_uid=True),dict(session='g1',greeter_uid=42))
