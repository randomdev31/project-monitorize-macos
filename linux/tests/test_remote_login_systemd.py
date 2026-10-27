import unittest
from monitorize.remote_login.systemd import EngineUnits


class Transport:
    def __init__(self):self.calls=[];self.active='inactive'
    def call(self,path,interface,method,*args):
        self.calls.append((method,args))
        if method=='GetUnit':return '/unit'
        return '/job'
    def properties(self,path,interface):return {'ActiveState':self.active,'ControlGroup':''}


class UnitTests(unittest.TestCase):
    def test_fixed_unit_names_and_no_client_commands(self):
        bus=Transport();units=EngineUnits(1000,bus,lambda:True,lambda *args:None)
        units.start('boot');units.stop('desktop')
        self.assertEqual(bus.calls,[('StartUnit',('monitorize-remote-login-boot@1000.service','replace')),
                                   ('StopUnit',('monitorize-remote-login-desktop@1000.service','replace'))])
        for phase in ('other','boot; rm -rf','../boot'):
            with self.assertRaises(ValueError):units.start(phase)

    def test_deactivating_is_not_exit(self):
        bus=Transport();units=EngineUnits(1000,bus,lambda:True,lambda *args:None)
        for state in ('active','activating','deactivating','reloading'):
            bus.active=state;self.assertTrue(units.running('boot'))
        bus.active='inactive';self.assertFalse(units.running('boot'))

    def test_invalid_uid_is_rejected(self):
        for uid in (0,-1,True,'1000'):
            with self.assertRaises(ValueError):EngineUnits(uid,None,None,None)

    def test_descriptor_write_is_delegated_only_to_fixed_callback(self):
        calls=[];units=EngineUnits(1000,Transport(),lambda:False,lambda *args:calls.append(args))
        self.assertFalse(units.identity_free())
        units.prepare_desktop({'uid':1000,'session':'s1'},'generation',{'capture':'kms'})
        self.assertEqual(len(calls),1)

    def test_inactive_service_still_waits_for_populated_cgroup(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            group=Path(d)/'engine';group.mkdir();events=group/'cgroup.events';events.write_text('populated 1\n')
            bus=Transport()
            bus.properties=lambda path,interface:({'ActiveState':'inactive'} if interface.endswith('.Unit') else {'ControlGroup':'/engine'})
            units=EngineUnits(1000,bus,lambda:True,lambda *args:None,cgroup_root=Path(d))
            self.assertTrue(units.running('desktop'))
            events.write_text('populated 0\n');self.assertFalse(units.running('desktop'))
