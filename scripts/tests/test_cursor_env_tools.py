import contextlib
import io
import json
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "scripts/use-venv.zsh"
SOURCE = (
    SCRIPT.read_text().split("<<'CURSOR_PYTHON'\n", 1)[1].split("\nCURSOR_PYTHON", 1)[0]
)


class CursorEnvironmentToolsTests(unittest.TestCase):
    def setUp(self):
        temporary_root = REPOSITORY / ".agent-tmp"
        if temporary_root.is_symlink():
            raise RuntimeError("Temporary root must not be a symlink")
        temporary_root.mkdir(exist_ok=True)
        if temporary_root.resolve().parent != REPOSITORY.resolve():
            raise RuntimeError("Temporary root must remain in the repository")
        self.temporary = tempfile.TemporaryDirectory(
            prefix="cursor-tools-tests-", dir=temporary_root
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = types.ModuleType("cursor_environment_tools")
        # Load only this repository's embedded helper for isolated unit tests.
        exec(compile(SOURCE, str(SCRIPT), "exec"), self.tools.__dict__)  # noqa: S102
        self.workspace = self.root / "workspace"
        self.project = self.workspace / "project with spaces"
        self.interpreter = self.project / ".venv/bin/python"
        self.interpreter.parent.mkdir(parents=True)
        self.interpreter.touch()
        self.extensions = self.root / "cursor/extensions"
        self.extension = self.extensions / "envs-original"
        self.extension.mkdir(parents=True)
        self.version = "1.40.0"
        self.write_registry(self.extension)
        self.transaction = self.root / "transaction"
        self.transaction.mkdir()
        self.cache = self.root / "Code/CachedExtensionVSIXs/envs-darwin-arm64"
        self.installs = []
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(self.tools.platform, "machine", return_value="arm64").start()
        mock.patch.object(
            self.tools, "cursor_cli", return_value=Path("/test/Cursor CLI")
        ).start()
        mock.patch.object(
            self.tools, "cached_vsix_candidates", return_value=iter([self.cache])
        ).start()
        self.real_run_command = self.tools.run_command

    def write_registry(self, directory, target="universal"):
        (directory / "package.json").write_text(
            json.dumps(
                {
                    "publisher": "ms-python",
                    "name": "vscode-python-envs",
                    "version": self.version,
                    "__metadata": {"targetPlatform": target},
                }
            )
        )
        (directory / "dist").mkdir(exist_ok=True)
        (directory / "dist/extension.js").write_text("extension fixture " + target)
        (directory / ".vsixmanifest").write_text(
            '<PackageManifest><Metadata><Identity TargetPlatform="'
            + target
            + '" /></Metadata></PackageManifest>'
        )
        (self.extensions / "extensions.json").write_text(
            json.dumps(
                [
                    {
                        "identifier": {"id": self.tools.ENVS_ID},
                        "relativeLocation": directory.name,
                    }
                ]
            )
        )

    def write_pet(self, directory, *, finds_target=True):
        pet = directory / self.tools.PET_RELATIVE_PATH
        pet.parent.mkdir(parents=True, exist_ok=True)
        output = {
            "environments": (
                [{"executable": str(self.interpreter), "error": None}]
                if finds_target
                else []
            )
        }
        program = (
            "import sys\n"
            "print('pet test' if '--version' in sys.argv else "
            + repr(json.dumps(output))
            + ")\n"
        )
        pet.write_text(
            "#!/bin/sh\nexec "
            + shlex.quote(sys.executable)
            + " -c "
            + shlex.quote(program)
            + ' "$@"\n'
        )
        pet.chmod(0o755)
        return pet

    def write_vsix(
        self,
        path,
        *,
        version=None,
        target="darwin-arm64",
        publisher="ms-python",
        pet=True,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "extension/package.json",
                json.dumps(
                    {
                        "publisher": publisher,
                        "name": "vscode-python-envs",
                        "version": version or self.version,
                    }
                ),
            )
            archive.writestr(
                "extension.vsixmanifest",
                '<PackageManifest xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">'
                '<Metadata><Identity TargetPlatform="'
                + target
                + '" /></Metadata></PackageManifest>',
            )
            if pet:
                archive.writestr(
                    "extension/python-env-tools/bin/pet", "native binary fixture"
                )

    def fake_install(self, command, timeout=30):
        if command[0] != "/test/Cursor CLI":
            return self.real_run_command(command, timeout)
        self.installs.append(command)
        package = Path(command[2])
        if package.name == "original.vsix":
            restored = self.extensions / "envs-restored"
            restored.mkdir(exist_ok=True)
            self.write_registry(restored)
            with zipfile.ZipFile(package) as archive:
                for name in archive.namelist():
                    if name.startswith("extension/"):
                        destination = restored / name.removeprefix("extension/")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(archive.read(name))
            return "restored"
        self.tools.validate_vsix(package, self.version, "darwin-arm64")
        repaired = self.extensions / "envs-repaired"
        repaired.mkdir(exist_ok=True)
        self.write_registry(repaired, target="darwin-arm64")
        self.write_pet(repaired)
        return "installed"

    def ensure(self, *, repair=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.tools.ensure_tools(
                self.extensions,
                self.workspace,
                self.project,
                self.interpreter,
                repair=repair,
                transaction=self.transaction,
            )

    def test_backup_restores_original_package_after_later_failure(self):
        self.write_vsix(self.cache)
        with mock.patch.object(
            self.tools, "run_command", side_effect=self.fake_install
        ):
            self.ensure(repair=True)
            self.assertTrue((self.transaction / "original.vsix").is_file())
            self.tools.restore_package(self.extensions, self.transaction)
        restored = self.tools.installed_extensions(self.extensions)[self.tools.ENVS_ID]
        self.assertEqual(
            (restored / "dist/extension.js").read_text(), "extension fixture universal"
        )
        self.assertFalse((restored / self.tools.PET_RELATIVE_PATH).exists())
        self.assertEqual(len(self.installs), 2)

    def test_rollback_does_not_overwrite_a_concurrent_extension_update(self):
        self.write_vsix(self.cache)
        with mock.patch.object(
            self.tools, "run_command", side_effect=self.fake_install
        ):
            self.ensure(repair=True)
            self.version = "1.42.0"
            self.write_registry(
                self.extensions / "envs-repaired", target="darwin-arm64"
            )
            with self.assertRaisesRegex(RuntimeError, "changed concurrently"):
                self.tools.restore_package(self.extensions, self.transaction)
        self.assertEqual(len(self.installs), 1)
        self.assertTrue((self.transaction / "original.vsix").exists())

    def test_rollback_verifies_restored_package_instead_of_trusting_cli_exit(self):
        self.write_vsix(self.cache)
        with mock.patch.object(
            self.tools, "run_command", side_effect=self.fake_install
        ):
            self.ensure(repair=True)
        with (
            mock.patch.object(self.tools, "run_command", return_value="installed"),
            self.assertRaisesRegex(RuntimeError, "Cannot verify restoration"),
        ):
            self.tools.restore_package(self.extensions, self.transaction)

    def test_missing_pet_without_option_never_downloads_or_installs(self):
        original = (self.extensions / "extensions.json").read_bytes()
        with (
            mock.patch.object(self.tools, "repair_package") as repair,
            self.assertRaisesRegex(
                RuntimeError, "environment discovery is unavailable"
            ),
        ):
            self.ensure()
        repair.assert_not_called()
        self.assertEqual((self.extensions / "extensions.json").read_bytes(), original)
        self.assertFalse((self.workspace / ".agent-tmp").exists())

    def test_healthy_tools_are_not_replaced_even_with_repair_option(self):
        self.write_pet(self.extension)
        with mock.patch.object(self.tools, "repair_package") as repair:
            self.ensure(repair=True)
        repair.assert_not_called()

    def test_existing_but_unusable_pet_requires_explicit_repair(self):
        pet = self.extension / self.tools.PET_RELATIVE_PATH
        pet.parent.mkdir(parents=True)
        pet.write_text("#!/nonexistent/python\n")
        pet.chmod(0o755)
        with self.assertRaisesRegex(
            RuntimeError, "environment discovery is unavailable"
        ):
            self.ensure()

    def test_python_extension_pet_is_accepted_as_supported_fallback(self):
        python = self.extensions / "python"
        self.write_pet(python)
        records = json.loads((self.extensions / "extensions.json").read_text())
        records.append(
            {"identifier": {"id": self.tools.PYTHON_ID}, "relativeLocation": "python"}
        )
        (self.extensions / "extensions.json").write_text(json.dumps(records))
        self.ensure()

    def test_verified_cached_package_is_installed_into_cursor(self):
        self.write_vsix(self.cache)
        with (
            mock.patch.object(self.tools, "run_command", side_effect=self.fake_install),
            mock.patch.object(self.tools, "download_vsix") as download,
        ):
            self.ensure(repair=True)
        download.assert_not_called()
        self.assertEqual(len(self.installs), 1)
        self.assertIn("--force", self.installs[0])
        pet = self.tools.selected_pet(self.tools.installed_extensions(self.extensions))
        self.assertTrue(pet.is_relative_to(self.extensions))
        self.assertFalse(pet.is_symlink())
        self.cache.unlink()
        self.ensure()

    def test_missing_vscode_cache_uses_official_download_with_current_version(self):
        self.version = "1.42.0"
        self.write_registry(self.extension)

        def download(path, version, target):
            self.assertEqual(version, "1.42.0")
            self.assertEqual(target, "darwin-arm64")
            self.write_vsix(path)

        with (
            mock.patch.object(
                self.tools, "download_vsix", side_effect=download
            ) as fetch,
            mock.patch.object(self.tools, "run_command", side_effect=self.fake_install),
        ):
            self.ensure(repair=True)
        fetch.assert_called_once()
        self.assertEqual(len(self.installs), 1)
        self.ensure()

    def test_mismatched_or_incomplete_packages_are_rejected(self):
        for options in (
            {"version": "1.38.0"},
            {"target": "darwin-x64"},
            {"publisher": "other-publisher"},
            {"pet": False},
        ):
            with self.subTest(options=options):
                self.write_vsix(self.cache, **options)
                with self.assertRaises((RuntimeError, KeyError)):
                    self.tools.validate_vsix(self.cache, self.version, "darwin-arm64")

    def test_download_uses_official_versioned_platform_url(self):
        self.write_vsix(self.cache)
        destination = self.root / "downloaded.vsix"
        with (
            mock.patch.object(
                self.tools.urllib.request,
                "urlopen",
                return_value=io.BytesIO(self.cache.read_bytes()),
            ) as request,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.tools.download_vsix(destination, self.version, "darwin-arm64")
        request.assert_called_once_with(
            "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
            "ms-python/vsextensions/vscode-python-envs/1.40.0/vspackage?targetPlatform=darwin-arm64",
            timeout=30,
        )
        self.tools.validate_vsix(destination, self.version, "darwin-arm64")

    def test_bad_download_is_not_installed(self):
        def download(path, version, target):
            self.write_vsix(path, target="universal")

        with (
            mock.patch.object(self.tools, "download_vsix", side_effect=download),
            mock.patch.object(self.tools, "run_command", side_effect=self.fake_install),
            self.assertRaisesRegex(RuntimeError, "does not match"),
        ):
            self.ensure(repair=True)
        self.assertEqual(self.installs, [])

    def test_installer_success_without_usable_pet_is_not_repair_success(self):
        self.write_vsix(self.cache)
        with (
            mock.patch.object(self.tools, "run_command", return_value="installed"),
            self.assertRaisesRegex(RuntimeError, "no pet executable"),
        ):
            self.ensure(repair=True)

    def test_running_pet_without_target_is_not_reported_as_success(self):
        self.write_pet(self.extension, finds_target=False)
        with (
            mock.patch.object(self.tools, "repair_package") as repair,
            self.assertRaisesRegex(RuntimeError, "did not discover"),
        ):
            self.ensure(repair=True)
        repair.assert_not_called()

    def test_timed_out_process_is_reaped(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.tools.run_command(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.05
            )


if __name__ == "__main__":
    unittest.main()
