"""Fast, isolated checks for the Arch builder's no-network preflight."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCH_DIR = PROJECT_ROOT / "packaging" / "arch"
REQUIRED = (
    "build.sh",
    "PKGBUILD",
    "dependencies.sh",
    "sources.conf",
    "container-prepare.sh",
    "container-build.sh",
    "smoke-test.sh",
    "monitorize.install",
    "monitorize-wrapper",
    "monitorize-remote-login-guard.hook",
    "monitorize-remote-login-remove.hook",
)


class ArchRecipeStagingTest(unittest.TestCase):
    def test_recipe_stages_every_package_startdir_input(self) -> None:
        builder = (ARCH_DIR / "build.sh").read_text()
        staging = re.search(r'for helper in .*?\ndone', builder, re.DOTALL).group()
        recipe = (ARCH_DIR / "PKGBUILD").read_text()
        inputs = re.findall(r'\$\{startdir\}/([^"\s]+)', recipe.split('package() {', 1)[1])
        self.assertIn("monitorize-remote-login-guard.hook", inputs)
        for cuda in ("0", "1"):
            with self.subTest(cuda=cuda), tempfile.TemporaryDirectory() as directory:
                subprocess.run(
                    ["bash", "-eu", "-c", staging], check=True,
                    env={**os.environ, "SCRIPT_DIR": str(ARCH_DIR),
                         "recipe_root": directory, "MONITORIZE_ENABLE_CUDA": cuda},
                )
                for name in inputs:
                    self.assertEqual((Path(directory) / name).read_bytes(),
                                     (ARCH_DIR / name).read_bytes())


class ArchBuilderPreflightTest(unittest.TestCase):
    def git(self, cwd: Path, *arguments: str) -> str:
        result = subprocess.run(
            ("git", "-c", "commit.gpgsign=false", *arguments), cwd=cwd, check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"},
        )
        return result.stdout.strip()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="monitorize-arch-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        deps = self.root / "deps"
        deps.mkdir()
        self.git(deps, "init", "-q")
        (deps / "file").write_text("build dependencies\n")
        self.git(deps, "add", ".")
        self.git(deps, "commit", "-qm", "Initial build dependencies")
        ffmpeg_tag = next(line.split("=", 1)[1] for line in
                          (ARCH_DIR / "sources.conf").read_text().splitlines()
                          if line.startswith("SUNSHINE_FFMPEG_TAG="))
        self.git(deps, "tag", ffmpeg_tag)

        sunshine = self.root / "sunshine"
        sunshine.mkdir()
        self.git(sunshine, "init", "-q")
        self.git(sunshine, "-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(deps), "third-party/build-deps")
        self.git(sunshine, "commit", "-qam", "Pin build dependencies")
        sunshine_commit = self.git(sunshine, "rev-parse", "HEAD")

        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.git(self.checkout, "init", "-q")
        destination = self.checkout / "packaging" / "arch"
        destination.mkdir(parents=True)
        for filename in REQUIRED:
            shutil.copy2(ARCH_DIR / filename, destination / filename)
        source_config = destination / "sources.conf"
        source_pin = next(line.split("=", 1)[1] for line in
                          source_config.read_text().splitlines()
                          if line.startswith("SUNSHINE_COMMIT="))
        source_config.write_text(source_config.read_text().replace(source_pin, sunshine_commit))
        shutil.copy2(PROJECT_ROOT / "pyproject.toml", self.checkout / "pyproject.toml")
        self.git(self.checkout, "-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(sunshine), "external/sunshine")
        self.git(self.checkout, "-c", "protocol.file.allow=always", "submodule", "update",
                 "--init", "--recursive")
        self.git(self.checkout, "add", ".")
        self.git(self.checkout, "commit", "-qm", "Initial source snapshot")

        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        self.podman_log = self.root / "podman.log"
        fake_podman = fake_bin / "podman"
        fake_podman.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$MONITORIZE_TEST_PODMAN_LOG\"\n"
            "case \"$1 $2\" in\n"
            "  'info --format') echo true;;\n"
            "  'image exists') exit \"${MONITORIZE_TEST_IMAGE_EXISTS:-1}\";;\n"
            "  run*) echo 'simulated container failure' >&2; exit 99;;\n"
            "  *) exit 99;;\n"
            "esac\n"
        )
        fake_podman.chmod(0o755)
        self.environment = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "MONITORIZE_TEST_PODMAN_LOG": str(self.podman_log),
        }

    def run_builder(self, *, image_exists: bool, no_cuda: bool = False) -> subprocess.CompletedProcess[str]:
        arguments = ("--no-cuda", "--rebuild-offline") if no_cuda else ("--rebuild-offline",)
        return subprocess.run(
            (str(self.checkout / "packaging/arch/build.sh"), *arguments),
            cwd=self.checkout, env={**self.environment,
                                    "MONITORIZE_TEST_IMAGE_EXISTS": "0" if image_exists else "1"},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

    def test_offline_rebuild_never_starts_container_without_prepared_image(self) -> None:
        result = self.run_builder(image_exists=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing prepared image", result.stderr)
        self.assertNotIn("run ", self.podman_log.read_text())

    def test_missing_package_hook_fails_before_container_start(self) -> None:
        self.git(self.checkout, "rm", "packaging/arch/monitorize-remote-login-guard.hook")
        self.git(self.checkout, "commit", "-qm", "Remove package hook")
        result = self.run_builder(image_exists=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Commit packaging/arch/monitorize-remote-login-guard.hook", result.stderr)
        self.assertNotIn("run ", self.podman_log.read_text())

    def test_no_cuda_offline_requires_a_separate_prepared_image(self) -> None:
        self.run_builder(image_exists=False)
        cuda_image = next(line for line in self.podman_log.read_text().splitlines()
                          if line.startswith("image exists "))
        self.podman_log.unlink()
        result = self.run_builder(image_exists=False, no_cuda=True)
        no_cuda_image = next(line for line in self.podman_log.read_text().splitlines()
                             if line.startswith("image exists "))
        self.assertNotEqual(cuda_image, no_cuda_image)
        self.assertIn("Missing prepared image", result.stderr)
        self.assertNotIn("run ", self.podman_log.read_text())

    def test_offline_rebuild_never_starts_container_without_cached_sources(self) -> None:
        result = self.run_builder(image_exists=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing or invalid cached", result.stderr)
        self.assertNotIn("run ", self.podman_log.read_text())

    def test_build_logic_change_reuses_dependency_image(self) -> None:
        self.run_builder(image_exists=False)
        first_image = next(line for line in self.podman_log.read_text().splitlines()
                           if line.startswith("image exists "))
        self.podman_log.unlink()
        build_script = self.checkout / "packaging/arch/container-build.sh"
        build_script.write_text(build_script.read_text() + "\n# source-only change\n")
        self.git(self.checkout, "add", "packaging/arch/container-build.sh")
        self.git(self.checkout, "commit", "-qm", "Adjust build logic")
        self.run_builder(image_exists=False)
        second_image = next(line for line in self.podman_log.read_text().splitlines()
                            if line.startswith("image exists "))
        self.assertEqual(first_image, second_image)

    def test_failed_build_preserves_previous_package_and_writes_log(self) -> None:
        package_dir = self.checkout / "dist/arch/x86_64"
        package_dir.mkdir(parents=True)
        previous = package_dir / "monitorize-0.33-archlinux-x86_64.pkg.tar.zst"
        previous.write_text("previous successful package")
        result = subprocess.run(
            (str(self.checkout / "packaging/arch/build.sh"),),
            cwd=self.checkout, env=self.environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(previous.read_text(), "previous successful package")
        self.assertIn("simulated container failure", (
            self.checkout / "dist/arch/failed-build.log").read_text())


if __name__ == "__main__":
    unittest.main()
