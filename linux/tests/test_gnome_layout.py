import copy
from pathlib import Path
import tempfile
import unittest
from monitorize.platform.gnome_layout import GnomeLayout
from monitorize.platform.session_layout import LayoutTransaction


def monitor(name,primary=False,width=1920,scale=1):
    return ((name,'vendor','product',name),[('mode',width,1080,60.,scale,[scale],{'is-current':True,'is-preferred':True})],{})


class Mutter:
    def __init__(self):
        self.serial=1;self.allowed=True;self.calls=[]
        self.monitors=[monitor('eDP-1',scale=1.25),monitor('Virtual-1')]
        self.logical=[(0,0,1.25,0,True,[self.monitors[0][0]],{}),(1536,0,1.,0,False,[self.monitors[1][0]],{})]
    def GetCurrentState(self,**kwargs):return self.serial,self.monitors,self.logical,{'layout-mode':1,'supports-changing-layout-mode':True}
    def Get(self,*args,**kwargs):return self.allowed
    def ApplyMonitorsConfig(self,serial,method,groups,options,**kwargs):
        if int(serial)!=self.serial:raise RuntimeError('stale')
        self.calls.append((int(method),copy.deepcopy(groups)))
        self.logical=[(int(x),int(y),float(scale),int(transform),bool(primary),
            [next(m[0] for m in self.monitors if m[0][0]==name) for name,_mode,_props in members],{})
            for x,y,scale,transform,primary,members in groups]
        self.serial+=1


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.mutter=Mutter();self.layout=GnomeLayout(self.mutter)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.transaction=LayoutTransaction(self.layout,Path(self.temp.name)/'journal','virtual_only')
    def attach(self):self.transaction.reserve(1,('Virtual-1',));self.transaction.ready(1,'Virtual-1')
    def test_virtual_only_and_guardian_restore_original_scale_primary(self):
        self.attach();self.transaction.stream(1,True)
        self.assertEqual([o['name'] for o in self.layout.outputs() if o['enabled']],['Virtual-1'])
        self.transaction.release(1)
        outputs={o['name']:o for o in self.layout.outputs()}
        self.assertTrue(outputs['eDP-1']['enabled']);self.assertEqual(outputs['eDP-1']['priority'],1)
        self.assertEqual(outputs['eDP-1']['scale'],1.25)
        self.assertTrue(all(call[0]==1 for call in self.mutter.calls))
    def test_primary_retains_physical(self):
        self.transaction.mode='primary';self.attach();self.transaction.stream(1,True)
        outputs={o['name']:o for o in self.layout.outputs()}
        self.assertTrue(outputs['eDP-1']['enabled']);self.assertEqual(outputs['Virtual-1']['priority'],1)
    def test_crash_journal_preserves_clone_group(self):
        extra=monitor('HDMI-1',scale=1.25);self.mutter.monitors.append(extra)
        self.mutter.logical[0][5].append(extra[0])
        self.attach();self.transaction.stream(1,True)
        LayoutTransaction(self.layout,self.transaction.journal,'primary').recover()
        physical=[g for g in self.mutter.logical if g[4]][0]
        self.assertEqual({s[0] for s in physical[5]},{'eDP-1','HDMI-1'})
    def test_denied_configuration_makes_no_changes(self):
        self.attach();self.mutter.allowed=False
        with self.assertRaisesRegex(RuntimeError,'does not permit'):self.transaction.stream(1,True)
        self.assertEqual(self.mutter.calls,[])
    def test_unplugged_physical_preserves_virtual_and_journal(self):
        self.attach();self.transaction.stream(1,True)
        self.mutter.monitors=[self.mutter.monitors[1]]
        with self.assertRaisesRegex(RuntimeError,'retaining virtual'):self.transaction.release(1)
        self.assertTrue(self.transaction.journal.exists())
    def test_invalid_saved_scale_cannot_remove_virtual(self):
        self.attach();self.transaction.stream(1,True)
        self.transaction.snapshot[0]['layout_group']['scale']=9
        with self.assertRaisesRegex(RuntimeError,'scale'):self.transaction.release(1)
        self.assertEqual([o['name'] for o in self.layout.outputs() if o['enabled']],['Virtual-1'])

    def test_changed_coordinate_mode_blocks_geometry_replay(self):
        self.attach();self.transaction.stream(1,True)
        self.transaction.snapshot[0]['layout_mode']=2
        with self.assertRaisesRegex(RuntimeError,'coordinate layout mode'):
            self.transaction.release(1)
        self.assertTrue(self.transaction.journal.exists())

    def test_compositor_refusing_primary_is_detected_and_restored(self):
        self.transaction.mode='primary';self.attach()
        original=self.mutter.ApplyMonitorsConfig
        def ignore_once(serial,method,groups,options,**kwargs):
            if not self.mutter.calls:
                self.mutter.calls.append(('ignored',[]));return
            return original(serial,method,groups,options,**kwargs)
        self.mutter.ApplyMonitorsConfig=ignore_once
        with self.assertRaisesRegex(RuntimeError,'could not be verified'):
            self.transaction.stream(1,True)
        self.assertTrue(self.layout.outputs()[0]['enabled'])
        self.assertEqual(self.layout.outputs()[0]['priority'],1)
