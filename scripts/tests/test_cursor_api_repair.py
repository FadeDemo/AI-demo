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
    .split("<<'CURSOR_API_PYTHON'\n", 1)[1]
    .split("\nCURSOR_API_PYTHON", 1)[0]
)


class CursorApiRepairTests(unittest.TestCase):
    def setUp(self):
        temporary = REPOSITORY / ".agent-tmp"
        if temporary.is_symlink() or temporary.resolve().parent != REPOSITORY.resolve():
            raise RuntimeError("Unsafe temporary root")
        temporary.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(
            prefix="cursor-api-tests-", dir=temporary
        )
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.helper = types.ModuleType("cursor_api_repair")
        exec(compile(SOURCE, str(SCRIPT), "exec"), self.helper.__dict__)  # noqa: S102
        self.app = {"path": str(self.root / "Cursor.app"), "pid": 100}
        self.product = Path(self.app["path"]) / "Contents/Resources/app/product.json"
        self.product.parent.mkdir(parents=True)
        self.original = json.dumps(
            {
                "other": 42,
                "extensionEnabledApiProposals": {
                    self.helper.EXTENSION: ["terminalShellEnv"]
                },
            },
            indent=2,
        ).encode()
        self.product.write_bytes(self.original)
        self.transaction = self.root / "runtime state/cursor-api-repair"
        self.interpreter = self.root / "project/.venv/bin/python"
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(
            self.helper.os.environ,
            {"USE_VENV_STATE_DIRECTORY": str(self.root / "runtime state")},
        ).start()
        mock.patch.object(self.helper, "app_info", return_value=self.app).start()
        self.external = mock.patch.object(self.helper, "external_process").start()
        mock.patch.object(self.helper, "preflight").start()
        self.restart = mock.patch.object(
            self.helper, "restart", return_value=self.app
        ).start()
        self.verify = mock.patch.object(self.helper, "verify_terminal").start()
        mock.patch.object(self.helper, "discovery_snapshot", return_value={}).start()

    def execute(self, action="repair-cursor-api"):
        self.helper.execute(action, self.root, self.interpreter)

    def test_minimal_grant_only_and_success_cleanup(self):
        self.execute()
        expected = json.loads(self.original)
        expected["extensionEnabledApiProposals"][self.helper.EXTENSION].append(
            self.helper.PROPOSAL
        )
        self.assertEqual(json.loads(self.product.read_bytes()), expected)
        self.verify.assert_called_once()
        self.restart.assert_called_once_with(
            self.app, self.root, self.interpreter.parent.parent.parent
        )
        self.assertFalse(self.transaction.exists())

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

    def test_existing_grant_skips_mutation_restart_and_backup(self):
        applied = self.helper.patch_product(self.original)
        self.product.write_bytes(applied)
        self.execute()
        self.assertEqual(self.product.read_bytes(), applied)
        self.restart.assert_not_called()
        self.verify.assert_not_called()
        self.assertFalse(self.transaction.exists())

    def test_existing_grant_does_not_require_an_external_terminal(self):
        self.product.write_bytes(self.helper.patch_product(self.original))
        self.external.side_effect = RuntimeError("outside Cursor")
        self.execute("repair-cursor-api-staged")
        self.external.assert_not_called()
        self.restart.assert_not_called()
        self.verify.assert_not_called()
        self.assertFalse(self.transaction.exists())

    def test_read_only_check_reports_missing_grant_without_changing_files(self):
        with self.assertRaisesRegex(
            RuntimeError, "missing the terminalDataWriteEvent grant"
        ):
            self.execute("check-cursor-api")
        self.assertEqual(self.product.read_bytes(), self.original)
        self.assertFalse(self.transaction.exists())
        self.restart.assert_not_called()
        self.verify.assert_not_called()

    def test_read_only_check_accepts_existing_grant(self):
        self.product.write_bytes(self.helper.patch_product(self.original))
        self.execute("check-cursor-api")
        self.restart.assert_not_called()
        self.verify.assert_not_called()

    def test_extension_without_api_requirement_needs_no_grant(self):
        self.helper.preflight.return_value = False
        self.execute("check-cursor-api")
        self.execute("repair-cursor-api-staged")
        self.assertEqual(self.product.read_bytes(), self.original)
        self.restart.assert_not_called()
        self.assertFalse(self.transaction.exists())

    def test_staged_api_repair_keeps_backup_until_commit(self):
        self.execute("repair-cursor-api-staged")
        self.assertTrue((self.transaction / "original.json").is_file())
        self.assertEqual(
            self.product.read_bytes(), self.helper.patch_product(self.original)
        )
        self.verify.assert_called_once()
        self.execute("commit-cursor-api")
        self.assertFalse(self.transaction.exists())

    def test_staged_api_repair_can_be_rolled_back(self):
        self.execute("repair-cursor-api-staged")
        self.execute("rollback-cursor-api")
        self.assertEqual(self.product.read_bytes(), self.original)
        self.assertFalse(self.transaction.exists())

    def test_commit_rejects_concurrent_application_change(self):
        self.execute("repair-cursor-api-staged")
        changed = self.product.read_bytes() + b"\n"
        self.product.write_bytes(changed)
        with self.assertRaisesRegex(RuntimeError, "changed before commit"):
            self.execute("commit-cursor-api")
        self.assertTrue((self.transaction / "original.json").is_file())
        self.assertEqual(self.product.read_bytes(), changed)

    def test_failed_terminal_verification_restores_and_restarts(self):
        self.verify.side_effect = RuntimeError("activation failed")
        with self.assertRaisesRegex(RuntimeError, "activation failed"):
            self.execute()
        self.assertEqual(self.product.read_bytes(), self.original)
        self.assertEqual(self.restart.call_count, 2)
        self.assertFalse(self.transaction.exists())

    def test_concurrent_change_is_not_overwritten(self):
        def fail(*args):
            self.product.write_bytes(b'{"updated":true}')
            raise RuntimeError("activation failed")

        self.verify.side_effect = fail
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual(self.product.read_bytes(), b'{"updated":true}')
        self.assertEqual(
            (self.transaction / "original.json").read_bytes(), self.original
        )
        self.assertEqual(self.restart.call_count, 1)

    def test_failed_rollback_restart_retains_recoverable_backup(self):
        self.restart.side_effect = RuntimeError("restart failed")
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual(self.product.read_bytes(), self.original)
        self.assertTrue(self.transaction.exists())
        self.restart.side_effect = None
        self.execute("rollback-cursor-api")
        self.assertFalse(self.transaction.exists())

    def test_inside_cursor_fails_before_mutation(self):
        self.external.side_effect = RuntimeError("outside Cursor")
        with self.assertRaisesRegex(RuntimeError, "outside Cursor"):
            self.execute()
        self.assertEqual(self.product.read_bytes(), self.original)
        self.assertFalse(self.transaction.exists())
        self.restart.assert_not_called()

    def test_denied_write_does_not_restart_cursor(self):
        with (
            mock.patch.object(
                self.helper, "replace_guarded", side_effect=PermissionError("denied")
            ),
            self.assertRaises(PermissionError),
        ):
            self.execute()
        self.assertEqual(self.product.read_bytes(), self.original)
        self.assertFalse(self.transaction.exists())
        self.restart.assert_not_called()

    def test_unfinished_repair_is_not_overwritten(self):
        self.transaction.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "Unfinished repair"):
            self.execute()
        self.assertEqual(self.product.read_bytes(), self.original)

    def test_unknown_product_structure_rejected(self):
        with self.assertRaisesRegex(TypeError, "Unexpected"):
            self.helper.patch_product(b"{}")

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

    def test_failed_terminal_verification_propagates_to_repair_rollback(self):
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
