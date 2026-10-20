import json
import unittest
from unittest.mock import patch
from monitorize.desktop.remote_login_runtime import Participant


class Interface:
    def __init__(self):self.state='waiting_for_desktop';self.calls=[]
    def GetStatus(self,**kwargs):return json.dumps({'state':self.state,'capture_ready':self.state=='desktop_available'})
    def AcquireDesktop(self,**kwargs):self.calls.append('acquire');return json.dumps({'granted':True,'generation':'a'*32})
    def PrepareDesktop(self,token,descriptor,**kwargs):
        self.calls.append(('prepare',json.loads(descriptor)));self.state='desktop_starting';return self.GetStatus()
    def Stop(self,token,**kwargs):self.calls.append('stop');self.state='stopped';return self.GetStatus()
    def Start(self,**kwargs):self.calls.append('start');self.state='waiting_for_desktop';return self.GetStatus()
    def ReleaseDesktop(self,token,**kwargs):return 'true'


class ParticipantTests(unittest.TestCase):
    def test_removed_output_can_restart_listener_from_reserved_service_identity(self):
        interface=Interface()
        original=interface.GetStatus
        interface.GetStatus=lambda **kwargs:json.dumps({**json.loads(original()),'output_name':'Virtual-4'})
        participant=Participant(factory=lambda:interface,output_finder=lambda:None)
        participant.poll()
        self.assertIn(('prepare',{'capture':'kms','output_name':'Virtual-4'}),interface.calls)

    def test_adoption_can_request_connected_output_before_compositor_enables_it(self):
        interface=Interface()
        with patch('monitorize.desktop.remote_login_runtime.find_boot_output',return_value='Virtual-4') as finder:
            participant=Participant(factory=lambda:interface)
            participant.poll()
        finder.assert_called_once_with(require_enabled=False)
        self.assertIn(('prepare',{'capture':'kms','output_name':'Virtual-4'}),interface.calls)

    def test_one_sender_and_no_duplicate_prepare(self):
        interface=Interface();connections=[]
        def factory():connections.append(1);return interface
        participant=Participant(factory=factory,output_finder=lambda:'Virtual-4')
        participant.poll();participant.poll()
        self.assertEqual(len(connections),1)
        self.assertEqual(interface.calls,['acquire',('prepare',{'capture':'kms','output_name':'Virtual-4'})])

    def test_stop_survives_polling_and_start_is_explicit(self):
        interface=Interface();participant=Participant(factory=lambda:interface,output_finder=lambda:'Virtual-4')
        participant.poll();participant.stop();participant.poll();participant.poll()
        self.assertEqual(interface.calls.count('stop'),1)
        self.assertEqual(len([c for c in interface.calls if isinstance(c,tuple)]),1)
        participant.start()
        self.assertEqual(len([c for c in interface.calls if isinstance(c,tuple)]),2)

    def test_missing_output_does_not_start_or_capture_other_screen(self):
        interface=Interface();participant=Participant(factory=lambda:interface,output_finder=lambda:None)
        self.assertEqual(participant.poll()['state'],'waiting_for_desktop')
        self.assertEqual(interface.calls,['acquire'])


class RuntimeStateTests(unittest.TestCase):
    def test_missing_or_failed_service_is_not_an_active_stream(self):
        from monitorize.desktop.remote_login_runtime import RemoteLoginRuntime
        from types import SimpleNamespace
        for state in ('unavailable','error','stopped','disabled'):
            self.assertFalse(RemoteLoginRuntime.active.fget(SimpleNamespace(enabled=True,status={'state':state})))
        for state in ('desktop_listening','desktop_available','disconnect_grace','desktop_starting'):
            self.assertTrue(RemoteLoginRuntime.active.fget(SimpleNamespace(enabled=True,status={'state':state})))
