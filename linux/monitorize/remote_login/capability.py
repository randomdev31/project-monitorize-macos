"""Validate the installed fork's exact-output contract without executing it."""
import mmap
from pathlib import Path

MARKERS=(b'MONITORIZE_CONTROL_PROTOCOL=1',b'MONITORIZE_STRICT_KMS_OUTPUT_MISSING')


def exact_kms_engine(path):
    try:
        with Path(path).open('rb') as source:
            if source.read(4)!=b'\x7fELF':return False
            with mmap.mmap(source.fileno(),0,access=mmap.ACCESS_READ) as binary:
                return all(binary.find(marker)>=0 for marker in MARKERS)
    except (OSError,ValueError):return False
