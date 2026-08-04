#!/bin/zsh
# use-venv-managed-command

set -eu
typeset -gr VSCODE_VENV_SCRIPT_PATH="${0:A}"

print_usage() {
  cat <<'EOF'
Usage: use-venv [PROJECT_OR_VENV_PATH] [--workspace WORKSPACE_PATH] [--reload]
       use-venv --install
       use-venv --uninstall

Switch a VS Code workspace to an existing Python .venv, update workspace and
debug settings, and let Python Environments discover it.

Arguments:
  PROJECT_OR_VENV_PATH  Project directory, .venv directory, or a directory
                        inside the project. Defaults to the current directory.
  --workspace PATH      VS Code workspace root. By default, search upward for
                        .vscode/settings.json and then for .git.
  --install             Install or update a standalone ~/.local/bin/use-venv.
  --uninstall           Remove the managed ~/.local/bin/use-venv installation.
  --reload              Also attempt a guarded VS Code window reload on macOS.
                        A reload failure rolls back the file changes.
  --no-reload           Compatibility alias for the default no-reload behavior.
  -h, --help            Show this help.
EOF
}

fail() {
  print -u2 "use-venv: $1"
  exit 1
}

typeset -g VSCODE_VENV_TRANSACTION_ACTIVE=false
typeset -g VSCODE_VENV_TRANSACTION_APPLIED=false
typeset -g VSCODE_VENV_TRANSACTION_DIRECTORY=""
typeset -g VSCODE_VENV_TRANSACTION_SETTINGS_PATH=""
typeset -g VSCODE_VENV_TRANSACTION_LAUNCH_PATH=""
typeset -g VSCODE_VENV_TRANSACTION_SETTINGS_ORIGINAL_EXISTS=false
typeset -g VSCODE_VENV_TRANSACTION_LAUNCH_ORIGINAL_EXISTS=false
typeset -g VSCODE_VENV_TRANSACTION_SETTINGS_APPLIED_EXISTS=false
typeset -g VSCODE_VENV_TRANSACTION_LAUNCH_APPLIED_EXISTS=false

cleanup_file_transaction() {
  local transaction_directory="$VSCODE_VENV_TRANSACTION_DIRECTORY"
  [[ -n "$transaction_directory" ]] || return 0

  rm -f \
    "$transaction_directory/settings.original" \
    "$transaction_directory/settings.applied" \
    "$transaction_directory/launch.original" \
    "$transaction_directory/launch.applied"
  rmdir "$transaction_directory"
  VSCODE_VENV_TRANSACTION_DIRECTORY=""
}

begin_file_transaction() {
  local temporary_root="${TMPDIR:-/tmp}"
  local settings_path="$VSCODE_VENV_WORKSPACE_DIRECTORY/.vscode/settings.json"
  local launch_path="$VSCODE_VENV_WORKSPACE_DIRECTORY/.vscode/launch.json"

  VSCODE_VENV_TRANSACTION_DIRECTORY="$(
    mktemp -d "$temporary_root/use-venv.XXXXXXXX"
  )" || fail "cannot create a transaction directory"
  VSCODE_VENV_TRANSACTION_SETTINGS_PATH="$settings_path"
  VSCODE_VENV_TRANSACTION_LAUNCH_PATH="$launch_path"

  if [[ -f "$settings_path" ]]; then
    if ! cp -p \
      "$settings_path" \
      "$VSCODE_VENV_TRANSACTION_DIRECTORY/settings.original"; then
      cleanup_file_transaction
      fail "cannot back up $settings_path"
    fi
    VSCODE_VENV_TRANSACTION_SETTINGS_ORIGINAL_EXISTS=true
  fi
  if [[ -f "$launch_path" ]]; then
    if ! cp -p \
      "$launch_path" \
      "$VSCODE_VENV_TRANSACTION_DIRECTORY/launch.original"; then
      cleanup_file_transaction
      fail "cannot back up $launch_path"
    fi
    VSCODE_VENV_TRANSACTION_LAUNCH_ORIGINAL_EXISTS=true
  fi

  VSCODE_VENV_TRANSACTION_ACTIVE=true
}

capture_applied_file_transaction() {
  local settings_path="$VSCODE_VENV_TRANSACTION_SETTINGS_PATH"
  local launch_path="$VSCODE_VENV_TRANSACTION_LAUNCH_PATH"

  if [[ -f "$settings_path" ]]; then
    cp -p "$settings_path" "$VSCODE_VENV_TRANSACTION_DIRECTORY/settings.applied"
    VSCODE_VENV_TRANSACTION_SETTINGS_APPLIED_EXISTS=true
  fi
  if [[ -f "$launch_path" ]]; then
    cp -p "$launch_path" "$VSCODE_VENV_TRANSACTION_DIRECTORY/launch.applied"
    VSCODE_VENV_TRANSACTION_LAUNCH_APPLIED_EXISTS=true
  fi
  VSCODE_VENV_TRANSACTION_APPLIED=true
}

restore_transaction_file() {
  local label="$1"
  local target_path="$2"
  local original_exists="$3"
  local applied_exists="$4"
  local original_path="$VSCODE_VENV_TRANSACTION_DIRECTORY/$label.original"
  local applied_path="$VSCODE_VENV_TRANSACTION_DIRECTORY/$label.applied"

  if [[ "$VSCODE_VENV_TRANSACTION_APPLIED" == true ]]; then
    if [[ "$applied_exists" == true ]]; then
      if [[ ! -f "$target_path" ]] || ! cmp -s "$target_path" "$applied_path"; then
        print -u2 "use-venv: not rolling back $target_path because it changed after the script wrote it"
        return 2
      fi
    elif [[ -e "$target_path" ]]; then
      print -u2 "use-venv: not rolling back $target_path because it was created after the script update"
      return 2
    fi
  fi

  if [[ "$original_exists" == true ]]; then
    cp -p "$original_path" "$target_path"
  else
    rm -f "$target_path"
  fi
}

rollback_file_transaction() {
  local rollback_status=0

  print -u2 "use-venv: rolling back VS Code configuration changes..."
  restore_transaction_file \
    settings \
    "$VSCODE_VENV_TRANSACTION_SETTINGS_PATH" \
    "$VSCODE_VENV_TRANSACTION_SETTINGS_ORIGINAL_EXISTS" \
    "$VSCODE_VENV_TRANSACTION_SETTINGS_APPLIED_EXISTS" || rollback_status=$?
  restore_transaction_file \
    launch \
    "$VSCODE_VENV_TRANSACTION_LAUNCH_PATH" \
    "$VSCODE_VENV_TRANSACTION_LAUNCH_ORIGINAL_EXISTS" \
    "$VSCODE_VENV_TRANSACTION_LAUNCH_APPLIED_EXISTS" || rollback_status=$?

  if (( rollback_status == 0 )); then
    print -u2 "use-venv: rollback completed."
    cleanup_file_transaction
    return 0
  fi

  print -u2 "use-venv: rollback was incomplete; backups remain at $VSCODE_VENV_TRANSACTION_DIRECTORY"
  return "$rollback_status"
}

commit_file_transaction() {
  VSCODE_VENV_TRANSACTION_ACTIVE=false
  cleanup_file_transaction
}

finish_file_transaction_on_exit() {
  local exit_status="$1"
  trap - EXIT

  if [[ "$VSCODE_VENV_TRANSACTION_ACTIVE" == true ]]; then
    rollback_file_transaction || exit_status=1
  fi
  exit "$exit_status"
}

trap 'finish_file_transaction_on_exit $?' EXIT

install_command() {
  local script_path="$VSCODE_VENV_SCRIPT_PATH"
  local install_directory="$HOME/.local/bin"
  local command_path="$install_directory/use-venv"
  local installed_marker=""
  local temporary_command_path=""

  mkdir -p "$install_directory"

  if [[ -L "$command_path" ]]; then
    if [[ "${command_path:A}" != "$script_path" ]]; then
      fail "$command_path already links to another file: ${command_path:A}"
    fi
  elif [[ -e "$command_path" ]]; then
    installed_marker="$(sed -n '2p' "$command_path" 2>/dev/null || true)"
    if [[ "$installed_marker" != "# use-venv-managed-command" ]]; then
      fail "$command_path already exists and is not managed by this script"
    fi
    if cmp -s "$script_path" "$command_path"; then
      print "Already installed: $command_path"
      return
    fi
  fi

  temporary_command_path="$(
    mktemp "$install_directory/.use-venv.XXXXXXXX"
  )" || fail "cannot create a temporary installation file"
  if ! install -m 0755 "$script_path" "$temporary_command_path"; then
    rm -f "$temporary_command_path"
    fail "cannot prepare $command_path"
  fi
  if ! mv -f "$temporary_command_path" "$command_path"; then
    rm -f "$temporary_command_path"
    fail "cannot replace $command_path"
  fi
  print "Installed standalone command: $command_path"

  case ":$PATH:" in
    *":$install_directory:"*) ;;
    *) print -u2 "Add $install_directory to PATH before using the global command." ;;
  esac
}

uninstall_command() {
  local command_path="$HOME/.local/bin/use-venv"
  local installed_marker=""

  if [[ ! -e "$command_path" && ! -L "$command_path" ]]; then
    print "Already uninstalled: $command_path"
    return
  fi

  if [[ -L "$command_path" ]]; then
    if [[ "${command_path:A}" != "$VSCODE_VENV_SCRIPT_PATH" ]]; then
      fail "$command_path links to another file and will not be removed"
    fi
  elif [[ -f "$command_path" ]]; then
    installed_marker="$(sed -n '2p' "$command_path" 2>/dev/null || true)"
    if [[ "$installed_marker" != "# use-venv-managed-command" ]]; then
      fail "$command_path is not managed by this script and will not be removed"
    fi
  else
    fail "$command_path is not a managed regular file or symbolic link"
  fi

  rm "$command_path"
  print "Uninstalled: $command_path"
}

absolute_directory() {
  local requested_directory="$1"
  [[ -d "$requested_directory" ]] || return 1
  (cd "$requested_directory" && pwd -P)
}

find_project_and_venv() {
  local requested_directory="$1"
  local search_directory

  search_directory="$(absolute_directory "$requested_directory")" || \
    fail "directory does not exist: $requested_directory"

  if [[ -x "$search_directory/bin/python" && -f "$search_directory/bin/activate" ]]; then
    VSCODE_VENV_DIRECTORY="$search_directory"
    VSCODE_VENV_PROJECT_DIRECTORY="${search_directory:h}"
    return
  fi

  while [[ "$search_directory" != "/" ]]; do
    if [[ -x "$search_directory/.venv/bin/python" ]]; then
      VSCODE_VENV_PROJECT_DIRECTORY="$search_directory"
      VSCODE_VENV_DIRECTORY="$search_directory/.venv"
      return
    fi
    search_directory="${search_directory:h}"
  done

  fail "no .venv with an executable Python was found at or above: $requested_directory"
}

find_workspace() {
  local requested_workspace="$1"
  local search_directory="$VSCODE_VENV_PROJECT_DIRECTORY"
  local git_workspace=""

  if [[ -n "$requested_workspace" ]]; then
    VSCODE_VENV_WORKSPACE_DIRECTORY="$(absolute_directory "$requested_workspace")" || \
      fail "workspace directory does not exist: $requested_workspace"
    return
  fi

  while [[ "$search_directory" != "/" ]]; do
    if [[ -f "$search_directory/.vscode/settings.json" ]]; then
      VSCODE_VENV_WORKSPACE_DIRECTORY="$search_directory"
      return
    fi
    if [[ -z "$git_workspace" && -d "$search_directory/.git" ]]; then
      git_workspace="$search_directory"
    fi
    search_directory="${search_directory:h}"
  done

  VSCODE_VENV_WORKSPACE_DIRECTORY="${git_workspace:-$VSCODE_VENV_PROJECT_DIRECTORY}"
}

update_vscode_settings() {
  local settings_directory="$VSCODE_VENV_WORKSPACE_DIRECTORY/.vscode"
  local settings_path="$settings_directory/settings.json"
  local launch_path="$settings_directory/launch.json"

  mkdir -p "$settings_directory"

  python3 - \
    "$settings_path" \
    "$VSCODE_VENV_WORKSPACE_DIRECTORY" \
    "$VSCODE_VENV_PROJECT_DIRECTORY" \
    "$VSCODE_VENV_DIRECTORY" \
    "$launch_path" <<'PYTHON'
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional


def remove_jsonc_comments(source: str) -> str:
    result: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
        elif char == "/" and next_char == "/":
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                index += 1
        elif char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(source) and source[index : index + 2] != "*/":
                if source[index] in "\r\n":
                    result.append(source[index])
                index += 1
            index += 2
        else:
            result.append(char)
            index += 1

    return "".join(result)


def parse_jsonc(source: str) -> dict[str, object]:
    if not source.strip():
        return {}
    without_comments = remove_jsonc_comments(source)
    without_trailing_commas = remove_trailing_commas(without_comments)
    parsed = json.loads(without_trailing_commas)
    if not isinstance(parsed, dict):
        raise TypeError("the top-level VS Code settings value must be an object")
    return parsed


def remove_trailing_commas(source: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False

    for index, char in enumerate(source):
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            result.append(char)
            continue

        if char == ",":
            next_index = index + 1
            while next_index < len(source) and source[next_index].isspace():
                next_index += 1
            if next_index < len(source) and source[next_index] in "}]":
                continue

        result.append(char)

    return "".join(result)


def skip_whitespace_and_comments(source: str, index: int) -> int:
    while index < len(source):
        if source[index].isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline_index = source.find("\n", index + 2)
            return (
                len(source)
                if newline_index < 0
                else skip_whitespace_and_comments(source, newline_index + 1)
            )
        if source.startswith("/*", index):
            comment_end = source.find("*/", index + 2)
            if comment_end < 0:
                raise ValueError("unterminated block comment in VS Code settings")
            index = comment_end + 2
            continue
        return index
    return index


def scan_string(source: str, index: int) -> int:
    if index >= len(source) or source[index] != '"':
        raise ValueError("expected a JSON string in VS Code settings")

    index += 1
    escaped = False
    while index < len(source):
        char = source[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return index + 1
        index += 1

    raise ValueError("unterminated JSON string in VS Code settings")


def scan_compound_value(source: str, index: int) -> int:
    closing_for = {"{": "}", "[": "]"}
    stack = [closing_for[source[index]]]
    index += 1

    while index < len(source):
        if source[index] == '"':
            index = scan_string(source, index)
            continue
        if source.startswith("//", index) or source.startswith("/*", index):
            index = skip_whitespace_and_comments(source, index)
            continue
        if source[index] in closing_for:
            stack.append(closing_for[source[index]])
        elif source[index] in "}]":
            if source[index] != stack[-1]:
                raise ValueError("mismatched JSON delimiters in VS Code settings")
            stack.pop()
            if not stack:
                return index + 1
        index += 1

    raise ValueError("unterminated JSON value in VS Code settings")


def scan_value(source: str, index: int) -> int:
    index = skip_whitespace_and_comments(source, index)
    if index >= len(source):
        raise ValueError("missing JSON value in VS Code settings")
    if source[index] == '"':
        return scan_string(source, index)
    if source[index] in "[{":
        return scan_compound_value(source, index)

    value_end = index
    while value_end < len(source):
        if source[value_end].isspace() or source[value_end] in ",}":
            break
        if source.startswith("//", value_end) or source.startswith("/*", value_end):
            break
        value_end += 1
    if value_end == index:
        raise ValueError("missing JSON value in VS Code settings")
    return value_end


def find_top_level_properties(
    source: str,
) -> tuple[int, dict[str, tuple[int, int, int]]]:
    index = skip_whitespace_and_comments(source, 0)
    if index >= len(source) or source[index] != "{":
        raise ValueError("the top-level VS Code settings value must be an object")
    opening_brace = index
    index = skip_whitespace_and_comments(source, index + 1)
    properties: dict[str, tuple[int, int, int]] = {}

    while index < len(source):
        if source[index] == "}":
            return opening_brace, properties

        key_start = index
        key_end = scan_string(source, key_start)
        key = json.loads(source[key_start:key_end])
        index = skip_whitespace_and_comments(source, key_end)
        if index >= len(source) or source[index] != ":":
            raise ValueError(f"missing colon after VS Code setting {key!r}")

        value_start = skip_whitespace_and_comments(source, index + 1)
        value_end = scan_value(source, value_start)
        properties[key] = (value_start, value_end, key_start)
        index = skip_whitespace_and_comments(source, value_end)

        if index < len(source) and source[index] == ",":
            index = skip_whitespace_and_comments(source, index + 1)
            continue
        if index < len(source) and source[index] == "}":
            return opening_brace, properties
        raise ValueError(f"missing comma after VS Code setting {key!r}")

    raise ValueError("unterminated top-level VS Code settings object")


def property_indent(source: str, key_start: int) -> str:
    line_start = source.rfind("\n", 0, key_start) + 1
    indent = source[line_start:key_start]
    return indent if not indent.strip() else "  "


def format_json_value(value: object, indent: str) -> str:
    serialized = json.dumps(value, ensure_ascii=False, indent=2)
    return serialized.replace("\n", "\n" + indent)


def update_jsonc(
    source: str,
    updates: dict[str, object],
    removals: tuple[str, ...] = (),
) -> str:
    if not source.strip():
        return json.dumps(updates, ensure_ascii=False, indent=2) + "\n"

    opening_brace, properties = find_top_level_properties(source)
    replacements: list[tuple[int, int, str]] = []
    missing_updates: list[tuple[str, object]] = []

    current_settings = parse_jsonc(source)
    for key in removals:
        if key not in properties:
            continue
        _, value_end, key_start = properties[key]
        following_index = skip_whitespace_and_comments(source, value_end)
        if following_index < len(source) and source[following_index] == ",":
            replacements.append((key_start, following_index + 1, ""))
            continue

        previous_properties = [
            property_data
            for property_name, property_data in properties.items()
            if property_name not in removals and property_data[2] < key_start
        ]
        if previous_properties:
            previous_value_end = max(previous_properties, key=lambda item: item[2])[1]
            previous_comma = skip_whitespace_and_comments(source, previous_value_end)
            if previous_comma < len(source) and source[previous_comma] == ",":
                replacements.append((previous_comma, value_end, ""))
                continue
        replacements.append((key_start, value_end, ""))

    for key, value in updates.items():
        if key not in properties:
            missing_updates.append((key, value))
            continue
        if current_settings.get(key) == value:
            continue
        value_start, value_end, key_start = properties[key]
        indent = property_indent(source, key_start)
        replacements.append((value_start, value_end, format_json_value(value, indent)))

    updated_source = source
    for value_start, value_end, replacement in sorted(replacements, reverse=True):
        updated_source = (
            updated_source[:value_start] + replacement + updated_source[value_end:]
        )

    if missing_updates:
        newline = "\r\n" if "\r\n" in source else "\n"
        if properties:
            first_key_start = min(value[2] for value in properties.values())
            indent = property_indent(source, first_key_start)
        else:
            indent = "  "
        entries = []
        for key, value in missing_updates:
            formatted_value = format_json_value(value, indent)
            entries.append(
                f"{indent}{json.dumps(key, ensure_ascii=False)}: {formatted_value}"
            )
        insertion = newline + ("," + newline).join(entries)
        insertion += "," if properties else newline
        updated_source = (
            updated_source[: opening_brace + 1]
            + insertion
            + updated_source[opening_brace + 1 :]
        )

    verified_settings = parse_jsonc(updated_source)
    for key in removals:
        if key in verified_settings:
            raise ValueError(f"failed to remove VS Code setting {key!r}")
    for key, value in updates.items():
        if verified_settings.get(key) != value:
            raise ValueError(f"failed to update VS Code setting {key!r}")
    return updated_source


def workspace_value(workspace: Path, target: Path) -> str:
    relative = os.path.relpath(target, workspace)
    if relative == ".":
        return "${workspaceFolder}"
    return "${workspaceFolder}/" + Path(relative).as_posix()


def file_matches(path: Path, pattern: str) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return re.search(pattern, source, flags=re.MULTILINE) is not None


def detect_test_framework(project: Path) -> Optional[str]:
    if (project / "pytest.ini").is_file() or (project / "conftest.py").is_file():
        return "pytest"

    pytest_config_patterns = {
        "pyproject.toml": r"^\s*\[tool\.pytest(?:\.|\])",
        "setup.cfg": r"^\s*\[tool:pytest\]",
        "tox.ini": r"^\s*\[pytest\]",
    }
    for filename, pattern in pytest_config_patterns.items():
        if file_matches(project / filename, pattern):
            return "pytest"

    tests_directory = project / "tests"
    if not tests_directory.is_dir():
        return "none"

    uses_pytest = False
    uses_unittest = False
    uses_plain_test_functions = False
    test_files_found = False
    try:
        test_paths = list(tests_directory.rglob("test*.py"))
    except OSError:
        return None

    for test_path in test_paths:
        test_files_found = True
        uses_pytest = uses_pytest or file_matches(
            test_path, r"^\s*(?:import\s+pytest\b|from\s+pytest\b)"
        )
        uses_unittest = uses_unittest or file_matches(
            test_path, r"^\s*(?:import\s+unittest\b|from\s+unittest\b)"
        )
        uses_plain_test_functions = uses_plain_test_functions or file_matches(
            test_path, r"^(?:async\s+)?def\s+test_"
        )

    if not test_files_found:
        return "none"
    if uses_pytest or (uses_unittest and uses_plain_test_functions):
        return "pytest"
    if uses_unittest:
        return "unittest"
    if uses_plain_test_functions:
        return "pytest"
    return None


settings_path = Path(sys.argv[1])
workspace = Path(sys.argv[2]).resolve()
project = Path(sys.argv[3]).resolve()
venv = Path(sys.argv[4]).resolve()
launch_path = Path(sys.argv[5])

try:
    existing_source = (
        settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
    )
    settings = parse_jsonc(existing_source)
except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
    raise SystemExit(f"use-venv: cannot read {settings_path}: {error}") from error

project_setting = workspace_value(workspace, project)
venv_setting = workspace_value(workspace, venv)
interpreter_setting = f"{venv_setting}/bin/python"
source_directory = project / "src" if (project / "src").is_dir() else project
source_setting = workspace_value(workspace, source_directory)

relative_venv = os.path.relpath(venv, workspace)
relative_venv_setting = "./" + Path(relative_venv).as_posix()
relative_project = Path(os.path.relpath(project, workspace)).as_posix()
python_projects = [
    {
        "path": relative_project,
        "envManager": "ms-python.python:venv",
        "packageManager": "ms-python.python:pip",
    }
]
test_framework = detect_test_framework(project)

updates = {
    "python-envs.workspaceSearchPaths": [relative_venv_setting],
    "python-envs.pythonProjects": python_projects,
    "python.useEnvironmentsExtension": True,
    "python.terminal.activateEnvironment": True,
    "terminal.integrated.cwd": project_setting,
    "python.analysis.extraPaths": [source_setting],
    "pylint.interpreter": [interpreter_setting],
    "autopep8.interpreter": [interpreter_setting],
    "isort.interpreter": [interpreter_setting],
    "python.testing.cwd": project_setting,
    "pylint.cwd": project_setting,
}

if test_framework == "pytest":
    updates.update(
        {
            "python.testing.pytestEnabled": True,
            "python.testing.unittestEnabled": False,
            "python.testing.pytestArgs": [],
        }
    )
elif test_framework == "unittest":
    updates.update(
        {
            "python.testing.pytestEnabled": False,
            "python.testing.unittestEnabled": True,
            "python.testing.unittestArgs": [
                "-v",
                "-s",
                "tests",
                "-p",
                "test_*.py",
            ],
        }
    )
elif test_framework == "none":
    updates.update(
        {
            "python.testing.pytestEnabled": False,
            "python.testing.unittestEnabled": False,
        }
    )

try:
    updated_source = update_jsonc(
        existing_source,
        updates,
        removals=("python.defaultInterpreterPath",),
    )
    if updated_source != existing_source:
        settings_path.write_text(updated_source, encoding="utf-8")
except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
    raise SystemExit(f"use-venv: cannot update {settings_path}: {error}") from error


def update_launch_jsonc(source: str) -> str:
    launch = parse_jsonc(source)
    configurations = launch.get("configurations")
    if not isinstance(configurations, list):
        return source

    _, top_level_properties = find_top_level_properties(source)
    configurations_property = top_level_properties.get("configurations")
    if configurations_property is None:
        return source
    configurations_start = configurations_property[0]
    if source[configurations_start] != "[":
        return source

    element_spans: list[tuple[int, int]] = []
    index = skip_whitespace_and_comments(source, configurations_start + 1)
    while index < len(source) and source[index] != "]":
        element_end = scan_value(source, index)
        element_spans.append((index, element_end))
        index = skip_whitespace_and_comments(source, element_end)
        if index < len(source) and source[index] == ",":
            index = skip_whitespace_and_comments(source, index + 1)
        elif index >= len(source) or source[index] != "]":
            raise ValueError("missing comma in VS Code launch configurations")

    replacements: list[tuple[int, int, str]] = []
    if len(configurations) != len(element_spans):
        raise ValueError("cannot match VS Code launch configurations to their source")

    for configuration, (start, end) in zip(configurations, element_spans):
        if not isinstance(configuration, dict) or configuration.get("type") not in {
            "debugpy",
            "python",
        }:
            continue

        configuration_source = source[start:end]
        _, configuration_properties = find_top_level_properties(configuration_source)
        env_property = configuration_properties.get("env")
        if env_property is not None and isinstance(configuration.get("env"), dict):
            env_start, env_end, _ = env_property
            env_source = configuration_source[env_start:env_end]
            env_updates = {}
            if "PYTHONPATH" in configuration["env"]:
                env_updates["PYTHONPATH"] = source_setting
            if "PROJECT_ROOT_PATH" in configuration["env"]:
                env_updates["PROJECT_ROOT_PATH"] = project_setting
            if env_updates:
                updated_env_source = update_jsonc(env_source, env_updates)
                configuration_source = (
                    configuration_source[:env_start]
                    + updated_env_source
                    + configuration_source[env_end:]
                )

        configuration_source = update_jsonc(
            configuration_source,
            {
                "cwd": project_setting,
                "python": interpreter_setting,
            },
        )
        replacements.append((start, end, configuration_source))

    updated_source = source
    for start, end, replacement in reversed(replacements):
        updated_source = updated_source[:start] + replacement + updated_source[end:]

    verified_launch = parse_jsonc(updated_source)
    for configuration in verified_launch.get("configurations", []):
        if not isinstance(configuration, dict) or configuration.get("type") not in {
            "debugpy",
            "python",
        }:
            continue
        if configuration.get("cwd") != project_setting:
            raise ValueError("failed to update a Python launch working directory")
        if configuration.get("python") != interpreter_setting:
            raise ValueError("failed to update a Python launch interpreter")
    return updated_source


if launch_path.exists():
    try:
        existing_launch_source = launch_path.read_text(encoding="utf-8")
        updated_launch_source = update_launch_jsonc(existing_launch_source)
        if updated_launch_source != existing_launch_source:
            launch_path.write_text(updated_launch_source, encoding="utf-8")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"use-venv: cannot update {launch_path}: {error}") from error
PYTHON

  print "Updated:     $settings_path"
  [[ ! -f "$launch_path" ]] || print "Updated:     $launch_path"
  print "Workspace:   $VSCODE_VENV_WORKSPACE_DIRECTORY"
  print "Project:     $VSCODE_VENV_PROJECT_DIRECTORY"
  print "Interpreter: $VSCODE_VENV_DIRECTORY/bin/python"
  "$VSCODE_VENV_DIRECTORY/bin/python" --version
}

reload_vscode() {
  [[ "$(uname -s)" == "Darwin" ]] || \
    fail "automatic VS Code reload is currently supported only on macOS"
  command -v osascript >/dev/null || fail "osascript is required to reload VS Code"

  local -a reload_commands=(
    "Developer: Reload Window"
    "开发人员: 重新加载窗口"
  )

  run_vscode_reload_automation() {
    osascript - "${reload_commands[@]}" <<'APPLESCRIPT'
on run argv
    set previousClipboard to the clipboard
    try
        tell application "Visual Studio Code" to activate
        delay 0.3

        tell application "System Events"
            tell process "Code"
                -- Locate the menu item by its Cmd-Shift-P shortcut attributes
                -- so this does not depend on the localized menu label.
                set commandPaletteItem to missing value
                repeat with candidateItem in menu items of menu "View" of menu bar 1
                    try
                        if (value of attribute "AXMenuItemCmdChar" of candidateItem is "P") and (value of attribute "AXMenuItemCmdModifiers" of candidateItem is 1) then
                            set commandPaletteItem to candidateItem
                            exit repeat
                        end if
                    end try
                end repeat
                if commandPaletteItem is missing value then error "Cannot find the VS Code Command Palette menu item"

                click commandPaletteItem
                delay 0.5

                -- Electron focuses the first result's static text rather than
                -- the search field. Confirm that it belongs to the result list.
                set currentElement to value of attribute "AXFocusedUIElement"
                set commandListFound to false
                repeat 8 times
                    try
                        if value of attribute "AXRole" of currentElement is "AXList" then
                            set commandListFound to true
                            exit repeat
                        end if
                        set currentElement to value of attribute "AXParent" of currentElement
                    on error
                        exit repeat
                    end try
                end repeat
                if not commandListFound then error "VS Code Command Palette result list did not receive focus"
            end tell

            set reloadCommandFound to false
            repeat with commandCandidate in argv
                set commandText to commandCandidate as text
                set the clipboard to commandText
                keystroke "v" using {command down}
                delay 0.5

                tell process "Code"
                    set focusedElement to value of attribute "AXFocusedUIElement"
                    try
                        set focusedValue to value of attribute "AXValue" of focusedElement as text
                    on error
                        set focusedValue to ""
                    end try
                end tell

                if focusedValue contains commandText then
                    set reloadCommandFound to true
                    exit repeat
                end if

                -- Clear the unmatched query before trying the next locale.
                keystroke "a" using {command down}
                key code 51
                delay 0.2
            end repeat

            if not reloadCommandFound then error "VS Code did not select a supported Reload Window command"

            set the clipboard to previousClipboard
            key code 36
        end tell
    on error errorMessage number errorNumber
        try
            set the clipboard to previousClipboard
            tell application "System Events" to key code 53
        end try
        error errorMessage number errorNumber
    end try
end run
APPLESCRIPT
  }

  print "Reloading VS Code..."
  local automation_error=""
  if automation_error="$(run_vscode_reload_automation 2>&1)"; then
    return
  fi

  if [[ "$automation_error" != *"not allowed assistive access"* && \
        "$automation_error" != *"不允许辅助访问"* && \
        "$automation_error" != *"(-25211)"* ]]; then
    fail "VS Code reload was not performed: $automation_error"
  fi

  if [[ ! -t 0 ]]; then
    fail "macOS denied UI control; grant Accessibility access to the terminal application and run use-venv again"
  fi

  print -u2 "macOS denied UI control. Opening Accessibility settings..."
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
  print -u2 "Enable Accessibility access for Visual Studio Code, then return here."
  read "?Press Enter to retry the VS Code reload: "

  run_vscode_reload_automation || \
    fail "VS Code reload was still denied; verify Accessibility access and run use-venv again"
}

requested_path="$PWD"
requested_workspace=""
should_reload=false

while (( $# > 0 )); do
  case "$1" in
    -h|--help)
      print_usage
      exit 0
      ;;
    --install)
      install_command
      exit 0
      ;;
    --uninstall)
      uninstall_command
      exit 0
      ;;
    --workspace)
      (( $# >= 2 )) || fail "--workspace requires a directory"
      requested_workspace="$2"
      shift 2
      ;;
    --no-reload)
      should_reload=false
      shift
      ;;
    --reload)
      should_reload=true
      shift
      ;;
    --*)
      fail "unknown option: $1"
      ;;
    *)
      requested_path="$1"
      shift
      ;;
  esac
done

find_project_and_venv "$requested_path"
find_workspace "$requested_workspace"

case "$VSCODE_VENV_PROJECT_DIRECTORY/" in
  "$VSCODE_VENV_WORKSPACE_DIRECTORY/"*) ;;
  *) fail "project must be inside the selected VS Code workspace" ;;
esac

begin_file_transaction
update_vscode_settings
capture_applied_file_transaction

if [[ "$should_reload" == true ]]; then
  reload_vscode
else
  print "VS Code reload is unnecessary; the Python Environments extension observes these settings live."
fi

commit_file_transaction
