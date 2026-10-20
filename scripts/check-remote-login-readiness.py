#!/usr/bin/env python3
"""Report pre-login prerequisites without changing the host."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'linux'))
from monitorize.platform.remote_login_readiness import collect_readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sunshine', help='Exact Sunshine executable whose KMS capability to inspect')
    parser.add_argument('--json', action='store_true', help='Print machine-readable evidence')
    args = parser.parse_args()
    report = collect_readiness(args.sunshine)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print('Remote login readiness — read-only; live validation required')
        print('Manager:', report['facts']['manager'], report['facts']['manager_version'])
        for check in report['checks']:
            print(f"{check['status']:7} {check['name']}: {check['detail']}")
        for note in report['limitations']:
            print('NOTE:', note)
        print('Result: experimental; headless greeter video/input/login are not validated.')
    # 2 means prerequisites blocked or unknown; never claim live support.
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
