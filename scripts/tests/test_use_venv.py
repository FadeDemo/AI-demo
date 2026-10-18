import json
import os
import plistlib
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "scripts/use-venv.zsh"
DEFINITIONS, ENTRYPOINT = SCRIPT.read_text().split('\nrequested_path="$PWD"', 1)
ENTRYPOINT = '\nrequested_path="$PWD"' + ENTRYPOINT

# Replace only operating-system interaction; request/configuration preparation,
# selection commands, read-back verification, and rollback run as in the script.
EDITOR_DOUBLES = r"""
uname() { print Darwin; }
run_cursor_automation() {
  if [[ "$1" == prepare-helper ]]; then return 0; fi
  if [[ "$1" == select-environment ]]; then
    if [[ "$VENV_TEST_FAIL_EDITOR" == Cursor || "$VENV_TEST_NO_READBACK" == true ]]; then
      print -u2 "simulated Cursor API selection/read-back failure"
      return 1
    fi
    if [[ -f "$VENV_TEST_STATE/Cursor" && "$(cat "$VENV_TEST_STATE/Cursor")" == "$USE_VENV_DIRECTORY/bin/python" ]]; then
      print "Selected: already aligned in Cursor"
      return 0
    fi
    print 'Cursor API select-environment' >> "$VENV_TEST_CALLS"
    print -r -- "$USE_VENV_DIRECTORY/bin/python" > "$VENV_TEST_STATE/Cursor"
    print "Selected: in Cursor"
    return 0
  fi
  [[ "$1" == reload-window ]] || return 1
  osascript - "$USE_VENV_EDITOR_APPLICATION" "$USE_VENV_EDITOR_PROCESS" "${USE_VENV_WORKSPACE_DIRECTORY:t}" "Developer: Reload Window" </dev/null
}
ensure_cursor_environment_tools() {
  if [[ "${1:-ensure}" == check ]]; then
    print check >> "$VENV_TEST_CHECK_CALLS"
    if [[ "$VENV_TEST_TOOLS_FAIL" == true ]] || [[ "${VENV_TEST_TOOLS_MISSING:-false}" == true && ! -f "$VENV_TEST_STATE/tools-repaired" ]]; then
      print -u2 "Cursor pet is unavailable"
      return 1
    fi
    return 0
  fi
  if [[ "${1:-ensure}" == rollback ]]; then
    print rollback >> "$VENV_TEST_TOOLS_CALLS"
    rm -f "$VENV_TEST_STATE/tools-repaired"
    [[ "$VENV_TEST_ROLLBACK_FAIL" != true ]]
    return
  fi
  print -r -- "$repair_cursor_envs" >> "$VENV_TEST_TOOLS_CALLS"
  if [[ "$VENV_TEST_TOOLS_FAIL" == true ]]; then
    print -u2 "Cursor pet is unavailable; rerun with --repair-cursor-envs"
    return 1
  fi
  if [[ "$repair_cursor_envs" == true && "$VENV_TEST_REPAIR_BACKUP" == true ]]; then
    print original > "$USE_VENV_CURSOR_REPAIR_DIRECTORY/original.vsix"
    print backup > "$USE_VENV_CURSOR_REPAIR_DIRECTORY/backup.json"
    print repaired > "$VENV_TEST_STATE/tools-repaired"
  fi
}
cursor_reload_state() {
  print -r -- "$1|${3:-}" >> "$VENV_TEST_RELOAD_CALLS"
  if [[ "$1" == snapshot ]]; then
    if [[ "$VENV_TEST_REQUIRE_TARGET_BEFORE_RELOAD" == true ]]; then
      python3 - "$USE_VENV_WORKSPACE_DIRECTORY/.vscode/settings.json" <<'PYTHON'
import sys
from pathlib import Path
if '"python-envs.workspaceSearchPaths"' not in Path(sys.argv[1]).read_text():
    sys.exit("Target workspace configuration must be written before reload")
PYTHON
    fi
    print '{}'
  elif [[ "${3:-}" == discovery && "$VENV_TEST_RELOAD_READY" != true ]]; then
    print -u2 "simulated discovery timeout"
    return 1
  fi
}
editor_process_state() {
  [[ "$USE_VENV_EDITOR_PROCESS" == "$VENV_TEST_CLOSED_EDITOR" ]] && return 1
  return 0
}
editor_workspace_selected_venv() {
  local state_file="$VENV_TEST_STATE/$USE_VENV_EDITOR_STORAGE_NAME"
  [[ ! -f "$state_file" ]] || cat "$state_file"
}
osascript() {
  local application_name="$2"
  local process_name="$3"
  print -r -- "$*" >> "$VENV_TEST_CALLS"
  cat >/dev/null
  if [[ "$process_name" == "$VENV_TEST_FAIL_EDITOR" ]]; then
    print -u2 "simulated selection failure"
    return 1
  fi
  if [[ "$VENV_TEST_NO_READBACK" != true && "$*" == *"Python: Select Interpreter"* ]]; then
    print -r -- "$USE_VENV_DIRECTORY/bin/python" > "$VENV_TEST_STATE/$process_name"
  fi
}
"""


class UseVenvTests(unittest.TestCase):
    def setUp(self):
        temporary_root = REPOSITORY / ".agent-tmp"
        if temporary_root.is_symlink():
            raise RuntimeError(
                "The repository temporary directory must not be a symlink"
            )
        temporary_root.mkdir(exist_ok=True)
        if temporary_root.resolve().parent != REPOSITORY.resolve():
            raise RuntimeError(
                "The temporary directory must remain under the repository"
            )
        self.temporary = tempfile.TemporaryDirectory(
            prefix="use-venv-tests-", dir=temporary_root
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.project = self.workspace / "projects/demo project"
        self.venv = self.project / ".venv"
        (self.project / "src").mkdir(parents=True)
        (self.venv / "bin").mkdir(parents=True)
        self.interpreter = self.venv / "bin/python"
        self.interpreter.write_text(
            "#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n'
        )
        self.interpreter.chmod(0o755)
        (self.project / "pyproject.toml").write_text(
            '[project]\nname = "demo-project"\n'
        )
        settings_directory = self.workspace / ".vscode"
        settings_directory.mkdir()
        self.settings = settings_directory / "settings.json"
        self.original_settings = (
            "{\n  // retain this comment\n"
            '  "python.defaultInterpreterPath": "old-python",\n'
            '  "editor.formatOnSave": true,\n'
            '  "ruff.configurationPreference": "filesystemFirst"\n}\n'
        )
        self.settings.write_text(self.original_settings)
        self.launch = settings_directory / "launch.json"
        self.original_launch = json.dumps(
            {"configurations": [{"type": "debugpy", "python": "old-python"}]}
        )
        self.launch.write_text(self.original_launch)
        self.state = self.root / "state"
        self.state.mkdir()
        self.runtime = self.root / "runtime state"
        self.runtime.mkdir()
        self.calls = self.root / "calls"
        self.environment = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(self.root),
            "USE_VENV_STATE_DIRECTORY": str(self.runtime),
            "VENV_TEST_STATE": str(self.state),
            "VENV_TEST_CALLS": str(self.calls),
            "VENV_TEST_CLOSED_EDITOR": "",
            "VENV_TEST_FAIL_EDITOR": "",
            "VENV_TEST_NO_READBACK": "false",
            "VENV_TEST_TOOLS_CALLS": str(self.root / "tools-calls"),
            "VENV_TEST_CHECK_CALLS": str(self.root / "check-calls"),
            "VENV_TEST_API_CALLS": str(self.root / "api-calls"),
            "VENV_TEST_TOOLS_FAIL": "false",
            "VENV_TEST_REPAIR_BACKUP": "false",
            "VENV_TEST_ROLLBACK_FAIL": "false",
            "VENV_TEST_RELOAD_CALLS": str(self.root / "reload-calls"),
            "VENV_TEST_RELOAD_READY": "true",
            "VENV_TEST_REQUIRE_TARGET_BEFORE_RELOAD": "false",
        }

    def run_switch(self, *arguments, **environment):
        return subprocess.run(
            [
                "zsh",
                "-s",
                "--",
                str(self.project),
                "--workspace",
                str(self.workspace),
                *arguments,
            ],
            input=DEFINITIONS + EDITOR_DOUBLES + ENTRYPOINT,
            text=True,
            capture_output=True,
            check=False,
            cwd=REPOSITORY,
            env={**self.environment, **environment},
            timeout=25,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def recorded_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_default_selects_vscode_and_preserves_shared_settings(self):
        result = self.run_switch()

        self.assert_success(result)
        self.assertIn("in VS Code", result.stdout)
        self.assertEqual(len(self.recorded_calls()), 1)
        self.assertIn(
            "Visual Studio Code Code workspace demo-project", self.recorded_calls()[0]
        )
        self.assertFalse((self.state / "Cursor").exists())
        self.assertFalse((self.root / "tools-calls").exists())
        settings_source = self.settings.read_text()
        self.assertIn("// retain this comment", settings_source)
        settings = json.loads(settings_source.replace("// retain this comment", ""))
        self.assertNotIn("python.defaultInterpreterPath", settings)
        self.assertTrue(settings["editor.formatOnSave"])
        self.assertEqual(settings["ruff.configurationPreference"], "filesystemFirst")
        self.assertEqual(
            settings["python.analysis.extraPaths"],
            settings["cursorpyright.analysis.extraPaths"],
        )
        self.assertEqual(
            settings["python-envs.workspaceSearchPaths"],
            ["./projects/demo project/.venv"],
        )
        launch = json.loads(self.launch.read_text())
        self.assertEqual(
            launch["configurations"][0]["python"],
            "${workspaceFolder}/projects/demo project/.venv/bin/python",
        )

    def test_legacy_environment_overrides_and_new_name_precedence(self):
        suffixes = [
            "CURSOR_EXTENSION_DIRECTORY",
            "CURSOR_LOG_DIRECTORY",
            "EDITOR_STORAGE_DIRECTORY",
        ]
        for suffix in suffixes:
            for new_value in (None, "new value"):
                with self.subTest(suffix=suffix, new_value=new_value):
                    old = "VSCODE_VENV_" + suffix
                    new = "USE_VENV_" + suffix
                    environment = {**self.environment, old: "legacy value"}
                    environment.pop(new, None)
                    if new_value is not None:
                        environment[new] = new_value
                    result = subprocess.run(
                        ["zsh", "-s"],
                        input=DEFINITIONS + f'\nprint -r -- "${{{new}}}"\n',
                        text=True,
                        capture_output=True,
                        env=environment,
                        timeout=10,
                        check=False,
                    )
                    self.assert_success(result)
                    self.assertEqual(result.stdout.strip(), new_value or "legacy value")

    def test_default_runtime_directory_is_user_application_support(self):
        environment = self.environment.copy()
        environment.pop("USE_VENV_STATE_DIRECTORY")
        result = subprocess.run(
            ["zsh", "-s"],
            input=DEFINITIONS + '\nprint -r -- "$USE_VENV_STATE_DIRECTORY"\n',
            text=True,
            capture_output=True,
            env=environment,
            timeout=10,
            check=False,
        )
        self.assert_success(result)
        self.assertEqual(
            result.stdout.strip(),
            str(Path.home() / "Library/Application Support/use-venv/transactions"),
        )

    def test_migrates_retained_extension_backup_without_changing_contents(self):
        source = self.workspace / ".agent-tmp/cursor-envs-transaction.example"
        source.mkdir(parents=True)
        (source / "backup.json").write_text('{"version":"1.40.0"}')
        (source / "original.vsix").write_bytes(b"original extension package")
        result = self.run_switch("--editor", "cursor")
        self.assert_success(result)
        self.assertFalse(source.exists())
        migrated = self.runtime / source.name
        self.assertEqual(
            (migrated / "original.vsix").read_bytes(), b"original extension package"
        )
        self.assertEqual((migrated / "backup.json").read_text(), '{"version":"1.40.0"}')

    def test_migration_collision_preserves_both_backups(self):
        source = self.workspace / ".agent-tmp/cursor-envs-transaction.collision"
        source.mkdir(parents=True)
        (source / "backup.json").write_text("{}")
        (source / "original.vsix").write_bytes(b"original application configuration")
        destination = self.runtime / source.name
        destination.mkdir()
        (destination / "original.vsix").write_bytes(b"another backup")
        result = self.run_switch("--editor", "cursor")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preserving both", result.stderr)
        self.assertEqual(
            (source / "original.vsix").read_bytes(),
            b"original application configuration",
        )
        self.assertEqual(
            (destination / "original.vsix").read_bytes(), b"another backup"
        )
        self.assertEqual(self.settings.read_text(), self.original_settings)

    def test_switch_does_not_create_agent_temporary_directory(self):
        result = self.run_switch(
            "--editor", "cursor", "--repair-cursor-envs", VENV_TEST_REPAIR_BACKUP="true"
        )
        self.assert_success(result)
        self.assertFalse((self.workspace / ".agent-tmp").exists())
        self.assertEqual(list(self.runtime.iterdir()), [])

    def incomplete_backup_case(self, folder, filename, contents):
        source = self.workspace / ".agent-tmp" / folder
        source.mkdir(parents=True)
        (source / filename).write_bytes(contents)
        result = self.run_switch("--editor", "cursor")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Incomplete legacy", result.stderr)
        self.assertEqual((source / filename).read_bytes(), contents)
        self.assertFalse((self.runtime / folder).exists())
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertFalse((self.root / "api-calls").exists())

    def test_incomplete_legacy_extension_backup_is_retained_and_reported(self):
        self.incomplete_backup_case(
            "cursor-envs-transaction.partial", "backup.json", b"{}"
        )

    def test_removed_api_repair_option_fails_before_mutation(self):
        result = self.run_switch("--editor", "cursor", "--repair-cursor-api")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown option: --repair-cursor-api", result.stderr)
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertEqual(self.launch.read_text(), self.original_launch)
        self.assertFalse((self.root / "api-calls").exists())

    def test_cursor_selects_cursor_even_when_vscode_is_closed(self):
        result = self.run_switch("--editor", "cursor", VENV_TEST_CLOSED_EDITOR="Code")

        self.assert_success(result)
        self.assertEqual(len(self.recorded_calls()), 1)
        self.assertIn("Cursor API select-environment", self.recorded_calls()[0])
        self.assertIn("in Cursor", result.stdout)
        self.assertEqual(
            (self.state / "Cursor").read_text().strip(), str(self.interpreter)
        )
        self.assertFalse((self.state / "Code").exists())
        self.assertEqual((self.root / "check-calls").read_text().strip(), "check")
        self.assertFalse((self.root / "api-calls").exists())

    def test_both_routes_selection_and_reload_to_each_editor(self):
        result = self.run_switch("--editor", "both", "--reload")

        self.assert_success(result)
        calls = self.recorded_calls()
        self.assertEqual(len(calls), 4)
        self.assertIn("Visual Studio Code Code workspace demo-project", calls[0])
        self.assertIn(
            "Visual Studio Code Code workspace Developer: Reload Window", calls[1]
        )
        self.assertIn("Cursor API select-environment", calls[2])
        self.assertIn("Cursor Cursor workspace Developer: Reload Window", calls[3])

    def test_closed_editor_is_reported_pending_and_never_launched_or_reloaded(self):
        result = self.run_switch(
            "--editor", "both", "--reload", VENV_TEST_CLOSED_EDITOR="Cursor"
        )

        self.assert_success(result)
        self.assertIn("Pending: Cursor is not running", result.stderr)
        self.assertIn("Skipped:     Cursor reload", result.stdout)
        self.assertEqual(len(self.recorded_calls()), 2)
        self.assertTrue(all("Cursor" not in call for call in self.recorded_calls()))
        self.assertNotEqual(self.settings.read_text(), self.original_settings)

    def test_aligned_selection_does_not_open_picker(self):
        (self.state / "Cursor").write_text(str(self.interpreter))

        result = self.run_switch("--editor", "cursor")

        self.assert_success(result)
        self.assertIn("already aligned", result.stdout)
        self.assertEqual(self.recorded_calls(), [])

    def test_failed_selection_rolls_back_shared_files(self):
        result = self.run_switch("--editor", "both", VENV_TEST_FAIL_EDITOR="Cursor")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cursor API interpreter selection failed", result.stderr)
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertEqual(self.launch.read_text(), self.original_launch)
        self.assertEqual(
            (self.state / "Code").read_text().strip(), str(self.interpreter)
        )

    def test_unverified_selection_is_not_reported_as_success(self):
        result = self.run_switch("--editor", "cursor", VENV_TEST_NO_READBACK="true")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cursor API interpreter selection failed", result.stderr)
        self.assertNotIn("Selected:", result.stdout)
        self.assertEqual(self.settings.read_text(), self.original_settings)

    def test_invalid_editor_does_not_modify_shared_files(self):
        for arguments in (("--editor", "other"), ("--editor",)):
            with self.subTest(arguments=arguments):
                result = self.run_switch(*arguments)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("--editor", result.stderr)
                self.assertEqual(self.settings.read_text(), self.original_settings)
                self.assertEqual(self.recorded_calls(), [])

    def test_missing_cursor_tools_stop_before_shared_configuration_changes(self):
        result = self.run_switch("--editor", "both", VENV_TEST_TOOLS_FAIL="true")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--repair-cursor-envs", result.stderr)
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertEqual(self.launch.read_text(), self.original_launch)
        self.assertEqual(self.recorded_calls(), [])

    def test_repair_applies_cursor_updates_before_switching_both_editors(self):
        result = self.run_switch(
            "--editor",
            "both",
            "--repair-cursor-envs",
            VENV_TEST_REPAIR_BACKUP="true",
            VENV_TEST_REQUIRE_TARGET_BEFORE_RELOAD="true",
        )

        self.assert_success(result)
        self.assertEqual((self.root / "tools-calls").read_text().strip(), "true")
        calls = self.recorded_calls()
        self.assertEqual(len(calls), 3)
        self.assertIn("Cursor Cursor workspace Developer: Reload Window", calls[0])
        self.assertIn("Visual Studio Code Code workspace demo-project", calls[1])
        self.assertIn("Cursor API select-environment", calls[2])
        self.assertEqual(
            (self.root / "reload-calls").read_text().splitlines(),
            ["snapshot|", "wait|discovery"],
        )
        self.assertEqual(list((self.runtime).iterdir()), [])

    def test_failed_switch_restores_extension_and_configuration(self):
        result = self.run_switch(
            "--editor",
            "both",
            "--repair-cursor-envs",
            VENV_TEST_REPAIR_BACKUP="true",
            VENV_TEST_FAIL_EDITOR="Code",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            (self.root / "tools-calls").read_text().splitlines(), ["true", "rollback"]
        )
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertEqual(self.launch.read_text(), self.original_launch)
        self.assertIn(
            "Cursor Cursor workspace Developer: Reload Window",
            self.recorded_calls()[-1],
        )
        self.assertEqual(
            (self.root / "reload-calls").read_text().splitlines(),
            ["snapshot|", "wait|discovery", "snapshot|", "wait|activation"],
        )
        self.assertEqual(list((self.runtime).iterdir()), [])

    def test_healthy_tools_do_not_reload_for_repair_flag(self):
        result = self.run_switch("--editor", "cursor", "--repair-cursor-envs")

        self.assert_success(result)
        self.assertEqual(len(self.recorded_calls()), 1)
        self.assertNotIn("Reload Window", self.recorded_calls()[0])
        self.assertFalse((self.root / "reload-calls").exists())
        self.assertEqual(list((self.runtime).iterdir()), [])

    def test_repair_and_reload_option_do_not_reload_cursor_twice(self):
        result = self.run_switch(
            "--editor",
            "both",
            "--repair-cursor-envs",
            "--reload",
            VENV_TEST_REPAIR_BACKUP="true",
        )

        self.assert_success(result)
        calls = self.recorded_calls()
        self.assertEqual(len(calls), 4)
        self.assertEqual(
            sum(
                "Cursor Cursor workspace Developer: Reload Window" in call
                for call in calls
            ),
            1,
        )
        self.assertIn(
            "Visual Studio Code Code workspace Developer: Reload Window", calls[2]
        )

    def test_discovery_timeout_restores_package_and_settings_without_selection(self):
        result = self.run_switch(
            "--editor",
            "cursor",
            "--repair-cursor-envs",
            VENV_TEST_REPAIR_BACKUP="true",
            VENV_TEST_RELOAD_READY="false",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cursor was not ready", result.stderr)
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertEqual(self.launch.read_text(), self.original_launch)
        self.assertEqual(
            (self.root / "tools-calls").read_text().splitlines(), ["true", "rollback"]
        )
        self.assertEqual(len(self.recorded_calls()), 2)
        self.assertTrue(all("Reload Window" in call for call in self.recorded_calls()))
        self.assertEqual(list((self.runtime).iterdir()), [])

    def test_failed_rollback_reload_keeps_original_package_backup(self):
        result = self.run_switch(
            "--editor",
            "cursor",
            "--repair-cursor-envs",
            VENV_TEST_REPAIR_BACKUP="true",
            VENV_TEST_FAIL_EDITOR="Cursor",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "runtime synchronization failed; backup remains at", result.stderr
        )
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertEqual(len(list((self.runtime).glob("*/original.vsix"))), 1)

    def test_failed_extension_rollback_keeps_backup(self):
        result = self.run_switch(
            "--editor",
            "both",
            "--repair-cursor-envs",
            VENV_TEST_REPAIR_BACKUP="true",
            VENV_TEST_FAIL_EDITOR="Code",
            VENV_TEST_ROLLBACK_FAIL="true",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("extension rollback failed; backup remains at", result.stderr)
        backups = list((self.runtime).glob("*/original.vsix"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text().strip(), "original")

    def test_closed_cursor_does_not_commit_an_unverified_repair(self):
        result = self.run_switch(
            "--editor",
            "cursor",
            "--repair-cursor-envs",
            VENV_TEST_REPAIR_BACKUP="true",
            VENV_TEST_CLOSED_EDITOR="Cursor",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cursor selection is pending", result.stderr)
        self.assertEqual(
            (self.root / "tools-calls").read_text().splitlines(), ["true", "rollback"]
        )
        self.assertEqual(self.recorded_calls(), [])

    def test_repair_option_rejects_vscode_only_without_changing_files(self):
        result = self.run_switch("--repair-cursor-envs")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --editor cursor", result.stderr)
        self.assertEqual(self.settings.read_text(), self.original_settings)
        self.assertEqual(self.recorded_calls(), [])

    def test_package_repair_can_proceed_without_api_grant(self):
        result = self.run_switch(
            "--editor",
            "cursor",
            "--repair-cursor-envs",
            VENV_TEST_TOOLS_MISSING="true",
            VENV_TEST_API_MISSING="true",
            VENV_TEST_REPAIR_BACKUP="true",
            VENV_TEST_RELOAD_READY="true",
        )
        self.assert_success(result)
        self.assertFalse((self.root / "api-calls").exists())
        self.assertTrue((self.root / "tools-calls").exists())

    def reload_fixture(self):
        source = DEFINITIONS.split("<<'CURSOR_RELOAD_PYTHON'\n", 1)[1].split(
            "\nCURSOR_RELOAD_PYTHON", 1
        )[0]
        helper = types.ModuleType("cursor_reload")
        # Exercise the repository helper with isolated startup logs.
        exec(compile(source, str(SCRIPT), "exec"), helper.__dict__)  # noqa: S102
        logs = self.root / "logs"
        host = logs / "session/window1/exthost/exthost.log"
        environments = (
            host.parent / "ms-python.vscode-python-envs/Python Environments.log"
        )
        environments.parent.mkdir(parents=True)
        host.write_text("")
        environments.write_text("")
        return helper, logs, host, environments

    def write_reload_logs(self, host, environments, *, workspace=None, discovered=True):
        with host.open("a") as output:
            output.write(
                "Extension host with pid 123 started\n"
                "Extension activated success: ms-python.vscode-python-envs — 47ms\n"
                "Extension host with pid 124 started\n"
            )
        with environments.open("a") as output:
            output.write(
                "[pet] configure: Sending configuration update: "
                + json.dumps(
                    {"workspaceDirectories": [str(workspace or self.workspace)]}
                )
                + "\n"
            )
            if discovered:
                output.write(
                    f"Discovered env: {self.interpreter}\nEnvironment discovery complete: 5 environments\n"
                )

    def test_reload_wait_ignores_old_logs_and_requires_fresh_target_discovery(self):
        helper, logs, host, environments = self.reload_fixture()
        self.write_reload_logs(host, environments)
        before = helper.snapshot(logs)
        self.assertFalse(
            helper.reload_ready(logs, before, self.workspace, str(self.interpreter))
        )

        self.write_reload_logs(host, environments, discovered=False)
        self.assertFalse(
            helper.reload_ready(logs, before, self.workspace, str(self.interpreter))
        )
        self.assertTrue(
            helper.reload_ready(
                logs, before, self.workspace, str(self.interpreter), discovery=False
            )
        )
        self.write_reload_logs(host, environments)
        self.assertTrue(
            helper.reload_ready(logs, before, self.workspace, str(self.interpreter))
        )

    def test_reload_wait_does_not_accept_another_workspace(self):
        helper, logs, host, environments = self.reload_fixture()
        before = helper.snapshot(logs)
        self.write_reload_logs(
            host, environments, workspace=self.root / "another-workspace"
        )
        self.assertFalse(
            helper.reload_ready(logs, before, self.workspace, str(self.interpreter))
        )
        with environments.open("a") as output:
            output.write("configure: Sending configuration update: invalid\n")
        self.assertFalse(
            helper.reload_ready(logs, before, self.workspace, str(self.interpreter))
        )

    def test_reload_wait_reads_new_log_files_and_has_a_bounded_timeout(self):
        helper, logs, _host, _environments = self.reload_fixture()
        before = helper.snapshot(logs)
        other_host = logs / "new-session/window2/exthost/exthost.log"
        other_environments = (
            other_host.parent / "ms-python.vscode-python-envs/Python Environments.log"
        )
        other_environments.parent.mkdir(parents=True)
        self.write_reload_logs(other_host, other_environments)
        helper.wait_for_reload(logs, before, self.workspace, str(self.interpreter))
        with (
            mock.patch.object(helper.time, "monotonic", side_effect=[0, 0, 31]),
            mock.patch.object(helper.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "within 30 seconds"),
        ):
            helper.wait_for_reload(
                logs, helper.snapshot(logs), self.workspace, str(self.interpreter)
            )
        sleep.assert_called_once_with(0.25)

    def test_reload_shell_helper_passes_snapshot_json_without_corruption(self):
        _helper, logs, host, environments = self.reload_fixture()
        commands = """
USE_VENV_CURSOR_LOG_DIRECTORY="$VENV_TEST_LOGS"
USE_VENV_WORKSPACE_DIRECTORY="$VENV_TEST_WORKSPACE"
USE_VENV_DIRECTORY="$VENV_TEST_VENV"
before="$(cursor_reload_state snapshot)"
print 'Extension host with pid 123 started' >> "$VENV_TEST_HOST"
print 'Extension activated success: ms-python.vscode-python-envs' >> "$VENV_TEST_HOST"
print -r -- "$VENV_TEST_CONFIGURATION" >> "$VENV_TEST_ENV_LOG"
cursor_reload_state wait "$before" activation
"""
        result = subprocess.run(
            ["zsh", "-s"],
            input=DEFINITIONS + commands,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env={
                **self.environment,
                "VENV_TEST_LOGS": str(logs),
                "VENV_TEST_WORKSPACE": str(self.workspace),
                "VENV_TEST_VENV": str(self.venv),
                "VENV_TEST_HOST": str(host),
                "VENV_TEST_ENV_LOG": str(environments),
                "VENV_TEST_CONFIGURATION": "configure: Sending configuration update: "
                + json.dumps({"workspaceDirectories": [str(self.workspace)]}),
            },
        )
        self.assert_success(result)

    def test_application_detection_uses_bundle_id_and_distinguishes_failures(self):
        cursor_bundle = "Cursor"
        vscode_bundle = "Visual Studio Code"
        cases = [
            ("cursor", cursor_bundle, 0, 0, cursor_bundle, "Cursor"),
            ("cursor", "", 0, 1, cursor_bundle, "Cursor"),
            ("cursor", "", 1, 2, cursor_bundle, "Cursor"),
            ("cursor", vscode_bundle, 0, 2, cursor_bundle, "Cursor"),
            ("vscode", vscode_bundle, 0, 0, vscode_bundle, "Code"),
            (
                "vscode",
                "Visual Studio Code - Insiders",
                0,
                0,
                vscode_bundle,
                "Code - Insiders",
            ),
        ]
        for editor, bundle, query_status, expected, requested_bundle, storage in cases:
            with self.subTest(editor=editor, bundle=bundle, query_status=query_status):
                commands = """
osascript() {
  cat >/dev/null
  print -r -- "$*" >> "$VENV_TEST_QUERY_CALLS"
  print -r -- "$VENV_TEST_RUNNING_BUNDLE"
  return "$VENV_TEST_QUERY_STATUS"
}
configure_editor "$VENV_TEST_EDITOR"
probe_status=0
editor_process_state || probe_status=$?
print -r -- "$probe_status|$USE_VENV_EDITOR_STORAGE_NAME"
"""
                calls_path = self.root / "query-calls"
                calls_path.write_text("")
                result = subprocess.run(
                    ["zsh", "-s"],
                    input=DEFINITIONS + commands,
                    capture_output=True,
                    text=True,
                    check=False,
                    env={
                        **self.environment,
                        "VENV_TEST_QUERY_CALLS": str(calls_path),
                        "VENV_TEST_EDITOR": editor,
                        "VENV_TEST_RUNNING_BUNDLE": bundle,
                        "VENV_TEST_QUERY_STATUS": str(query_status),
                    },
                    timeout=10,
                )
                self.assert_success(result)
                self.assertEqual(result.stdout.strip(), f"{expected}|{storage}")
                self.assertEqual(
                    calls_path.read_text().splitlines(),
                    [f"-l JavaScript - {requested_bundle}"],
                )

    @unittest.skipUnless(
        shutil.which("osascript"), "Requires macOS JavaScript automation"
    )
    def test_bundle_identifier_is_read_from_metadata_and_missing_id_fails(self):
        javascript = DEFINITIONS.split("<<'JAVASCRIPT'\n", 1)[1].split(
            "\nJAVASCRIPT", 1
        )[0]
        javascript += "\nfunction run(argv) { return bundleIdentifier(argv[0]); }\n"
        application = self.root / "Test Editor.app"
        contents = application / "Contents"
        contents.mkdir(parents=True)
        for identifier in ("example.editor.first", "example.editor.changed", None):
            with self.subTest(identifier=identifier):
                metadata = {
                    "CFBundleExecutable": "test-editor",
                    "CFBundlePackageType": "APPL",
                }
                if identifier is not None:
                    metadata["CFBundleIdentifier"] = identifier
                (contents / "Info.plist").write_bytes(plistlib.dumps(metadata))
                result = subprocess.run(
                    ["osascript", "-l", "JavaScript", "-", str(application)],
                    input=javascript,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if identifier is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Cannot read CFBundleIdentifier", result.stderr)
                else:
                    self.assert_success(result)
                    self.assertEqual(result.stdout.strip(), identifier)

    @unittest.skipUnless(
        shutil.which("osacompile"), "Requires macOS AppleScript compiler"
    )
    def test_native_editor_automation_scripts_compile(self):
        scripts = re.findall(
            r"<<'APPLESCRIPT'\n(.*?)\nAPPLESCRIPT", DEFINITIONS, re.DOTALL
        )
        self.assertTrue(scripts)
        for index, script in enumerate(scripts):
            with self.subTest(script=index):
                source = self.root / f"editor-{index}.applescript"
                source.write_text(script)
                result = subprocess.run(
                    ["osacompile", "-o", str(source.with_suffix(".scpt")), str(source)],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                )
                self.assert_success(result)

    def test_reads_environment_and_legacy_python_selection_from_target_storage(self):
        storage = self.root / "workspaceStorage"
        entry = storage / "workspace-id"
        entry.mkdir(parents=True)
        (entry / "workspace.json").write_text(
            json.dumps({"folder": self.workspace.as_uri()})
        )
        database = entry / "state.vscdb"
        for payload in (
            {
                "ms-python.vscode-python-envs": {
                    "ms-python.vscode-python-envs:venv:WORKSPACE_SELECTED": {
                        str(self.workspace): str(self.interpreter)
                    }
                },
                "ms-python.python": {
                    "autoSelectedWorkspacePythonInterpreter-" + str(self.workspace): {
                        "path": "old-python"
                    }
                },
            },
            {
                "ms-python.python": {
                    "userSelectedEnvPath": json.dumps(
                        {self.workspace.as_uri(): str(self.interpreter)}
                    )
                }
            },
            {
                "ms-python.python": {
                    "autoSelectedWorkspacePythonInterpreter-" + str(self.workspace): {
                        "path": str(self.interpreter)
                    }
                }
            },
        ):
            with self.subTest(payload=payload):
                with closing(sqlite3.connect(database)) as connection, connection:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)"
                    )
                    connection.execute("DELETE FROM ItemTable")
                    connection.executemany(
                        "INSERT INTO ItemTable VALUES (?, ?)",
                        [(key, json.dumps(value)) for key, value in payload.items()],
                    )
                before = database.read_bytes()
                commands = (
                    "\nconfigure_editor cursor\n"
                    'USE_VENV_WORKSPACE_DIRECTORY="$VENV_TEST_WORKSPACE"\n'
                    'USE_VENV_EDITOR_STORAGE_DIRECTORY="$VENV_TEST_STORAGE"\n'
                    "editor_workspace_selected_venv\n"
                )
                result = subprocess.run(
                    ["zsh", "-s"],
                    input=DEFINITIONS + commands,
                    capture_output=True,
                    check=False,
                    text=True,
                    env={
                        **self.environment,
                        "VENV_TEST_WORKSPACE": str(self.workspace),
                        "VENV_TEST_STORAGE": str(storage),
                    },
                    timeout=10,
                )
                self.assert_success(result)
                self.assertEqual(result.stdout.strip(), str(self.interpreter))
                self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
