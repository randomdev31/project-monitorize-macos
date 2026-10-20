#!/usr/bin/env python3
"""Reject native source snapshots missing the paired managed-display host changes.

The Git pin equality/clean-tree checks remain the native builders' responsibility.
This source check also runs in extracted package sources, without Git or app imports.
Runtime additionally checks the installed binary's version marker before listening.
"""
from pathlib import Path
import sys


REQUIRED = {
    'src/listener_codec_policy.h': ('MONITORIZE_CODEC_NEGOTIATION=1', 'forced_format', 'advertise'),
    'src/listener_probe_display.h': ('listener_probe_display', 'make_avcodec_encode_device'),
    'src/monitorize_control.h': ('MONITORIZE_CONTROL_PROTOCOL=1', 'MONITORIZE_LAYOUT_RECOVERY=1'),
    'src/main.cpp': ('monitorize_control::protocol_marker',),
    'src/nvhttp.cpp': ('prepare_managed_display', 'monitorize_control::bind_target',
                       '"release"', '"abort"'),
    'src/stream.cpp': ('"stream_started"', '"stream_stopped"', '"stream_ready"'),
    'src/video.cpp': ('monitorize_control::enabled()',),
}


def missing_protocol_sources(source):
    missing = []
    for relative, markers in REQUIRED.items():
        path = source / relative
        try:
            contents = path.read_text()
        except (OSError, UnicodeError):
            missing.append(relative)
            continue
        if any(marker not in contents for marker in markers):
            missing.append(relative)
    return missing


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check-client-display-protocol.py SUNSHINE_SOURCE_DIR')
    missing = missing_protocol_sources(Path(sys.argv[1]))
    if missing:
        print('Error: Sunshine source lacks Monitorize client display protocol v1: '
              + ', '.join(missing) + '. Commit/publish the paired Sunshine changes and '
              'update the submodule and all native package pins before building this app.', file=sys.stderr)
        return 1
    print('Monitorize Sunshine client display protocol v1 source check passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
