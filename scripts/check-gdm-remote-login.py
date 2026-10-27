#!/usr/bin/env python3
"""Print read-only GDM greeter/headless evidence; does not validate streaming."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'linux'))
from monitorize.remote_login.gdm_probe import collect
if __name__=='__main__':
    print(json.dumps(collect(),indent=2))
    raise SystemExit(2)  # A live Moonlight test is always required.
