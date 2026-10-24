"""Primary selection uses compositor state, never activates a virtual output."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from monitorize.remote_login import login_primary as primary

def monitor(name,w=1920,h=1080,rate=59.96,current=True):
    return [(name,'Vendor','Model','Serial'),[('mode',w,h,rate,1.0,[1.0],{'is-current':current})],{}]
def layout(*monitors,primary_name='eDP-1'):
    return (1,list(monitors),[(0,0,1.0,0,True,[(primary_name,'Vendor','Model','Serial')],{})],{})

class SelectionTests(unittest.TestCase):
    def test_uses_primary_instead_of_first_or_virtual_secondary_and_keeps_actual_mode(self):
        state=layout(monitor('Virtual-2'),monitor('eDP-1',2560,1600,59.94))
        self.assertEqual(primary.select_primary(state),dict(output_name='eDP-1',capture='kms',width=2560,height=1600,fps=59.94))
    def test_rejects_missing_multiple_primary_inactive_ambiguous_and_invalid_modes(self):
        good=layout(monitor('eDP-1'))
        states=[(1,good[1],[],{}),(1,good[1],good[2]*2,{}),layout(monitor('eDP-1',current=False)),layout(monitor('eDP-1'),monitor('eDP-1')),layout(monitor('../unsafe')),layout(monitor('eDP-1',rate=float('nan'))),layout(monitor('eDP-1',w=0))]
        for state in states:
            with self.subTest(state=state),self.assertRaises((ValueError,PermissionError)):primary.select_primary(state)
    def test_mirrored_primary_can_capture_one_existing_output(self):
        state=layout(monitor('eDP-1'),monitor('HDMI-A-1'))
        state[2][0][5].append(('HDMI-A-1','Vendor','Model','Serial'))
        self.assertEqual(primary.select_primary(state)['output_name'],'eDP-1')

class OperationTests(unittest.TestCase):
    def test_idle_does_not_disconnect_or_reconfigure_existing_primary(self):
        helper=Mock();check=Mock()
        result=primary.operation(SimpleNamespace(manager='gdm.service'),{},'idle',helper,check)
        self.assertEqual(result,{})
        check.assert_called();self.assertEqual(helper.mock_calls,[])
    def test_only_gdm_prepare_and_idle_are_supported(self):
        for manager,operation in [('sddm.service','prepare'),('gdm.service','activate')]:
            with self.subTest(manager=manager,operation=operation),self.assertRaises(ValueError):
                primary.operation(SimpleNamespace(manager=manager),{},operation,Mock(),Mock())

class DrmTests(unittest.TestCase):
    def test_requires_one_enabled_existing_connector_without_changing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'card0-eDP-1';output.mkdir()
            (output/'enabled').write_text('enabled');(output/'status').write_text('connected')
            target=dict(output_name='eDP-1',capture='kms',width=1920,height=1080,fps=60)
            primary.verify_drm(target,root=root)
            self.assertEqual((output/'enabled').read_text(),'enabled')
            second=root/'card1-eDP-1';second.mkdir()
            (second/'enabled').write_text('enabled');(second/'status').write_text('connected')
            with self.assertRaises(PermissionError):primary.verify_drm(target,root=root)
            second.rename(root/'card1-DP-1');(output/'enabled').write_text('disabled')
            with self.assertRaises(PermissionError):primary.verify_drm(target,root=root)


class AuthenticatedOperationTests(unittest.TestCase):
    def prepare(self,*,owner=123,peers=(123,123),response=None,name='eDP-1',canonical=None):
        import json,os
        uid=os.getuid();environment=dict(XDG_SESSION_TYPE='wayland',XDG_RUNTIME_DIR='/run/user/'+str(uid),WAYLAND_DISPLAY='wayland-0')
        target=dict(output_name=name,capture='kms',width=2560,height=1600,fps=59.94)
        result=SimpleNamespace(returncode=0,stdout=response if response is not None else json.dumps(dict(pid=owner,target=target)))
        helper=Mock();check=Mock()
        with patch('monitorize.remote_login.gdm_context.verify',return_value=environment) as verify,patch('monitorize.remote_login.gdm_context.socket_owner',side_effect=peers),patch.object(primary.subprocess,'run',return_value=result) as run,patch.object(primary,'verify_drm',return_value=Path('/sys/class/drm/card0-'+(canonical or name))) as drm:
            actual=primary.operation(SimpleNamespace(manager='gdm.service'),dict(session='g1',greeter_uid=uid),'prepare',helper,check)
            self.assertEqual(actual,dict(target,output_name=canonical or name))
            self.assertEqual(run.call_args.kwargs['user'],uid)
            self.assertEqual(helper.mock_calls,[])
            self.assertEqual(verify.call_count,2);self.assertEqual(drm.call_count,2)
        return actual
    def test_prepare_captures_authenticated_primary_without_virtual_operations(self):self.prepare()
    def test_returns_canonical_kms_connector_for_hdmi(self):self.prepare(name='HDMI-1',canonical='HDMI-A-1')
    def test_mismatched_bus_owner_socket_replacement_and_oversized_query_are_rejected(self):
        for kwargs in (dict(owner=999),dict(peers=(123,999)),dict(response='x'*4097)):
            with self.subTest(kwargs=kwargs),self.assertRaises((ValueError,PermissionError)):self.prepare(**kwargs)

class RoutingTests(unittest.TestCase):
    def test_opted_in_greeter_never_enters_virtual_prepare_or_idle(self):
        from monitorize.remote_login import wayland_greeter
        settings=SimpleNamespace(login_primary_display=True,manager='gdm.service')
        for operation in ('prepare','idle'):
            virtual=Mock(side_effect=AssertionError('must not create or remove a virtual display'))
            with patch.object(primary,'operation',return_value={'output_name':'eDP-1'}) as existing:
                target=wayland_greeter.capture_operation(settings,{},operation,Mock(),Mock(),virtual)
            self.assertEqual(target['output_name'],'eDP-1');existing.assert_called_once();virtual.assert_not_called()
    def test_default_and_explicit_off_keep_existing_virtual_lifecycle(self):
        from monitorize.remote_login import wayland_greeter
        for settings in (SimpleNamespace(),SimpleNamespace(login_primary_display=False)):
            virtual=Mock(return_value={'output_name':'Virtual-2'})
            with patch.object(primary,'operation') as existing:
                self.assertEqual(wayland_greeter.capture_operation(settings,{},'prepare',Mock(),Mock(),virtual)['output_name'],'Virtual-2')
            virtual.assert_called_once();existing.assert_not_called()


class PrimarySnapshotTests(unittest.TestCase):
    def test_primary_switch_during_selection_is_rejected(self):
        # Same authenticated compositor, but its primary output changed while
        # root verified the session/socket. Do not capture the old secondary.
        import json,os
        uid=os.getuid();environment=dict(XDG_SESSION_TYPE='wayland',XDG_RUNTIME_DIR='/run/user/'+str(uid),WAYLAND_DISPLAY='wayland-0')
        first=dict(output_name='eDP-1',capture='kms',width=1920,height=1080,fps=60)
        second=dict(first,output_name='HDMI-A-1')
        results=[SimpleNamespace(returncode=0,stdout=json.dumps(dict(pid=123,target=t))) for t in (first,second)]
        with patch('monitorize.remote_login.gdm_context.verify',return_value=environment),patch('monitorize.remote_login.gdm_context.socket_owner',return_value=123),patch.object(primary.subprocess,'run',side_effect=results),patch.object(primary,'verify_drm'):
            with self.assertRaisesRegex(PermissionError,'primary display changed'):
                primary.operation(SimpleNamespace(manager='gdm.service'),dict(session='g1',greeter_uid=uid),'prepare',Mock(),Mock())

class ConnectorNamingTests(unittest.TestCase):
    def test_mutter_hdmi_name_resolves_to_the_canonical_kms_connector(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'card0-HDMI-A-1';output.mkdir()
            (output/'enabled').write_text('enabled');(output/'status').write_text('connected')
            target=primary.select_primary(layout(monitor('HDMI-1'),primary_name='HDMI-1'))
            self.assertEqual(primary.verify_drm(target,root=root),output)
    def test_alias_never_selects_arbitrarily_between_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for card in ('card0','card1'):
                output=root/(card+'-HDMI-A-1');output.mkdir()
                (output/'enabled').write_text('enabled');(output/'status').write_text('connected')
            target=dict(output_name='HDMI-1',capture='kms',width=1920,height=1080,fps=60)
            with self.assertRaises(PermissionError):primary.verify_drm(target,root=root)
