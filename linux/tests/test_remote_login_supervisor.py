import unittest
from monitorize.remote_login.policy import session_target
from monitorize.remote_login.supervisor import Supervisor


def session(uid=1000,id='s1',**kw):
    return dict(uid=uid,id=id,seat='seat0',active=True,remote=False,type='wayland',**kw)


class SupervisorTests(unittest.TestCase):
    def setUp(self):self.supervisor=Supervisor(1000)
    def tick(self,**kw):return self.supervisor.reconcile(**dict({'sessions':[],'greeter_ready':True,'boot_running':False,'desktop_running':False,'identity_free':True},**kw))

    def test_greeter_start_only_when_free(self):
        r=self.tick();self.assertEqual(r['action'],'start_boot')
        r=self.tick(boot_running=True,identity_free=False);self.assertEqual(r['state'],'greeter_listening')
        r=self.tick(identity_free=False);self.assertEqual(r['action'],'wait')

    def test_login_waits_for_actual_engine_exit_and_lock(self):
        r=self.tick(sessions=[session()],boot_running=True,identity_free=False)
        self.assertEqual(r['action'],'stop_boot');self.assertEqual(r['state'],'handoff_to_desktop')
        self.assertFalse(self.supervisor.can_acquire(1000,'s1'))
        r=self.tick(sessions=[session()],identity_free=False)
        self.assertEqual(r['state'],'waiting_for_desktop');self.assertFalse(self.supervisor.can_acquire(1000,'s1'))
        self.tick(sessions=[session()])
        self.assertTrue(self.supervisor.can_acquire(1000,'s1'))
        self.assertFalse(self.supervisor.can_acquire(1001,'s1'))
        self.assertFalse(self.supervisor.can_acquire(1000,'old'))

    def test_acquisition_generation_and_repeated_events(self):
        self.tick(sessions=[session()]);token=self.supervisor.acquire(1000,'s1')
        self.assertEqual(self.supervisor.acquire(1000,'s1'),token)
        r=self.tick(sessions=[session()],desktop_running=True,identity_free=False)
        self.assertEqual(r['state'],'desktop_owned');self.assertEqual(self.supervisor.generation,token)
        self.assertFalse(self.supervisor.release('stale'))
        self.assertTrue(self.supervisor.release(token))

    def test_logout_stops_desktop_before_boot_rearm(self):
        self.tick(sessions=[session()]);self.supervisor.acquire(1000,'s1')
        r=self.tick(desktop_running=True,identity_free=False)
        self.assertEqual(r['action'],'stop_desktop');self.assertEqual(r['state'],'handoff_to_greeter')
        self.assertEqual(self.tick(identity_free=False)['action'],'wait')
        self.assertEqual(self.tick()['action'],'start_boot')

    def test_lock_retains_desktop_no_greeter(self):
        self.tick(sessions=[session()]);self.supervisor.acquire(1000,'s1')
        locked=dict(session(),locked=True)
        r=self.tick(sessions=[locked],desktop_running=True,identity_free=False)
        self.assertEqual(r['state'],'desktop_owned');self.assertEqual(r['action'],'wait')

    def test_other_user_never_captured(self):
        r=self.tick(sessions=[session(uid=1001)],boot_running=True)
        self.assertEqual(r['action'],'stop_boot');self.assertFalse(self.supervisor.can_acquire(1001,'s1'))
        r=self.tick(sessions=[session(uid=1001)])
        self.assertEqual(r['state'],'suspended');self.assertEqual(r['action'],'wait')

    def test_manual_stop_suppresses_current_session_only(self):
        self.tick(sessions=[session()]);self.supervisor.acquire(1000,'s1')
        self.supervisor.user_stop('s1')
        self.tick(sessions=[session()]);self.assertFalse(self.supervisor.can_acquire(1000,'s1'))
        self.tick();self.tick(sessions=[session(id='s2')]);self.assertTrue(self.supervisor.can_acquire(1000,'s2'))

    def test_unknown_session_fails_closed(self):
        r=self.tick(sessions=None,boot_running=True)
        self.assertEqual(r['action'],'stop_boot');self.assertEqual(r['state'],'error')

    def test_disabled_stops_both_serially(self):
        self.supervisor.enabled=False
        self.assertEqual(self.tick(boot_running=True,desktop_running=True)['action'],'stop_boot')
        self.assertEqual(self.tick(desktop_running=True)['action'],'stop_desktop')
        self.assertEqual(self.tick()['state'],'disabled')

    def test_remote_tty_inactive_and_ambiguous_never_granted(self):
        for data in [dict(session(),remote=True),dict(session(),active=False),dict(session(),type='tty')]:
            self.tick(sessions=[data]);self.assertFalse(self.supervisor.can_acquire(1000,'s1'))
        self.tick(sessions=[session(),session(id='s2')]);self.assertFalse(self.supervisor.can_acquire(1000,'s1'))

    def test_session_change_invalidates_old_token(self):
        self.tick(sessions=[session()]);old=self.supervisor.acquire(1000,'s1')
        self.tick(sessions=[session(id='s2')]);new=self.supervisor.acquire(1000,'s2')
        self.assertNotEqual(old,new);self.assertFalse(self.supervisor.release(old))
