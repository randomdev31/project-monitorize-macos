"""Entry point for the self-contained Intel macOS application."""
import json
import subprocess
import sys
from monitorize.macos.app import main


def smoke_test():
    """Check packaged Qt and helper without changing the user's display layout."""
    from PyQt6.QtWidgets import QApplication
    from monitorize.macos.app import Window
    from monitorize.macos.runtime import check_host, helper_path
    check_host()
    result = subprocess.run([str(helper_path()), '--list'], capture_output=True, check=True, timeout=10)
    if not isinstance(json.loads(result.stdout), list):
        raise RuntimeError('Invalid native display enumeration response')
    app = QApplication([])
    window = Window()
    app.processEvents()
    window.close()
    print('Packaged Qt frontend and native helper smoke test passed.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(smoke_test() if '--smoke-test' in sys.argv else main())
