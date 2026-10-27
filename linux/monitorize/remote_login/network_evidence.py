"""Read-only network metadata; a desktop snapshot never proves boot networking.

Call from a separate worker, never the login safety-stop loop. There is no SSID,
GetSecrets, password retrieval, activation or profile update in this collector.
"""
import ipaddress
import json
from pathlib import Path
import subprocess
import uuid
from monitorize.platform.login_capture_probe import read_phase


def _query(argv):
    result=subprocess.run(argv,capture_output=True,text=True,check=True,timeout=3)
    if len(result.stdout)>65536:raise ValueError('Network evidence response too large.')
    return result.stdout


def collect_network_evidence(*,query=_query,phase_reader=read_phase,
                             boot_reader=lambda:Path('/proc/sys/kernel/random/boot_id').read_text().strip()):
    result=dict(status='unknown',connections=[],observed_before_login=False,
                remote_reachability_verified=False)
    try:
        boot=boot_reader();before=phase_reader()
        rows=query(['/usr/bin/nmcli','--terse','--fields','UUID,TYPE,DEVICE','connection','show','--active']).splitlines()
        addresses=json.loads(query(['/usr/sbin/ip','-json','address','show']))
        by_device={}
        for device in addresses:
            values=[]
            for address in device.get('addr_info',[]):
                try:values.append(str(ipaddress.ip_address(address.get('local',''))))
                except ValueError:pass
            by_device[device.get('ifname')]=values
        connections=[]
        for row in rows:
            fields=row.split(':',2)
            if len(fields)!=3:continue
            identifier,kind,device=fields
            if kind not in ('802-11-wireless','802-3-ethernet'):continue
            identifier=str(uuid.UUID(identifier))
            if not device or len(device)>64 or '\\' in device:continue
            connections.append(dict(uuid=identifier,type=kind,interface=device,addresses=by_device.get(device,[])))
        after=phase_reader();same_boot=boot_reader()==boot
        result.update(status='observed',boot_id=boot,phase_before=before,phase_after=after,
                      connections=connections,observed_before_login=bool(same_boot and before==after=='greeter'
                          and any(c['addresses'] for c in connections)))
    except Exception:
        # No raw command output or exception body enters diagnostics.
        pass
    return result
