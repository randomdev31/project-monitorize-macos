"""Portable configuration/validation for the macOS processes (no Qt imports)."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import platform
import shutil
import sys


@dataclass(frozen=True)
class DisplayMode:
    width: int = 1920
    height: int = 1080
    hz: int = 60

    def __post_init__(self):
        for value, low, high in ((self.width, 640, 7680), (self.height, 480, 4320), (self.hz, 24, 120)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Resolution must be 640–7680 × 480–4320; refresh rate 24–120 Hz.')

    def arguments(self, slot):
        check_slot(slot)
        return [str(self.width), str(self.height), str(self.hz), str(slot)]


def check_slot(slot):
    if type(slot) is not int or slot not in (1, 2):
        raise ValueError('Only display slots 1 and 2 are supported.')


def helper_path():
    return Path(__file__).parent / 'native' / 'monitorize-display'


def check_host():
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise RuntimeError('This port requires Intel macOS (x86_64).')
    if tuple(map(int, platform.mac_ver()[0].split('.')[:1])) < (12,):
        raise RuntimeError('macOS Monterey 12 or newer is required.')
    if not os.access(helper_path(), os.X_OK):
        raise RuntimeError('Native helper missing. Run bash macos/build-native.sh before installing.')


def sunshine_binary():
    override = os.environ.get('MONITORIZE_SUNSHINE')
    candidates = [override] if override else [shutil.which('sunshine'), '/usr/local/bin/sunshine',
        '/Applications/Sunshine.app/Contents/MacOS/sunshine']
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise RuntimeError('Install Sunshine for Intel macOS, or set MONITORIZE_SUNSHINE to its executable.')


def state_root():
    return Path.home() / 'Library' / 'Application Support' / 'Monitorize'


def base_port(slot):
    check_slot(slot)
    return 47989 + (slot - 1) * 1100


def parse_display_event(line):
    data = json.loads(line)
    if not isinstance(data, dict) or type(data.get('id')) is not int or not 0 < data['id'] <= 0xFFFFFFFF:
        raise ValueError('Native helper returned an invalid display ID.')
    return data['id']


def prepare_sunshine(slot, display_id, root=None):
    """Write only Monitorize-owned profiles. Keep Sunshine UI preferences on restart."""
    check_slot(slot)
    if type(display_id) is not int or not 0 < display_id <= 0xFFFFFFFF:
        raise ValueError('A live CoreGraphics display ID is required.')
    profile = (Path(root) if root is not None else state_root()) / f'sunshine-{slot}'
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile.chmod(0o700)
    if any(c in str(profile) for c in '\r\n'):
        raise ValueError('Profile paths cannot contain newlines.')
    credentials = profile / 'credentials'
    credentials.mkdir(exist_ok=True, mode=0o700)
    apps = profile / 'apps.json'
    if not apps.exists():
        apps.write_text(json.dumps({'env': {}, 'apps': [{'name': 'Desktop'}]}, indent=2) + '\n')
    options = {
        'port': str(base_port(slot)), 'output_name': str(display_id),
        'sunshine_name': f'Monitorize Mac {slot}',
        'origin_web_ui_allowed': 'pc', 'upnp': 'disabled',
        'apps': str(apps), 'file_state': str(profile / 'sunshine_state.json'),
        'credentials_file': str(profile / 'sunshine_credentials.json'),
        'pkey': str(credentials / 'cakey.pem'), 'cert': str(credentials / 'cacert.pem'),
        'log_path': str(profile / 'sunshine.log'),
    }
    config = profile / 'sunshine.conf'
    previous = config.read_text().splitlines() if config.exists() else ['encoder = videotoolbox']
    retained = [line for line in previous if line.partition('=')[0].strip() not in options]
    content = '\n'.join(retained + [f'{key} = {value}' for key, value in options.items()]) + '\n'
    temp = config.with_suffix('.tmp')
    temp.write_text(content)
    temp.chmod(0o600)
    temp.replace(config)
    return config
