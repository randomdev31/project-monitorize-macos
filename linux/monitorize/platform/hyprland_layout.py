"""Hyprland layout operations with explicit output identity and verification.

Hyprland has no KDE-style primary-monitor priority. The virtual-primary policy
selects the focused monitor; other applications may use their own placement.
"""
import json
import math
import re
import subprocess
from .session_layout import KdeLayout,output_identity


def _number(value):
    number=float(value)
    if not math.isfinite(number):raise ValueError('Invalid monitor geometry.')
    return number


class HyprlandLayout(KdeLayout):
    def run(self,*args):
        result=subprocess.run(['hyprctl',*args],capture_output=True,text=True,timeout=4,check=True)
        return result.stdout

    def outputs(self):
        monitors=json.loads(self.run('-j','monitors','all'))
        if not isinstance(monitors,list) or not monitors:raise RuntimeError('Hyprland returned no displays.')
        outputs=[]
        for index,monitor in enumerate(monitors):
            name=monitor['name']
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):
                raise ValueError('Unsupported monitor identifier.')
            width=int(_number(monitor.get('width',0)));height=int(_number(monitor.get('height',0)))
            refresh=_number(monitor.get('refreshRate',60));scale=_number(monitor.get('scale',1))
            if scale<=0 or scale>8 or refresh<0:raise ValueError('Invalid monitor geometry.')
            outputs.append(dict(name=name,connected=True,enabled=not monitor.get('disabled',False) and width>0 and height>0,
                priority=1 if monitor.get('focused') else index+2,
                pos={'x':int(_number(monitor.get('x',0))),'y':int(_number(monitor.get('y',0)))},
                mode=f'{width}x{height}@{refresh:g}',scale=scale))
        return outputs

    def apply(self,settings):
        for command in settings:
            prefix,name,action=command.split('.',2)
            if prefix!='output' or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):raise ValueError('Invalid layout target.')
            if action=='enable':self.run('keyword','monitor',name+',preferred,auto,auto')
            elif action=='disable':self.run('keyword','monitor',name+',disable')
            elif action=='priority.1':self.run('dispatch','focusmonitor',name)
            elif action.startswith('priority.'):continue
            else:raise ValueError('Unsupported layout operation.')

    def restore(self,snapshot,owned):
        current={item['name']:item for item in self.outputs()}
        visible=[]
        for saved in snapshot:
            output=current.get(saved['name'])
            if not output or not saved['enabled']:continue
            name=output['name']
            if not self.active(output):
                if saved.get('identity')==output_identity(output) and saved.get('mode') and saved.get('scale'):
                    mode=saved['mode'];scale=_number(saved['scale']);pos=saved.get('pos') or {'x':0,'y':0}
                    if not re.fullmatch(r'[0-9]+x[0-9]+@[0-9.]+',mode):raise ValueError('Invalid saved display mode.')
                    location=f"{int(pos['x'])}x{int(pos['y'])}"
                    self.run('keyword','monitor',f'{name},{mode},{location},{scale:g}')
                else:self.run('keyword','monitor',name+',preferred,auto,auto')
            visible.append(saved)
        if not visible:
            fallback=next((output for output in current.values() if output['name'] not in owned),None)
            if fallback is None:raise RuntimeError('No physical display can be restored; retaining virtual output.')
            self.run('keyword','monitor',fallback['name']+',preferred,auto,auto')
            visible=[fallback]
        primary=min(visible,key=lambda value:value.get('priority',100))['name']
        self.run('dispatch','focusmonitor',primary)
        observed={output['name']:output for output in self.outputs()}
        if any(not self.active(observed.get(value['name'],{})) for value in visible):
            raise RuntimeError('Hyprland physical display restoration was not confirmed.')
        if observed[primary]['priority']!=1:raise RuntimeError('Hyprland restored monitor focus was not confirmed.')
