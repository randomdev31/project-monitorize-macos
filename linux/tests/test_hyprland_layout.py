import copy
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from monitorize.platform.hyprland_layout import HyprlandLayout
from monitorize.platform.session_layout import LayoutTransaction

class SimulatedHyprland(HyprlandLayout):
    def __init__(self):
        self.monitors=[dict(name='eDP-1',width=2560,height=1600,refreshRate=120,scale=1.5,x=10,y=0,focused=True,disabled=False),dict(name='Virtual-1',width=1920,height=1080,refreshRate=60,scale=1,x=2570,y=0,focused=False,disabled=False)]
        self.commands=[]
    def run(self,*args):
        self.commands.append(args)
        if args==('-j','monitors','all'):return json.dumps(self.monitors)
        if args[0]=='eval':raise subprocess.CalledProcessError(1,args)
        if args[:2]==('keyword','monitor'):
            name,rule=args[2].split(',',1);monitor=next(o for o in self.monitors if o['name']==name)
            monitor['disabled']=rule=='disable'
            if rule != 'disable' and not rule.startswith('preferred'):
                mode,pos,scale,*extra=rule.split(',')
                dimensions,refresh=mode.split('@');width,height=dimensions.split('x');x,y=pos.split('x')
                monitor.update(width=int(width),height=int(height),refreshRate=float(refresh),x=int(x),y=int(y),scale=float(scale))
                if extra:monitor['transform']=int(extra[1])
        elif args[:2]==('dispatch','focusmonitor'):
            for monitor in self.monitors:monitor['focused']=monitor['name']==args[2]
        else:raise AssertionError(args)
        return 'ok'

class HyprlandLayoutTests(unittest.TestCase):
    def test_vkms_rejects_old_or_unverifiable_aquamarine_before_changes(self):
        for version in ('0.15.0','unknown',''):
            backend=HyprlandLayout()
            with self.subTest(version=version),patch.object(backend,'run',return_value=json.dumps({'systemAquamarine':version})):
                with self.assertRaisesRegex(RuntimeError,'Aquamarine'):backend.require_vkms_lifecycle()

    def test_vkms_accepts_supported_running_aquamarine(self):
        for version in ('0.15.1','0.16.0','1.0.0'):
            with self.subTest(version=version),patch.object(HyprlandLayout,'run',return_value=json.dumps({'systemAquamarine':version,'buildAquamarine':'0.15.0'})):
                HyprlandLayout().require_vkms_lifecycle()
    def test_virtual_only_restores_original_mode_scale_position(self):
        with tempfile.TemporaryDirectory() as directory:
            backend=SimulatedHyprland();layout=LayoutTransaction(backend,Path(directory)/'journal','virtual_only')
            with patch('monitorize.platform.session_layout.output_identity',return_value='same'),patch('monitorize.platform.hyprland_layout.output_identity',return_value='same'):
                layout.reserve(1,('Virtual-1',));layout.ready(1,'Virtual-1');layout.stream(1,True)
                self.assertTrue(backend.monitors[0]['disabled'])
                layout.release(1)
            self.assertFalse(backend.monitors[0]['disabled'])
            self.assertTrue(backend.monitors[0]['focused'])
            self.assertIn(('keyword','monitor','eDP-1,2560x1600@120,10x0,1.5,transform,0'),backend.commands)
    def test_primary_focus_does_not_disable_physical_screen(self):
        backend=SimulatedHyprland();snapshot=[dict(name='eDP-1',enabled=True)]
        backend.policy('primary',snapshot,{1:'Virtual-1'})
        self.assertFalse(backend.monitors[0]['disabled']);self.assertTrue(backend.monitors[1]['focused'])
    def test_invalid_monitor_geometry_or_name_is_rejected(self):
        backend=SimulatedHyprland();backend.monitors[0]['name']='eDP-1,disable'
        with self.assertRaises(ValueError):backend.outputs()
        backend.monitors[0]['name']='eDP-1';backend.monitors[0]['scale']=float('nan')
        with self.assertRaises(ValueError):backend.outputs()

    def test_lua_configuration_and_focus_use_current_api(self):
        backend=HyprlandLayout()
        with patch.object(backend,'run',return_value='ok') as run:
            backend.monitor('eDP-1',disabled=True)
            self.assertIn('disabled = true',run.call_args.args[1])
            self.assertEqual(run.call_args.args[0],'eval')
            backend.focus('Virtual-1')
            self.assertIn('hl.dsp.focus',run.call_args.args[1])

    def test_timeout_does_not_replay_a_possibly_applied_mutation(self):
        backend=HyprlandLayout()
        with patch.object(backend,'run',side_effect=subprocess.TimeoutExpired('hyprctl',4)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):backend.monitor('eDP-1',disabled=True)
            self.assertEqual(run.call_count,1)
