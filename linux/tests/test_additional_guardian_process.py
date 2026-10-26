"""Real process ownership with simulated Xorg/Niri state and harmless holders."""
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

MANAGER=r'''
import asyncio,os,sys
from pathlib import Path
from monitorize.streaming.recovery_guardian import Guardian
from monitorize.platform.session_layout import LayoutTransaction
from test_additional_layout_backends import XServer,NiriServer,xoutput
path,events,journal,owner,desktop=sys.argv[1:]
class Backend(XServer if desktop=='x11' else NiriServer):
    def restore(self,snapshot,owned):
        super().restore(snapshot,owned)
        assert all(o['enabled'] for o in self.outputs() if o['name'] in ('eDP-1','HDMI-1'))
        with open(events,'a') as stream:stream.write('physical-restored\n')
class Manager(Guardian):
    async def spawn_holder(self,args,environment):
        if desktop=='x11':self.layout.backend.state.append(xoutput('Virtual-1'))
        else:self.layout.backend.add_virtual('Virtual-1')
        code="import sys; print('holder-ready',flush=True); sys.stdin.readline(); open(sys.argv[1],'a').write('holder-cleaned\\n')"
        return await asyncio.create_subprocess_exec(sys.executable,'-c',code,events,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
asyncio.run(Manager(path,'token','virtual_only',int(owner),LayoutTransaction(Backend(),journal,'virtual_only')).run())
'''
GUI=r'''
import json,os,socket,subprocess,sys,time
manager,path,events,journal,desktop=sys.argv[1:]
child=subprocess.Popen([sys.executable,manager,path,events,journal,str(os.getpid()),desktop],
    start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def command(operation,**values):
    with socket.socket(socket.AF_UNIX) as peer:
        peer.connect(path);peer.sendall((json.dumps(dict(token='token',operation=operation,**values))+'\n').encode())
        assert json.loads(peer.makefile('rb').readline())['ok']
for _ in range(200):
    if os.path.exists(path):break
    time.sleep(.01)
holder=socket.socket(socket.AF_UNIX);holder.connect(path)
holder.sendall((json.dumps(dict(token='token',operation='hold',slot=1,args=['1920','1080','60','primary',desktop,'vkms']))+'\n').encode())
assert holder.makefile('rb').readline()==b'holder-ready\n'
command('ready',slot=1,name='Virtual-1');command('stream',slot=1,active=True)
print(child.pid,flush=True);time.sleep(30)
'''


class AdditionalGuardianProcessTests(unittest.TestCase):
    def test_gui_death_restores_physical_screens_before_real_holder_cleanup(self):
        for desktop in ('x11','niri'):
            with self.subTest(desktop=desktop),tempfile.TemporaryDirectory() as tmp:
                directory=Path(tmp);manager=directory/'manager.py';manager.write_text(MANAGER)
                events=directory/'events';path=str(directory/'control.sock')
                env={**os.environ,'XDG_STATE_HOME':tmp,'XDG_CONFIG_HOME':tmp,
                     'XDG_SESSION_TYPE':'x11' if desktop=='x11' else 'wayland'}
                gui=subprocess.Popen([sys.executable,'-c',GUI,str(manager),path,str(events),str(directory/'journal'),desktop],
                    env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                pid=None
                try:
                    self.assertTrue(select.select([gui.stdout],[],[],5)[0])
                    line=gui.stdout.readline().strip()
                    self.assertTrue(line,gui.stderr.read() if not line else '')
                    pid=int(line);gui.kill();gui.wait(timeout=2)
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        if events.exists() and 'holder-cleaned' in events.read_text():break
                        time.sleep(.05)
                    recorded=events.read_text()
                    self.assertIn('holder-cleaned',recorded)
                    self.assertLess(recorded.index('physical-restored'),recorded.index('holder-cleaned'))
                finally:
                    if gui.poll() is None:gui.kill()
                    gui.wait(timeout=2);gui.stdout.close();gui.stderr.close()
                    if pid:
                        try:os.kill(pid,signal.SIGTERM)
                        except ProcessLookupError:pass
