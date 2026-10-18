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


class CursorDiscoveryCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = REPOSITORY / ".agent-tmp"
        if temporary.is_symlink() or temporary.resolve().parent != REPOSITORY.resolve():
            raise RuntimeError("Unsafe temporary root")
        temporary.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(
            prefix="cursor-discovery-tests-", dir=temporary
        )
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.helper = types.ModuleType("cursor_discovery_cleanup")
        exec(compile(SOURCE, str(SCRIPT), "exec"), self.helper.__dict__)  # noqa: S102
        self.app = {"pid": 100, "path": str(self.root / "Cursor.app")}
        self.project = self.root / "project"
        self.extension = self.root / "extensions"
        self.command = (
            str(self.project / ".venv/bin/python")
            + " "
            + str(
                self.extension
                / "ms-python.python-2025.4.0/python_files/unittestadapter/discovery.py"
            )
            + " --udiscovery -s tests"
        )
        self.original = self.process(110, self.command)
        self.recorded = {
            120: {**self.original, "owner": 110, "owner_started": ("host birth",)}
        }
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(
            self.helper.os.environ,
            {"USE_VENV_CURSOR_EXTENSION_DIRECTORY": str(self.extension)},
        ).start()
        self.table = mock.patch.object(self.helper, "process_table").start()
        self.kill = mock.patch.object(self.helper.os, "kill").start()
        self.clock = 0.0
        mock.patch.object(
            self.helper.time, "monotonic", side_effect=lambda: self.clock
        ).start()
        mock.patch.object(self.helper.time, "sleep", side_effect=self.sleep).start()

    def sleep(self, duration):
        self.clock += duration

    def process(self, parent, command, *, started=("task birth",), state="S"):
        return {
            "parent": parent,
            "command": command,
            "started": started,
            "state": state,
        }

    def orphan(self, **changes):
        return {120: {**self.original, "parent": 1, **changes}}

    def test_snapshot_restricts_app_extension_and_project(self):
        host = self.app["path"] + "/Contents/Frameworks/Cursor Helper (Plugin)"
        self.table.return_value = {
            100: self.process(1, self.app["path"]),
            110: self.process(100, host, started=("host birth",)),
            120: self.original,
            121: self.process(110, self.command),
            122: self.process(
                110, self.command.replace(".py --udiscovery", ".py --execution")
            ),
            123: self.process(
                110, self.command.replace(str(self.extension), "/other/extensions")
            ),
            200: self.process(1, "VS Code"),
            210: self.process(200, host),
            220: self.process(210, self.command),
        }
        with mock.patch.object(
            self.helper,
            "process_cwd",
            side_effect=lambda pid: self.project if pid == 120 else self.root / "other",
        ):
            result = self.helper.discovery_snapshot(self.app, self.project)
        self.assertEqual(result, self.recorded)

    def test_naturally_exited_task_needs_no_signal(self):
        self.table.return_value = {}
        self.helper.clean_discoveries(self.recorded)
        self.kill.assert_not_called()

    def test_task_with_living_owner_is_preserved(self):
        self.table.return_value = {
            **self.orphan(),
            110: self.process(100, "host", started=("host birth",)),
        }
        self.helper.clean_discoveries(self.recorded)
        self.kill.assert_not_called()

    def test_reused_pid_is_preserved(self):
        self.table.return_value = self.orphan(started=("new task birth",))
        self.helper.clean_discoveries(self.recorded)
        self.kill.assert_not_called()

    def test_changed_command_is_preserved(self):
        self.table.return_value = self.orphan(command="another Python application")
        self.helper.clean_discoveries(self.recorded)
        self.kill.assert_not_called()

    def test_zombie_is_treated_as_exited_without_signal(self):
        self.table.return_value = self.orphan(state="Z", command="(Python)")
        self.helper.clean_discoveries(self.recorded)
        self.kill.assert_not_called()

    def test_only_recorded_orphan_is_terminated(self):
        state = {
            **self.orphan(),
            999: self.process(1, self.command, started=("new discovery",)),
        }
        self.table.side_effect = lambda: dict(state)
        self.kill.side_effect = lambda pid, sig: state.pop(pid)
        self.helper.clean_discoveries(self.recorded)
        self.kill.assert_called_once_with(120, self.helper.signal.SIGTERM)
        self.assertIn(999, state)

    def test_identity_is_rechecked_before_signal(self):
        before = self.orphan()
        changed = self.orphan(started=("replacement",))
        with mock.patch.object(
            self.helper, "wait_for_discoveries", side_effect=[before, changed]
        ):
            self.table.return_value = changed
            self.helper.clean_discoveries(self.recorded)
        self.kill.assert_not_called()

    def test_stubborn_orphan_gets_term_then_kill_with_bounded_wait(self):
        state = self.orphan()
        self.table.side_effect = lambda: dict(state)

        def kill(pid, sig):
            if sig == self.helper.signal.SIGKILL:
                state.pop(pid)

        self.kill.side_effect = kill
        self.helper.clean_discoveries(self.recorded)
        self.assertEqual(
            self.kill.call_args_list,
            [
                mock.call(120, self.helper.signal.SIGTERM),
                mock.call(120, self.helper.signal.SIGKILL),
            ],
        )
        self.assertLess(self.clock, 6.5)

    def test_failed_exit_verification_reports_exact_pid(self):
        self.table.return_value = self.orphan()
        with self.assertRaisesRegex(RuntimeError, "120"):
            self.helper.clean_discoveries(self.recorded)
        self.assertLess(self.clock, 6.5)

    def test_cleanup_runs_when_reload_or_restart_fails(self):
        with (
            mock.patch.object(
                self.helper, "discovery_snapshot", return_value=self.recorded
            ),
            mock.patch.object(self.helper, "clean_discoveries") as clean,
            self.assertRaisesRegex(RuntimeError, "reload failed"),
            self.helper.discovery_cleanup(self.app, self.project),
        ):
            raise RuntimeError("reload failed")
        clean.assert_called_once_with(self.recorded)

    def test_cleanup_error_does_not_mask_operation_error(self):
        with (
            mock.patch.object(
                self.helper, "discovery_snapshot", return_value=self.recorded
            ),
            mock.patch.object(
                self.helper,
                "clean_discoveries",
                side_effect=RuntimeError("cleanup failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "original error"),
            self.helper.discovery_cleanup(self.app, self.project),
        ):
            raise RuntimeError("original error")

    def test_cleanup_failure_is_reported_after_successful_operation(self):
        with (
            mock.patch.object(
                self.helper, "discovery_snapshot", return_value=self.recorded
            ),
            mock.patch.object(
                self.helper,
                "clean_discoveries",
                side_effect=RuntimeError("cleanup failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "cleanup failed"),
            self.helper.discovery_cleanup(self.app, self.project),
        ):
            pass

    def test_window_reload_uses_cleanup_on_both_paths(self):
        for error in (None, RuntimeError("reload failed")):
            with (
                self.subTest(error=error),
                mock.patch.object(self.helper, "app_info", return_value=self.app),
                mock.patch.object(
                    self.helper, "discovery_snapshot", return_value=self.recorded
                ) as snapshot,
                mock.patch.object(self.helper, "clean_discoveries") as clean,
                mock.patch.object(
                    self.helper, "reload_workspace_window", side_effect=error
                ),
            ):
                if error:
                    with self.assertRaisesRegex(RuntimeError, "reload failed"):
                        self.helper.reload_window(self.root, self.project)
                else:
                    self.helper.reload_window(self.root, self.project)
                snapshot.assert_called_once_with(self.app, self.project)
                clean.assert_called_once_with(self.recorded)

    def test_app_restart_cleans_before_launching_new_instance(self):
        events = []
        with (
            mock.patch.object(
                self.helper, "app_info", side_effect=[self.app, None, self.app]
            ),
            mock.patch.object(
                self.helper, "discovery_snapshot", return_value=self.recorded
            ),
            mock.patch.object(
                self.helper,
                "clean_discoveries",
                side_effect=lambda recorded: events.append("clean"),
            ),
            mock.patch.object(self.helper, "editor_environment", return_value={}),
            mock.patch.object(
                self.helper,
                "run",
                side_effect=lambda argv, **kwargs: events.append(argv[0]),
            ),
        ):
            self.helper.restart(self.app, self.root, self.project)
        self.assertEqual(events, ["osascript", "clean", "open"])

    def test_refused_app_quit_still_runs_cleanup(self):
        with (
            mock.patch.object(self.helper, "app_info", return_value=self.app),
            mock.patch.object(
                self.helper, "discovery_snapshot", return_value=self.recorded
            ),
            mock.patch.object(self.helper, "clean_discoveries") as clean,
            mock.patch.object(
                self.helper, "run", side_effect=RuntimeError("quit refused")
            ) as run,
            self.assertRaisesRegex(RuntimeError, "quit refused"),
        ):
            self.helper.restart(self.app, self.root, self.project)
        clean.assert_called_once_with(self.recorded)
        run.assert_called_once()

    def test_reload_command_receives_selected_project(self):
        with mock.patch.object(self.helper, "reload_window") as reload:
            self.helper.execute(
                "reload-window", self.root, self.project / ".venv/bin/python"
            )
        reload.assert_called_once_with(self.root, self.project)


if __name__ == "__main__":
    unittest.main()
