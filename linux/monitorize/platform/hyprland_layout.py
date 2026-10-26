"""Hyprland layout operations with explicit output identity and verification.

Hyprland has no KDE-style primary-monitor priority. The virtual-primary policy
selects the focused monitor; other applications may use their own placement.
"""
import json
import copy
import math
import os
import re
import subprocess
from .session_layout import KdeLayout,output_identity


def _number(value):
    number=float(value)
    if not math.isfinite(number):raise ValueError('Invalid monitor geometry.')
    return number


class HyprlandLayout(KdeLayout):
    def require_vkms_lifecycle(self):
        version = json.loads(self.run('-j', 'version'))
        reported = version.get('systemAquamarine', '') if isinstance(version, dict) else ''
        match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', reported)
        if not match or tuple(map(int, match.groups())) < (0, 15, 1):
            raise RuntimeError('Hyprland VKMS needs a verified running Aquamarine 0.15.1 or newer. '
                               'Update Hyprland/Aquamarine, or use compositor-created displays.')

    def run(self,*args):
        instance = getattr(self, '_instance', None)
        if instance is None:
            instance = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
            if not instance:
                result = subprocess.run(['hyprctl', '-j', 'instances'], capture_output=True, text=True, timeout=4, check=True)
                instances = json.loads(result.stdout)
                if not isinstance(instances, list) or len(instances) != 1:
                    raise RuntimeError('A unique Hyprland instance is required for display recovery.')
                instance = instances[0].get('instance')
            if not isinstance(instance, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', instance):
                raise ValueError('Invalid Hyprland instance identity.')
            self._instance = instance
        result=subprocess.run(['hyprctl','-i',instance,*args],capture_output=True,text=True,timeout=4,check=True)
        return result.stdout

    def monitor(self, name, *, mode='preferred', position='auto', scale=1, transform=0, disabled=False):
        fields = dict(output=name, mode=mode, position=position, scale=scale, transform=transform, disabled=disabled)
        lua = 'hl.monitor({ '+', '.join(key+' = '+json.dumps(value) for key, value in fields.items())+' })'
        try:
            self.run('eval', lua)
        except subprocess.CalledProcessError:
            rule = name+',disable' if disabled else f'{name},{mode},{position},{scale:g},transform,{transform}'
            self.run('keyword', 'monitor', rule)

    def focus(self, name):
        try:
            self.run('eval', 'hl.dispatch(hl.dsp.focus({ monitor = '+json.dumps(name)+' }))')
        except subprocess.CalledProcessError:
            self.run('dispatch', 'focusmonitor', name)

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
            transform=monitor.get('transform',0)
            if type(transform) is not int or not 0 <= transform <= 7:
                raise ValueError('Unsupported Hyprland transform.')
            outputs.append(dict(name=name,connected=True,enabled=not monitor.get('disabled',False) and width>0 and height>0,
                priority=1 if monitor.get('focused') else index+2,
                pos={'x':int(_number(monitor.get('x',0))),'y':int(_number(monitor.get('y',0)))},
                mode=f'{width}x{height}@{refresh:g}',scale=scale,
                transform=transform, mirror=monitor.get('mirrorOf', 'none')))
        return outputs

    def snapshot(self, outputs, exclude):
        result=[]
        for output in outputs:
            if output['name'] in exclude:continue
            if output.get('mirror') not in (None, '', 'none'):
                raise ValueError('Disable Hyprland output mirroring before using guarded layouts.')
            result.append(dict(copy.deepcopy(output), identity=output_identity(output)))
        return result

    def apply(self,settings):
        for command in settings:
            prefix,name,action=command.split('.',2)
            if prefix!='output' or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):raise ValueError('Invalid layout target.')
            if action=='enable':self.monitor(name)
            elif action=='disable':self.monitor(name, disabled=True)
            elif action=='priority.1':self.focus(name)
            elif action.startswith('priority.'):continue
            else:raise ValueError('Unsupported layout operation.')

    def restore(self,snapshot,owned):
        current={item['name']:item for item in self.outputs()}
        visible=[]
        for saved in snapshot:
            output=current.get(saved['name'])
            if not output or not saved['enabled']:continue
            name=output['name']
            if not self.active(output) or any(output.get(key) != saved.get(key) for key in ('mode','scale','pos','transform')):
                if saved.get('identity')==output_identity(output) and saved.get('mode') and saved.get('scale'):
                    mode=saved['mode'];scale=_number(saved['scale']);pos=saved.get('pos') or {'x':0,'y':0}
                    if not re.fullmatch(r'[0-9]+x[0-9]+@[0-9.]+',mode):raise ValueError('Invalid saved display mode.')
                    location=f"{int(pos['x'])}x{int(pos['y'])}"
                    self.monitor(name, mode=mode, position=location, scale=scale, transform=saved.get('transform',output.get('transform',0)))
                else:self.monitor(name)
            visible.append(saved)
        if not visible:
            fallback=next((output for output in current.values() if output['name'] not in owned),None)
            if fallback is None:raise RuntimeError('No physical display can be restored; retaining virtual output.')
            self.monitor(fallback['name'])
            visible=[fallback]
        primary=min(visible,key=lambda value:value.get('priority',100))['name']
        self.focus(primary)
        observed={output['name']:output for output in self.outputs()}
        if any(not self.active(observed.get(value['name'],{})) for value in visible):
            raise RuntimeError('Hyprland physical display restoration was not confirmed.')
        if observed[primary]['priority']!=1:raise RuntimeError('Hyprland restored monitor focus was not confirmed.')
        for saved in visible:
            actual=observed[saved['name']]
            if saved.get('identity')==output_identity(actual) and any(key in saved and actual.get(key)!=saved.get(key) for key in ('mode','scale','pos','transform')):
                raise RuntimeError('Hyprland saved display geometry was not restored.')
