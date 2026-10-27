"""Verified temporary Niri output policies for the independent layout guardian."""
import copy
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time

TRANSFORMS = {'Normal': 'normal', '90': '90', '180': '180', '270': '270',
              'Flipped': 'flipped', 'Flipped90': 'flipped-90',
              'Flipped180': 'flipped-180', 'Flipped270': 'flipped-270'}


class NiriLayout:
    def __init__(self):
        self.socket_identity = None

    def run(self, *args):
        socket = Path(os.environ.get('NIRI_SOCKET', ''))
        info = socket.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError('Niri IPC socket does not belong to this user.')
        identity = (info.st_dev, info.st_ino)
        if self.socket_identity is not None and self.socket_identity != identity:
            raise RuntimeError('Niri compositor changed; recovery remains pending.')
        self.socket_identity = identity
        result = subprocess.run(['niri', 'msg', '--json', *args], capture_output=True, text=True, timeout=5, check=True)
        if len(result.stdout) > 1048576:
            raise ValueError('Niri output response exceeds its bound.')
        if args and args[0] == 'action' and not result.stdout.strip():
            return None
        return json.loads(result.stdout)

    @staticmethod
    def active(output):
        return bool(output.get('connected') and output.get('enabled'))

    def outputs(self):
        state = self.run('outputs')
        if not isinstance(state, dict) or not state or len(state) > 64:
            raise ValueError('Niri returned invalid output state.')
        focused = self.run('focused-output')
        focused = focused.get('name') if isinstance(focused, dict) else None
        outputs = []
        for name, output in state.items():
            if not isinstance(output, dict) or output.get('name') != name or not name or len(name) > 128 or name.startswith('-'):
                raise ValueError('Niri returned invalid output identity.')
            modes = output.get('modes'); index = output.get('current_mode'); logical = output.get('logical')
            if not isinstance(modes, list) or (index is not None and (type(index) is not int or not 0 <= index < len(modes))):
                raise ValueError('Niri returned invalid current mode.')
            enabled = index is not None and logical is not None
            if (index is None) != (logical is None):
                raise ValueError('Niri output is transitioning; retry layout preparation.')
            mode = modes[index] if enabled else None
            if enabled:
                if output.get('is_custom_mode') or not isinstance(logical, dict):
                    raise ValueError('This Niri mode cannot be safely restored.')
                if any(type(mode.get(k)) is not int or mode[k] <= 0 for k in ('width', 'height', 'refresh_rate')):
                    raise ValueError('Niri returned invalid mode geometry.')
                scale = float(logical['scale'])
                if not math.isfinite(scale) or scale <= 0 or logical['transform'] not in TRANSFORMS:
                    raise ValueError('Niri returned unsupported scale or transform.')
                if any(type(logical[k]) is not int for k in ('x', 'y')):
                    raise ValueError('Niri returned invalid output position.')
            outputs.append(dict(name=name, connected=True, enabled=enabled,
                priority=1 if name == focused else 2, mode=copy.deepcopy(mode),
                logical=copy.deepcopy(logical), identity=json.dumps([name, output.get('make'), output.get('model'), output.get('serial')]),
                focused=name == focused))
        return outputs

    def snapshot(self, outputs, exclude):
        return [copy.deepcopy(o) for o in outputs if o['name'] not in exclude]

    def _observe(self, predicate):
        for _ in range(20):
            state = {o['name']: o for o in self.outputs()}
            if predicate(state):
                return
            time.sleep(.05)
        raise RuntimeError('Niri layout change was not confirmed; retaining virtual output.')

    def policy(self, mode, snapshot, targets):
        if mode != 'virtual_only':
            raise ValueError('Niri supports Extend and Virtual displays only.')
        state = {o['name']: o for o in self.outputs()}; names = list(targets.values())
        if not names or any(not self.active(state.get(n, {})) for n in names):
            raise RuntimeError('A virtual Niri output is unavailable.')
        physical = [s['name'] for s in snapshot if s['enabled'] and s['name'] in state]
        if any(state[s['name']]['identity'] != s['identity'] for s in snapshot if s['name'] in physical):
            raise RuntimeError('A physical Niri monitor changed before layout application.')
        for name in physical:
            self.run('output', name, 'off')
            self._observe(lambda observed: all(self.active(observed.get(n, {})) for n in names)
                          and not self.active(observed.get(name, {})))
        self._observe(lambda observed: all(self.active(observed.get(n, {})) for n in names)
                      and all(not self.active(observed.get(n, {})) for n in physical))

    def restore(self, snapshot, owned):
        state = {o['name']: o for o in self.outputs()}
        saved = [s for s in snapshot if s['enabled'] and s['name'] in state and state[s['name']]['identity'] == s['identity']]
        for output in saved:
            name = output['name']; mode = output['mode']; logical = output['logical']
            self.run('output', name, 'mode', f"{mode['width']}x{mode['height']}@{mode['refresh_rate']/1000:.3f}")
            self.run('output', name, 'scale', str(logical['scale']))
            self.run('output', name, 'transform', TRANSFORMS[logical['transform']])
            self.run('output', name, 'position', 'set', '--', str(logical['x']), str(logical['y']))
            self.run('output', name, 'on')
        fallback = None
        if not saved:
            fallback = next((o['name'] for o in state.values() if o['name'] not in owned), None)
            if fallback is None:
                raise RuntimeError('No physical Niri output can be restored; retaining virtual output.')
            self.run('output', fallback, 'on')
        self._observe(lambda observed: self.active(observed.get(fallback, {})) if fallback else all(
            self.active(observed.get(s['name'], {})) and observed[s['name']]['identity'] == s['identity']
            and observed[s['name']]['mode'] == s['mode'] and observed[s['name']]['logical'] == s['logical'] for s in saved))
        focus = next((s['name'] for s in saved if s['focused']), fallback)
        if focus:
            self.run('action', 'focus-monitor', focus)
            self._observe(lambda observed: observed.get(focus, {}).get('focused'))
