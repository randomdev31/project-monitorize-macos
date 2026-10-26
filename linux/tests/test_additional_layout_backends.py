"""Output-state and recovery contracts; no live compositor commands are run."""
import copy
import json
import os
from pathlib import Path
import tempfile
import socket
import subprocess
import unittest
from unittest.mock import patch

from monitorize.platform.session_layout import LayoutTransaction, layout_modes, current_layout_backend, guarded_holder_supported
from monitorize.platform.xrandr_layout import XrandrLayout, parse_outputs, resolve_output, IDENTITY_TRANSFORM
from monitorize.platform.niri_layout import NiriLayout


def xoutput(name, enabled=True, primary=False):
    return dict(name=name, connected=True, enabled=enabled, priority=1 if primary else 2,
                primary=primary, mode='1920x1080', rate=60., pos={'x':0,'y':0},
                rotation='normal', reflect='normal', transform=list(IDENTITY_TRANSFORM),
                identity=name, connector_id=None)


class XServer(XrandrLayout):
    def __init__(self):
        self.state = [xoutput('eDP-1', primary=True), xoutput('HDMI-1'), xoutput('DP-1', False)]
        self.commands = []; self.fail_restore = False; self.ignore_disable = False

    def outputs(self):
        return copy.deepcopy(self.state)

    def run(self, *args):
        self.commands.append(args); target=None; i=0
        while i < len(args):
            arg=args[i]; i+=1
            if arg=='--output':
                target=next(o for o in self.state if o['name']==args[i]); i+=1
            elif arg=='--off':
                if not self.ignore_disable:target['enabled']=False
            elif arg=='--noprimary':
                for o in self.state:o['primary']=False
            elif arg=='--primary':
                for o in self.state:o['primary']=o is target
            elif arg=='--auto':target['enabled']=True
            else:
                value=args[i]; i+=1
                if self.fail_restore:raise RuntimeError('X server refused restoration')
                if arg=='--mode':target.update(mode=value, enabled=True)
                elif arg=='--rate':target['rate']=float(value)
                elif arg=='--pos':
                    x,y=value.split('x');target['pos']={'x':int(x),'y':int(y)}
                elif arg=='--rotate':target['rotation']=value
                elif arg=='--reflect':target['reflect']=value
                elif arg=='--transform':target['transform']=[float(v) for v in value.split(',')]
                else:raise AssertionError(arg)
        return ''


class NiriServer(NiriLayout):
    def __init__(self):
        super().__init__()
        self.state = {name:dict(name=name,make='maker',model=name,serial=name,
            modes=[dict(width=1920,height=1080,refresh_rate=60000,is_preferred=True)],
            current_mode=0 if enabled else None,logical=dict(x=x,y=0,width=1920,height=1080,scale=1.,transform='Normal') if enabled else None)
            for name,enabled,x in [('eDP-1',True,0),('HDMI-1',True,1920),('DP-1',False,0)]}
        self.focus='eDP-1';self.commands=[];self.fail_restore=False;self.ignore_disable=False
        self.config={n:copy.deepcopy(o['logical'] or dict(x=0,y=0,width=1920,height=1080,scale=1.,transform='Normal')) for n,o in self.state.items()}

    def add_virtual(self, name):
        value=copy.deepcopy(self.state['eDP-1']);value.update(name=name,serial=name,current_mode=0,logical=copy.deepcopy(self.config['eDP-1']))
        self.state[name]=value;self.config[name]=copy.deepcopy(value['logical'])

    def run(self, *args):
        if args==('outputs',):return copy.deepcopy(self.state)
        if args==('focused-output',):return copy.deepcopy(self.state.get(self.focus))
        self.commands.append(args)
        if args[:2]==('action','focus-monitor'):
            self.focus=args[2];return None
        _,name,action,*values=args;output=self.state[name];logical=self.config[name]
        if action=='off':
            if not self.ignore_disable:output.update(current_mode=None,logical=None)
        else:
            if self.fail_restore:raise RuntimeError('Niri refused restoration')
            if action=='mode':self.assert_mode=values[0]
            elif action=='scale':logical['scale']=float(values[0])
            elif action=='transform':
                from monitorize.platform.niri_layout import TRANSFORMS
                logical['transform']=next(k for k,v in TRANSFORMS.items() if v==values[0])
            elif action=='position':
                if values[:2] != ['set','--'] or len(values) != 4:raise AssertionError('Niri positional x/y need -- for negative coordinates')
                logical.update(x=int(values[2]),y=int(values[3]))
            elif action=='on':output.update(current_mode=0,logical=copy.deepcopy(logical))
            else:raise AssertionError(args)
            if output['current_mode'] is not None:output['logical']=copy.deepcopy(logical)
        return None


class BackendRecoveryTests(unittest.TestCase):
    def backends(self):return [XServer(),NiriServer()]

    def test_niri_restores_monitor_left_of_and_above_origin(self):
        backend=NiriServer()
        backend.config['HDMI-1'].update(x=-1920,y=-1080)
        backend.state['HDMI-1']['logical']=copy.deepcopy(backend.config['HDMI-1'])
        baseline=backend.snapshot(backend.outputs(),())
        backend.add_virtual('Virtual-1');backend.policy('virtual_only',baseline,{1:'Virtual-1'})
        backend.restore(baseline,['Virtual-1'])
        self.assertEqual(backend.state['HDMI-1']['logical']['x'],-1920)
        self.assertIn(('output','HDMI-1','position','set','--','-1920','-1080'),backend.commands)

    def add_virtual(self, backend, name):
        if isinstance(backend,XServer):backend.state.append(xoutput(name))
        else:backend.add_virtual(name)

    def test_two_clients_restore_only_after_last_stream_and_reconnect(self):
        for backend in self.backends():
            with self.subTest(backend=type(backend).__name__),tempfile.TemporaryDirectory() as tmp:
                transaction=LayoutTransaction(backend,Path(tmp)/'journal','virtual_only')
                transaction.reserve(1)
                self.add_virtual(backend,'Virtual-1');transaction.ready(1,'Virtual-1')
                self.assertEqual(backend.commands,[])
                transaction.stream(1,True)
                self.assertFalse(next(o for o in backend.outputs() if o['name']=='eDP-1')['enabled'])
                transaction.reserve(2);self.add_virtual(backend,'Virtual-2');transaction.ready(2,'Virtual-2')
                transaction.stream(2,True);transaction.stream(1,False)
                self.assertFalse(next(o for o in backend.outputs() if o['name']=='HDMI-1')['enabled'])
                transaction.stream(2,False)
                state={o['name']:o for o in backend.outputs()}
                self.assertTrue(state['eDP-1']['enabled']);self.assertTrue(state['HDMI-1']['enabled'])
                self.assertFalse(state['DP-1']['enabled']);self.assertTrue(state['Virtual-2']['enabled'])
                transaction.stream(1,True)
                self.assertFalse(next(o for o in backend.outputs() if o['name']=='eDP-1')['enabled'])
                transaction.release(1);transaction.release(2)
                self.assertFalse(transaction.journal.exists())

    def test_failed_restore_retains_owned_output_and_durable_journal(self):
        for backend in self.backends():
            with self.subTest(backend=type(backend).__name__),tempfile.TemporaryDirectory() as tmp:
                transaction=LayoutTransaction(backend,Path(tmp)/'journal','virtual_only')
                transaction.reserve(1);self.add_virtual(backend,'Virtual-1');transaction.ready(1,'Virtual-1');transaction.stream(1,True)
                backend.fail_restore=True
                with self.assertRaises(RuntimeError):transaction.release(1)
                self.assertTrue(transaction.journal.exists());self.assertEqual(transaction.targets[1],'Virtual-1')
                self.assertTrue(next(o for o in backend.outputs() if o['name']=='Virtual-1')['enabled'])

    def test_restart_replays_original_layout(self):
        for backend in self.backends():
            with self.subTest(backend=type(backend).__name__),tempfile.TemporaryDirectory() as tmp:
                journal=Path(tmp)/'journal';transaction=LayoutTransaction(backend,journal,'virtual_only')
                transaction.reserve(1);self.add_virtual(backend,'Virtual-1');transaction.ready(1,'Virtual-1');transaction.stream(1,True)
                LayoutTransaction(backend,journal,'virtual_only').recover()
                self.assertFalse(journal.exists())
                self.assertTrue(next(o for o in backend.outputs() if o['name']=='eDP-1')['enabled'])

    def test_ignored_disable_is_detected_and_layout_restored(self):
        for backend in self.backends():
            with self.subTest(backend=type(backend).__name__),tempfile.TemporaryDirectory() as tmp,patch('time.sleep'):
                transaction=LayoutTransaction(backend,Path(tmp)/'journal','virtual_only');transaction.reserve(1)
                self.add_virtual(backend,'Virtual-1');transaction.ready(1,'Virtual-1');backend.ignore_disable=True
                with self.assertRaisesRegex(RuntimeError,'not confirmed'):transaction.stream(1,True)
                self.assertTrue(next(o for o in backend.outputs() if o['name']=='eDP-1')['enabled'])


class XrandrIdentityTests(unittest.TestCase):
    def test_explicit_physical_mirror_without_connector_property_keeps_working(self):
        state=parse_outputs('eDP-1 connected primary 1920x1080+0+0\n 1920x1080 60.00*+\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'card0-eDP-1';path.mkdir();(path/'connector_id').write_text('41')
            self.assertEqual(resolve_output('eDP-1',state,Path(tmp)),'eDP-1')
            state[0]['connector_id']=42
            with self.assertRaises(ValueError):resolve_output('eDP-1',state,Path(tmp))

    def test_owned_virtual_monitor_without_connector_property_is_not_guessed(self):
        state=parse_outputs('Virtual-1 connected 1920x1080+0+0\n 1920x1080 60.00*+\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'card0-Virtual-1';path.mkdir();(path/'connector_id').write_text('41')
            with self.assertRaises(ValueError):resolve_output('Virtual-1',state,Path(tmp))
    def test_connector_id_wins_over_a_different_output_with_the_same_name(self):
        listing='Virtual-1 connected primary 1920x1080+0+0\n\tCONNECTOR_ID: 39\n 1920x1080 60.00*+\nVirtual-1-2 connected 2340x1080+1920+0\n\tCONNECTOR_ID: 41\n 2340x1080 60.00*+\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'card0-Virtual-1';path.mkdir();(path/'connector_id').write_text('41')
            self.assertEqual(resolve_output('Virtual-1',parse_outputs(listing),Path(tmp)),'Virtual-1-2')

    def test_ambiguous_connector_id_cannot_select_another_monitor(self):
        state=parse_outputs('a connected 1920x1080+0+0\n CONNECTOR_ID: 41\nb connected 1920x1080+0+0\n CONNECTOR_ID: 41\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'card0-Virtual-1';path.mkdir();(path/'connector_id').write_text('41')
            with self.assertRaisesRegex(ValueError,'one active'):resolve_output('Virtual-1',state,Path(tmp))

    def test_verbose_transform_is_saved_and_panning_is_rejected(self):
        backend=XrandrLayout();query='eDP-1 connected primary 1920x1080+0+0\n 1920x1080 60.00*+\n'
        verbose='eDP-1 connected primary 1920x1080+0+0\n Transform: 1.5 0 0\n 0 1.5 0\n 0 0 1\n'
        with patch.object(backend,'run',side_effect=[query,verbose]):
            self.assertEqual(backend.outputs()[0]['transform'][0],1.5)
        with patch.object(backend,'run',side_effect=[query,verbose+' Panning: 2000x1200+0+0\n']):
            with self.assertRaisesRegex(ValueError,'panning'):backend.outputs()

    def test_replaced_monitors_do_not_receive_stale_geometry(self):
        backend=XServer()
        with tempfile.TemporaryDirectory() as tmp:
            transaction=LayoutTransaction(backend,Path(tmp)/'journal','virtual_only');transaction.reserve(1)
            backend.state.append(xoutput('Virtual-1'));transaction.ready(1,'Virtual-1');transaction.stream(1,True)
            for output in backend.state:
                if output['name'] in ('eDP-1','HDMI-1','DP-1'):output['connected']=False
            backend.state.append(xoutput('new-screen',False));backend.commands=[]
            transaction.release(1)
            self.assertIn(('--output','new-screen','--auto','--output','new-screen','--primary'),backend.commands)


class CapabilityTests(unittest.TestCase):
    def test_hyprland_environment_without_a_desktop_label_selects_hyprland(self):
        from monitorize.platform.hyprland_layout import HyprlandLayout
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'wayland','HYPRLAND_INSTANCE_SIGNATURE':'verified-instance'},clear=True):
            self.assertIsInstance(current_layout_backend(),HyprlandLayout)

    def test_generic_x11_and_niri_get_only_extend_and_virtual_only(self):
        for desktop,environment in [('x11',{'XDG_SESSION_TYPE':'x11','DISPLAY':':0'}),('niri',{'XDG_SESSION_TYPE':'wayland','NIRI_SOCKET':'/run/user/test/niri'})]:
            with self.subTest(desktop=desktop),patch.dict(os.environ,environment,clear=True),patch('shutil.which',return_value='/bin/tool'),patch('os.path.isfile',return_value=False):
                self.assertEqual(layout_modes(desktop),('extend','virtual_only'))
                self.assertTrue(guarded_holder_supported(desktop,'vkms'));self.assertFalse(guarded_holder_supported(desktop,'native'))
                self.assertIsInstance(current_layout_backend(),XrandrLayout if desktop=='x11' else NiriLayout)

    def test_kde_and_gnome_wayland_choices_are_preserved(self):
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'wayland'},clear=True),patch('shutil.which',return_value='/bin/tool'),patch('os.path.isfile',return_value=False):
            for desktop in ('kde','gnome','hyprland'):
                self.assertEqual(layout_modes(desktop),('extend','primary','virtual_only'))
            self.assertTrue(guarded_holder_supported('hyprland','native'));self.assertTrue(guarded_holder_supported('hyprland','vkms'))
            self.assertFalse(guarded_holder_supported('gnome','native'))

    def test_missing_tools_flatpak_and_xwayland_are_not_enabled(self):
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'wayland','DISPLAY':':0'},clear=True),patch('shutil.which',return_value='/bin/tool'),patch('os.path.isfile',return_value=False):
            self.assertEqual(layout_modes('x11'),('extend',))
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'x11','DISPLAY':':0'},clear=True),patch('shutil.which',return_value=None),patch('os.path.isfile',return_value=False):
            self.assertEqual(layout_modes('x11'),('extend',))
        with patch('os.path.isfile',return_value=True):self.assertEqual(layout_modes('kde'),('extend',))


class NiriCommandTests(unittest.TestCase):
    def test_replaced_ipc_socket_is_rejected_before_any_command(self):
        from types import SimpleNamespace
        import stat
        backend=NiriLayout()
        values=[SimpleNamespace(st_mode=stat.S_IFSOCK|0o600,st_uid=os.getuid(),st_dev=1,st_ino=i) for i in (11,12)]
        with patch('monitorize.platform.niri_layout.Path.stat',side_effect=values),patch('monitorize.platform.niri_layout.subprocess.run',return_value=subprocess.CompletedProcess([],0,'{}','')) as command:
            backend.run('outputs')
            with self.assertRaisesRegex(RuntimeError,'changed'):backend.run('output','eDP-1','off')
            self.assertEqual(command.call_count,1)

    def test_successful_focus_action_has_no_json_reply(self):
        with tempfile.TemporaryDirectory() as tmp,socket.socket(socket.AF_UNIX) as server:
            path=str(Path(tmp)/'niri');server.bind(path)
            with patch.dict(os.environ,{'NIRI_SOCKET':path}),patch('monitorize.platform.niri_layout.subprocess.run',return_value=subprocess.CompletedProcess([],0,'','')):
                self.assertIsNone(NiriLayout().run('action','focus-monitor','eDP-1'))

    def test_output_query_cannot_succeed_with_an_empty_reply(self):
        with tempfile.TemporaryDirectory() as tmp,socket.socket(socket.AF_UNIX) as server:
            path=str(Path(tmp)/'niri');server.bind(path)
            with patch.dict(os.environ,{'NIRI_SOCKET':path}),patch('monitorize.platform.niri_layout.subprocess.run',return_value=subprocess.CompletedProcess([],0,'','')):
                with self.assertRaises(ValueError):NiriLayout().run('outputs')
