import json
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "scripts/use-venv.zsh"
SOURCE = (
    SCRIPT.read_text()
    .split("<<'CURSOR_AUTOMATION_PYTHON'\n", 1)[1]
    .split("\nCURSOR_AUTOMATION_PYTHON", 1)[0]
)


class CursorAutomationTests(unittest.TestCase):
    def setUp(self):
        temporary = REPOSITORY / ".agent-tmp"
        if temporary.is_symlink() or temporary.resolve().parent != REPOSITORY.resolve():
            raise RuntimeError("Unsafe temporary root")
        temporary.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(
            prefix="cursor-automation-tests-", dir=temporary
        )
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.helper = types.ModuleType("cursor_automation")
        exec(compile(SOURCE, str(SCRIPT), "exec"), self.helper.__dict__)  # noqa: S102
        self.app = {"path": str(self.root / "Cursor.app"), "pid": 100}
        self.product = Path(self.app["path"]) / "Contents/Resources/app/product.json"
        self.product.parent.mkdir(parents=True)
        self.original = json.dumps(
            {
                "other": 42,
                "extensionEnabledApiProposals": {
                    "ms-python.vscode-python-envs": ["terminalShellEnv"]
                },
            },
            indent=2,
        ).encode()
        self.product.write_bytes(self.original)
        self.transaction = self.root / "runtime state/probe"
        self.interpreter = self.root / "project/.venv/bin/python"
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(
            self.helper.os.environ,
            {"USE_VENV_STATE_DIRECTORY": str(self.root / "runtime state")},
        ).start()
        mock.patch.object(self.helper, "app_info", return_value=self.app).start()
        self.external = mock.patch.object(self.helper, "external_process").start()
        self.restart = mock.patch.object(
            self.helper, "restart", return_value=self.app
        ).start()
        mock.patch.object(self.helper, "discovery_snapshot", return_value={}).start()

    def test_force_helper_reinstall_bypasses_live_matching_instance(self):
        with (
            mock.patch.object(
                self.helper.helper_transport, "find", return_value={"session": "old"}
            ) as find,
            mock.patch.object(
                self.helper.helper_transport, "reload", return_value={"session": "new"}
            ) as reload,
            mock.patch.object(self.helper, "run") as run,
        ):
            result = self.helper.helper_ready(self.app, self.root, force=True)
        self.assertEqual(result["session"], "new")
        self.assertEqual(find.call_count, 1)
        self.assertIn("--install-extension", run.call_args.args[0])
        self.assertIn("--force", run.call_args.args[0])
        reload.assert_called_once_with(self.root, self.helper.HELPER_REVISION)

    def test_runtime_directory_is_private_and_separate_from_workspace(self):
        root = self.helper.runtime_directory()
        self.assertEqual(root, self.root / "runtime state")
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.root / ".agent-tmp").exists())

    def test_runtime_directory_rejects_symbolic_link(self):
        target = self.root / "real runtime"
        target.mkdir()
        link = self.root / "linked runtime"
        link.symlink_to(target, target_is_directory=True)
        with (
            mock.patch.dict(
                self.helper.os.environ, {"USE_VENV_STATE_DIRECTORY": str(link)}
            ),
            self.assertRaisesRegex(RuntimeError, "non-symlink"),
        ):
            self.helper.runtime_directory()

    def test_gui_environment_does_not_inherit_runner_color_settings(self):
        with (
            mock.patch.dict(
                self.helper.os.environ,
                {"NO_COLOR": "1", "TERM": "dumb", "KEEP": "yes"},
                clear=True,
            ),
            mock.patch.object(
                self.helper.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 1, "", ""),
            ),
        ):
            environment = self.helper.editor_environment()
            self.assertNotIn("NO_COLOR", environment)
            self.assertNotIn("TERM", environment)
            self.assertEqual(environment["KEEP"], "yes")
            self.assertEqual(self.helper.os.environ["NO_COLOR"], "1")

    def test_gui_environment_preserves_desktop_color_policy(self):
        def launchctl(arguments, **kwargs):
            if arguments[-1] == "NO_COLOR":
                return subprocess.CompletedProcess(arguments, 0, "1\n", "")
            return subprocess.CompletedProcess(arguments, 1, "", "")

        with mock.patch.object(self.helper.subprocess, "run", side_effect=launchctl):
            self.assertEqual(self.helper.editor_environment()["NO_COLOR"], "1")

    def test_empty_desktop_values_are_removed_instead_of_exported(self):
        with (
            mock.patch.dict(self.helper.os.environ, {"NO_COLOR": "1", "TERM": "dumb"}),
            mock.patch.object(
                self.helper.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ),
        ):
            environment = self.helper.editor_environment()
        self.assertNotIn("NO_COLOR", environment)
        self.assertNotIn("TERM", environment)

    def test_reload_uses_helper_and_waits_for_new_session(self):
        with (
            mock.patch.object(self.helper, "helper_ready"),
            mock.patch.object(self.helper.helper_transport, "reload") as reload,
        ):
            self.helper.reload_window(self.root)
        reload.assert_called_once_with(self.root, self.helper.HELPER_REVISION)
        self.restart.assert_not_called()
        self.assertEqual(self.product.read_bytes(), self.original)

    def test_failed_helper_reload_propagates(self):
        with (
            mock.patch.object(self.helper, "helper_ready"),
            mock.patch.object(
                self.helper.helper_transport,
                "reload",
                side_effect=RuntimeError("no new session"),
            ),
            self.assertRaisesRegex(RuntimeError, "no new session"),
        ):
            self.helper.reload_window(self.root)

    def test_probe_uses_exact_workspace_and_project(self):
        expected = {
            "venv": str(self.interpreter.parent.parent),
            "python": str(self.interpreter),
        }
        with (
            mock.patch.object(self.helper, "helper_ready", return_value={"port": 123}),
            mock.patch.object(
                self.helper.helper_transport, "request", return_value=expected
            ) as request,
        ):
            result = self.helper.probe_terminal(
                self.app, self.root, self.interpreter, self.transaction
            )
        self.assertEqual(result, expected)
        self.assertEqual(request.call_args.args[1:3], (self.root, "probe"))
        self.assertEqual(
            request.call_args.kwargs["project"],
            str(self.interpreter.parent.parent.parent),
        )
        self.assertTrue(request.call_args.kwargs["requireActivation"])

    def test_failed_terminal_verification_propagates(self):
        with (
            mock.patch.object(self.helper, "helper_ready", return_value={"port": 123}),
            mock.patch.object(
                self.helper.helper_transport,
                "request",
                side_effect=RuntimeError("did not automatically activate"),
            ),
            self.assertRaisesRegex(RuntimeError, "did not automatically activate"),
        ):
            self.helper.probe_terminal(
                self.app, self.root, self.interpreter, self.transaction
            )
