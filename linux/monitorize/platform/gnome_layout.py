"""Temporary Mutter logical-monitor policies for the desktop recovery guardian.

No ScreenCast sessions or persistent monitor files are created here. Snapshots
retain clone groups, mode IDs, scale and transform, not KDE output commands.
"""
import copy
import math
from .session_layout import output_identity


class GnomeLayout:
    def __init__(self,interface=None):
        self.interface=interface

    def _interface(self):
        if self.interface is None:
            import dbus
            bus=dbus.SessionBus()
            self.interface=dbus.Interface(bus.get_object('org.gnome.Mutter.DisplayConfig',
                '/org/gnome/Mutter/DisplayConfig',introspect=False),'org.gnome.Mutter.DisplayConfig')
        return self.interface

    @staticmethod
    def active(output):return bool(output.get('connected') and output.get('enabled'))

    def _read(self):
        interface=self._interface()
        serial,monitors,logical,properties=interface.GetCurrentState(signature='',timeout=3)
        self.layout_mode=int(properties.get('layout-mode',1))
        outputs={}
        for spec,modes,attributes in monitors:
            name=str(spec[0])
            if name in outputs:raise RuntimeError('Mutter returned ambiguous monitor identities.')
            available={str(mode[0]):dict(width=int(mode[1]),height=int(mode[2]),scales=[float(s) for s in mode[5]]) for mode in modes}
            mode=next((str(m[0]) for m in modes if m[6].get('is-current')),None)
            preferred=next((str(m[0]) for m in modes if m[6].get('is-preferred')),next(iter(available),None))
            outputs[name]=dict(name=name,connected=True,enabled=False,priority=2,
                pos=None,mode=mode or preferred,scale=1,available=available,
                properties={str(k):v for k,v in attributes.items() if k in ('color-mode','rgb-range','is-underscanning')},
                type=str(spec[1]),sizeMM=[int(attributes.get('width-mm',0)),int(attributes.get('height-mm',0))],
                monitor_identity=[str(value) for value in spec],layout_group=None)
        groups=[]
        for x,y,scale,transform,primary,specs,_attributes in logical:
            group=dict(x=int(x),y=int(y),scale=float(scale),transform=int(transform),primary=bool(primary),monitors=[])
            if not math.isfinite(group['scale']) or group['scale']<=0:raise ValueError('Invalid Mutter scale.')
            for spec in specs:
                name=str(spec[0]);output=outputs[name]
                if output['enabled'] or not output['mode']:raise RuntimeError('Mutter active mode is ambiguous.')
                group['monitors'].append(dict(name=name,mode=output['mode'],properties=dict(output['properties'])))
                output.update(enabled=True,priority=1 if primary else 2,pos={'x':int(x),'y':int(y)},scale=float(scale))
            groups.append(group)
            for monitor in group['monitors']:outputs[monitor['name']]['layout_group']=group
        return serial,outputs,groups,dict(properties)

    def outputs(self):return list(self._read()[1].values())

    def snapshot(self,outputs,exclude):
        result=[]
        for output in outputs:
            if output['name'] in exclude:continue
            group=copy.deepcopy(output['layout_group'])
            if group:group['monitors']=[m for m in group['monitors'] if m['name'] not in exclude]
            result.append(dict(name=output['name'],enabled=output['enabled'],priority=output['priority'],
                identity=output_identity(output),layout_mode=self.layout_mode,monitor_identity=output['monitor_identity'],layout_group=group))
        return result

    def _width(self,group,outputs):
        mode=outputs[group['monitors'][0]['name']]['available'][group['monitors'][0]['mode']]
        dimension=mode['height'] if group['transform']%2 else mode['width']
        return max(1,round(dimension/(group['scale'] if self.layout_mode==1 else 1)))

    def _commit(self,build):
        interface=self._interface()
        for attempt in range(2):
            serial,outputs,groups,properties=self._read()
            import dbus
            allowed=interface.Get('org.gnome.Mutter.DisplayConfig','ApplyMonitorsConfigAllowed',
                dbus_interface='org.freedesktop.DBus.Properties',signature='ss',timeout=3)
            if not allowed:raise RuntimeError('Mutter does not permit temporary display configuration.')
            desired=build(outputs,copy.deepcopy(groups))
            if not desired:raise RuntimeError('No display can be restored; retaining virtual output.')
            minimum_x=min(g['x'] for g in desired);minimum_y=min(g['y'] for g in desired)
            if not any(g['primary'] for g in desired):desired[0]['primary']=True
            if sum(g['primary'] for g in desired)!=1:raise ValueError('Layout requires one primary logical monitor.')
            payload=[]
            for group in desired:
                group['x']-=minimum_x;group['y']-=minimum_y
                members=[]
                for monitor in group['monitors']:
                    output=outputs[monitor['name']];mode=output['available'].get(monitor['mode'])
                    if mode is None or group['scale'] not in mode['scales']:
                        raise RuntimeError('Saved Mutter mode or scale is no longer supported.')
                    monitor_properties={}
                    for key,value in monitor.get('properties',{}).items():
                        if key in ('color-mode','rgb-range'):monitor_properties[key]=dbus.UInt32(value)
                        elif key=='is-underscanning':monitor_properties['underscanning']=dbus.Boolean(value)
                    members.append((monitor['name'],monitor['mode'],dbus.Dictionary(monitor_properties,signature='sv')))
                payload.append((group['x'],group['y'],group['scale'],group['transform'],group['primary'],
                    dbus.Array(members,signature='(ssa{sv})')))
            options={}
            if 'layout-mode' in properties and properties.get('supports-changing-layout-mode'):
                options['layout-mode']=dbus.UInt32(properties['layout-mode'])
            try:
                interface.ApplyMonitorsConfig(dbus.UInt32(serial),dbus.UInt32(1),
                    dbus.Array(payload,signature='(iiduba(ssa{sv}))'),dbus.Dictionary(options,signature='sv'),signature='uua(iiduba(ssa{sv}))a{sv}',timeout=3)
            except Exception as error:
                name=error.get_dbus_name() if hasattr(error,'get_dbus_name') else ''
                if attempt==0 and name=='org.freedesktop.DBus.AccessDenied':continue
                raise
            _serial,_outputs,observed,_props=self._read()
            def normalized(groups):
                return sorted((g['x'],g['y'],g['scale'],g['transform'],g['primary'],
                    sorted((m['name'],m['mode'],sorted(m.get('properties',{}).items())) for m in g['monitors'])) for g in groups)
            if normalized(observed)!=normalized(desired):
                raise RuntimeError('Mutter layout change could not be verified; retaining virtual output.')
            return

    def policy(self,mode,snapshot,targets):
        if mode not in ('primary','virtual_only'):raise ValueError('Unsupported GNOME layout policy.')
        names=list(targets.values());physical={s['name'] for s in snapshot if s['enabled']}
        def build(outputs,groups):
            if not names or any(name not in outputs or not self.active(outputs[name]) for name in names):
                raise RuntimeError('A streaming virtual display is unavailable.')
            desired=[]
            for group in groups:
                members={m['name'] for m in group['monitors']}
                if members.intersection(names) and not members.issubset(names):
                    raise RuntimeError('Virtual target shares a clone group with a physical output.')
                if mode=='virtual_only':group['monitors']=[m for m in group['monitors'] if m['name'] not in physical]
                if not group['monitors']:continue
                group['primary']=names[0] in {m['name'] for m in group['monitors']}
                desired.append(group)
            if mode=='virtual_only':
                right=0
                for group in desired:
                    group.update(x=right,y=0);right+=self._width(group,outputs)
            return desired
        self._commit(build)

    def restore(self,snapshot,owned):
        owned=set(owned)
        def build(outputs,groups):
            if any(saved.get('layout_mode',self.layout_mode)!=self.layout_mode for saved in snapshot):
                raise RuntimeError('Mutter coordinate layout mode changed; retaining virtual output.')
            desired=[];restored=set()
            for saved in snapshot:
                if not saved['enabled'] or not saved.get('layout_group'):continue
                group=copy.deepcopy(saved['layout_group'])
                members=[]
                for monitor in group['monitors']:
                    name=monitor['name'];output=outputs.get(name)
                    original=next((s for s in snapshot if s['name']==name),None)
                    if name in restored or output is None or original is None:continue
                    if original.get('monitor_identity')!=output['monitor_identity'] or original['identity']!=output_identity(output):continue
                    members.append(monitor);restored.add(name)
                if members:group['monitors']=members;desired.append(group)
            if not desired:
                fallback=next((o for o in outputs.values() if o['name'] not in owned and o['mode']),None)
                if fallback is None:raise RuntimeError('No physical display can be restored; retaining virtual output.')
                mode=fallback['available'][fallback['mode']]
                desired=[dict(x=0,y=0,scale=mode['scales'][0],transform=0,primary=True,
                    monitors=[dict(name=fallback['name'],mode=fallback['mode'],properties=dict(fallback['properties']))])]
                restored.add(fallback['name'])
            # Retain current virtual/new groups until restoration has been verified.
            right=max(g['x']+self._width(g,outputs) for g in desired)
            for group in groups:
                group['monitors']=[m for m in group['monitors'] if m['name'] not in restored]
                if group['monitors']:
                    group.update(x=right,y=0,primary=False);desired.append(group)
                    right+=self._width(group,outputs)
            return desired
        self._commit(build)
