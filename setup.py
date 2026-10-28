"""Tag macOS distributions correctly when the native display helper is included."""
import sys
from pathlib import Path

if sys.platform == "darwin" and not (Path(__file__).parent / "linux/monitorize/macos/native/monitorize-display").is_file():
    raise RuntimeError("Build the native helper first: bash macos/build-native.sh")
from setuptools import setup
from setuptools.dist import Distribution


class PlatformDistribution(Distribution):
    def has_ext_modules(self):
        return sys.platform == 'darwin'


setup(distclass=PlatformDistribution)
