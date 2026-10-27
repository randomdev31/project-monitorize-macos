"""Regression coverage for upgrading the prepared NVENC dependency."""

import io
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FFMPEG_CMAKE = ROOT / "external/sunshine/cmake/dependencies/ffmpeg.cmake"


@unittest.skipUnless(shutil.which("cmake"), "cmake is unavailable")
class FFmpegCacheTest(unittest.TestCase):
    def test_dependency_upgrade_ignores_old_extracted_library(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "_deps/ffmpeg/lib/libavcodec.a"
            old.parent.mkdir(parents=True)
            old.write_text("old API 13.1-only bundle")
            release = root / "_deps/ffmpeg-test-release"
            release.mkdir()
            archive = release / "Linux-x86_64-ffmpeg.tar.gz"
            payload = b"new dynamic NVENC bundle"
            with tarfile.open(archive, "w:gz") as output:
                info = tarfile.TarInfo("ffmpeg/lib/libavcodec.a")
                info.size = len(payload)
                output.addfile(info, io.BytesIO(payload))
                header = tarfile.TarInfo("ffmpeg/include/libavcodec/avcodec.h")
                header.size = 0
                output.addfile(header, io.BytesIO())
            # Cache extraction is tested offline; host libva discovery is a separate
            # configure dependency and must not require development packages here.
            modules = root / "cmake"
            modules.mkdir()
            (modules / "FindLibva.cmake").write_text(f'''set(LIBVA_FOUND TRUE)
set(LIBVA_LIB "{root}/host/libva.so")
set(LIBVA_DRM_LIB "{root}/host/libva-drm.so")
set(_libva_library_dir "{root}/host")
''')
            (root / "host").mkdir()
            (root / "host/libva-x11.so").touch()
            script = root / "CMakeLists.txt"
            # Stub Git/tag discovery; exercise actual archive/cache/header staging.
            script.write_text(f'''cmake_minimum_required(VERSION 3.25)
project(FFmpegCache NONE)
set(CMAKE_MODULE_PATH "{modules}")
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
function(execute_process)
  cmake_parse_arguments(PROBE "" "OUTPUT_VARIABLE" "" ${{ARGN}})
  if(PROBE_OUTPUT_VARIABLE)
    set(${{PROBE_OUTPUT_VARIABLE}} test-release PARENT_SCOPE)
  endif()
endfunction()
include("{FFMPEG_CMAKE}")
file(WRITE "{root}/selected.txt" "${{FFMPEG_PREPARED_BINARIES}}")
''')
            configured = subprocess.run(
                ["cmake", "-S", str(root), "-B", str(root)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, configured.returncode, configured.stdout + configured.stderr)
            selected = Path((root / "selected.txt").read_text())
            self.assertEqual(payload, (selected / "lib/libavcodec.a").read_bytes())
            self.assertEqual("old API 13.1-only bundle", old.read_text())
            # Reconfiguration must reuse the release-specific extraction offline.
            archive.unlink()
            configured = subprocess.run(
                ["cmake", "-S", str(root), "-B", str(root)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, configured.returncode, configured.stdout + configured.stderr)
            self.assertEqual(payload, (selected / "lib/libavcodec.a").read_bytes())


if __name__ == "__main__":
    unittest.main()
