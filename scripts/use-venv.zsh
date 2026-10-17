#!/bin/zsh
# use-venv-managed-command

set -eu
typeset -gr USE_VENV_SCRIPT_PATH="${0:A}"

# Keep existing callers' environment overrides; explicitly set new names win.
for use_venv_suffix in CURSOR_EXTENSION_DIRECTORY CURSOR_LOG_DIRECTORY EDITOR_STORAGE_DIRECTORY; do
  use_venv_new_name="USE_VENV_$use_venv_suffix"
  use_venv_old_name="VSCODE_VENV_$use_venv_suffix"
  if ((!${+parameters[$use_venv_new_name]} && ${+parameters[$use_venv_old_name]})); then
    export "$use_venv_new_name=${(P)use_venv_old_name}"
  fi
done
unset use_venv_suffix use_venv_new_name use_venv_old_name

export USE_VENV_STATE_DIRECTORY="${USE_VENV_STATE_DIRECTORY:-$HOME/Library/Application Support/use-venv/transactions}"

runtime_state() {
  python3 - "$1" "$USE_VENV_STATE_DIRECTORY" "${2:-}" <<'RUNTIME_STATE_PYTHON'
import json
import shutil
import sys
from pathlib import Path


def prepare_root(path):
    root = Path(path).expanduser()
    if not root.is_absolute() or root.is_symlink():
        raise RuntimeError(
            "Runtime state directory must be an absolute non-symlink path"
        )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root.resolve()


def migrate_tree(source, destination):
    if source.is_symlink() or any(path.is_symlink() for path in source.rglob("*")):
        raise RuntimeError(
            f"Legacy backup contains symbolic links; retained at {source}"
        )
    if destination.exists():
        raise RuntimeError(
            f"Backup destination already exists; preserving both {source} and {destination}"
        )
    shutil.move(str(source), str(destination))
    print(f"Migrated:    {source} -> {destination}")


def migrate_legacy(workspace, root):
    legacy = workspace / ".agent-tmp"
    if legacy.is_symlink():
        raise RuntimeError("Legacy transaction directory must not be a symlink")
    if not legacy.is_dir():
        return
    api = legacy / "cursor-api-repair"
    if api.exists():
        if not all(
            (api / name).is_file()
            for name in ("state.json", "original.json", "applied.json")
        ):
            raise RuntimeError(f"Incomplete legacy API backup; retained at {api}")
        json.loads((api / "state.json").read_text())
        migrate_tree(api, root / api.name)
    for package in sorted(legacy.glob("cursor-envs-transaction.*")):
        if (
            not (package / "backup.json").exists()
            and not (package / "original.vsix").exists()
        ):
            continue
        if (
            not (package / "backup.json").is_file()
            or not (package / "original.vsix").is_file()
        ):
            raise RuntimeError(
                f"Incomplete legacy extension backup; retained at {package}"
            )
        json.loads((package / "backup.json").read_text())
        migrate_tree(package, root / package.name)


if __name__ == "__main__":
    try:
        root = prepare_root(sys.argv[2])
        if sys.argv[1] == "prepare":
            print(root)
        elif sys.argv[1] == "migrate":
            migrate_legacy(Path(sys.argv[3]), root)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"use-venv: {error}", file=sys.stderr)
        sys.exit(1)
RUNTIME_STATE_PYTHON
}

prepare_runtime_state() {
  USE_VENV_STATE_DIRECTORY="$(runtime_state prepare)" || fail "cannot prepare runtime state directory"
  export USE_VENV_STATE_DIRECTORY
}

print_usage() {
  cat <<'EOF'
Usage: use-venv [PROJECT_OR_VENV_PATH] [--workspace WORKSPACE_PATH]
                [--editor vscode|cursor|both] [--repair-cursor-envs]
                [--repair-cursor-api] [--reload]
       use-venv PROJECT --editor cursor --rollback-cursor-api
       use-venv --install
       use-venv --uninstall

Switch a VS Code or Cursor workspace to an existing Python .venv, update workspace and
debug settings, let Python Environments discover it, and realign the
extension's selected environment when it points elsewhere (macOS only).

Arguments:
  PROJECT_OR_VENV_PATH  Project directory, .venv directory, or a directory
                        inside the project. Defaults to the current directory.
  --workspace PATH      Workspace root. By default, search upward for
                        .vscode/settings.json and then for .git.
  --editor EDITOR       Select vscode (default), cursor, or both. Editors that
                        are not running are reported as pending, not launched.
  --reinstall-cursor-helper
                        Force reinstall the bundled helper and reload Cursor.
                        Requires a running Cursor workspace and cursor/both.
  --repair-cursor-envs  Allow repairing Cursor's Python Environments package
                        from a matching platform VSIX and reloading its
                        window after replacement. Requires cursor/both.
  --repair-cursor-api   Repair a missing terminalDataWriteEvent grant, restart
                        Cursor, and verify activation in a new terminal. Run
                        outside Cursor. May be combined with package repair.
  --rollback-cursor-api Restore an unfinished API repair from its backup and
                        restart Cursor. Requires --editor cursor.
  --install             Install or update a standalone ~/.local/bin/use-venv.
  --uninstall           Remove the managed ~/.local/bin/use-venv installation.
  --reload              Also attempt a guarded target-editor reload on macOS.
                        A reload failure rolls back the file changes.
  --no-reload           Compatibility alias for the default no-reload behavior.
  -h, --help            Show this help.
EOF
}

configure_editor() {
  case "$1" in
    vscode)
      USE_VENV_EDITOR_LABEL="VS Code"
      USE_VENV_EDITOR_APPLICATION="Visual Studio Code"
      USE_VENV_EDITOR_PROCESS="Code"
      USE_VENV_EDITOR_STORAGE_NAME="Code"
      ;;
    cursor)
      USE_VENV_EDITOR_LABEL="Cursor"
      USE_VENV_EDITOR_APPLICATION="Cursor"
      USE_VENV_EDITOR_PROCESS="Cursor"
      USE_VENV_EDITOR_STORAGE_NAME="Cursor"
      ;;
    *) fail "unknown editor: $1" ;;
  esac
}

typeset -g USE_VENV_EDITOR_LABEL="VS Code"
typeset -g USE_VENV_EDITOR_APPLICATION="Visual Studio Code"
typeset -g USE_VENV_EDITOR_PROCESS="Code"
typeset -g USE_VENV_EDITOR_STORAGE_NAME="Code"
typeset -g USE_VENV_SELECTION_PENDING=false
typeset -g USE_VENV_CURSOR_REPAIR_DIRECTORY=""
typeset -g USE_VENV_CURSOR_REPAIR_COMMITTED=false
typeset -g USE_VENV_CURSOR_RELOADED=false
typeset -g USE_VENV_CURSOR_API_ACTIVE=false
typeset -g USE_VENV_CURSOR_API_REQUIRED=false

fail() {
  print -u2 "use-venv: $1"
  exit 1
}

typeset -g USE_VENV_TRANSACTION_ACTIVE=false
typeset -g USE_VENV_TRANSACTION_APPLIED=false
typeset -g USE_VENV_TRANSACTION_DIRECTORY=""
typeset -g USE_VENV_TRANSACTION_SETTINGS_PATH=""
typeset -g USE_VENV_TRANSACTION_LAUNCH_PATH=""
typeset -g USE_VENV_TRANSACTION_SETTINGS_ORIGINAL_EXISTS=false
typeset -g USE_VENV_TRANSACTION_LAUNCH_ORIGINAL_EXISTS=false
typeset -g USE_VENV_TRANSACTION_SETTINGS_APPLIED_EXISTS=false
typeset -g USE_VENV_TRANSACTION_LAUNCH_APPLIED_EXISTS=false

cleanup_file_transaction() {
  local transaction_directory="$USE_VENV_TRANSACTION_DIRECTORY"
  [[ -n "$transaction_directory" ]] || return 0

  rm -f \
    "$transaction_directory/settings.original" \
    "$transaction_directory/settings.applied" \
    "$transaction_directory/launch.original" \
    "$transaction_directory/launch.applied" \
    "$transaction_directory/state.json"
  rmdir "$transaction_directory"
  USE_VENV_TRANSACTION_DIRECTORY=""
}

begin_file_transaction() {
  prepare_runtime_state
  local temporary_root="$USE_VENV_STATE_DIRECTORY"
  local settings_path="$USE_VENV_WORKSPACE_DIRECTORY/.vscode/settings.json"
  local launch_path="$USE_VENV_WORKSPACE_DIRECTORY/.vscode/launch.json"

  USE_VENV_TRANSACTION_DIRECTORY="$(
    mktemp -d "$temporary_root/workspace-config.XXXXXXXX"
  )" || fail "cannot create a transaction directory"
  USE_VENV_TRANSACTION_SETTINGS_PATH="$settings_path"
  USE_VENV_TRANSACTION_LAUNCH_PATH="$launch_path"
  python3 - "$USE_VENV_TRANSACTION_DIRECTORY/state.json" "$USE_VENV_WORKSPACE_DIRECTORY" "$settings_path" "$launch_path" <<'CONFIG_TRANSACTION_PYTHON'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {"workspace": sys.argv[2], "settings": sys.argv[3], "launch": sys.argv[4]}
    )
)
CONFIG_TRANSACTION_PYTHON

  if [[ -f "$settings_path" ]]; then
    if ! cp -p \
      "$settings_path" \
      "$USE_VENV_TRANSACTION_DIRECTORY/settings.original"; then
      cleanup_file_transaction
      fail "cannot back up $settings_path"
    fi
    USE_VENV_TRANSACTION_SETTINGS_ORIGINAL_EXISTS=true
  fi
  if [[ -f "$launch_path" ]]; then
    if ! cp -p \
      "$launch_path" \
      "$USE_VENV_TRANSACTION_DIRECTORY/launch.original"; then
      cleanup_file_transaction
      fail "cannot back up $launch_path"
    fi
    USE_VENV_TRANSACTION_LAUNCH_ORIGINAL_EXISTS=true
  fi

  USE_VENV_TRANSACTION_ACTIVE=true
}

capture_applied_file_transaction() {
  local settings_path="$USE_VENV_TRANSACTION_SETTINGS_PATH"
  local launch_path="$USE_VENV_TRANSACTION_LAUNCH_PATH"

  if [[ -f "$settings_path" ]]; then
    cp -p "$settings_path" "$USE_VENV_TRANSACTION_DIRECTORY/settings.applied"
    USE_VENV_TRANSACTION_SETTINGS_APPLIED_EXISTS=true
  fi
  if [[ -f "$launch_path" ]]; then
    cp -p "$launch_path" "$USE_VENV_TRANSACTION_DIRECTORY/launch.applied"
    USE_VENV_TRANSACTION_LAUNCH_APPLIED_EXISTS=true
  fi
  USE_VENV_TRANSACTION_APPLIED=true
}

restore_transaction_file() {
  local label="$1"
  local target_path="$2"
  local original_exists="$3"
  local applied_exists="$4"
  local original_path="$USE_VENV_TRANSACTION_DIRECTORY/$label.original"
  local applied_path="$USE_VENV_TRANSACTION_DIRECTORY/$label.applied"

  if [[ "$USE_VENV_TRANSACTION_APPLIED" == true ]]; then
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

  print -u2 "use-venv: rolling back shared editor configuration changes..."
  restore_transaction_file \
    settings \
    "$USE_VENV_TRANSACTION_SETTINGS_PATH" \
    "$USE_VENV_TRANSACTION_SETTINGS_ORIGINAL_EXISTS" \
    "$USE_VENV_TRANSACTION_SETTINGS_APPLIED_EXISTS" || rollback_status=$?
  restore_transaction_file \
    launch \
    "$USE_VENV_TRANSACTION_LAUNCH_PATH" \
    "$USE_VENV_TRANSACTION_LAUNCH_ORIGINAL_EXISTS" \
    "$USE_VENV_TRANSACTION_LAUNCH_APPLIED_EXISTS" || rollback_status=$?

  if ((rollback_status == 0)); then
    print -u2 "use-venv: rollback completed."
    cleanup_file_transaction
    return 0
  fi

  print -u2 "use-venv: rollback was incomplete; backups remain at $USE_VENV_TRANSACTION_DIRECTORY"
  return "$rollback_status"
}

commit_file_transaction() {
  USE_VENV_TRANSACTION_ACTIVE=false
  cleanup_file_transaction
}

finish_file_transaction_on_exit() {
  local exit_status="$1"
  trap - EXIT

  if [[ "$USE_VENV_TRANSACTION_ACTIVE" == true ]]; then
    rollback_file_transaction || exit_status=1
  fi
  if ! finish_cursor_repair_transaction; then
    exit_status=1
  fi
  if [[ "$USE_VENV_CURSOR_API_ACTIVE" == true && -d "$USE_VENV_STATE_DIRECTORY/cursor-api-repair" ]]; then
    if ! run_cursor_automation rollback-cursor-api; then
      print -u2 "use-venv: Cursor API rollback failed; backup remains in $USE_VENV_STATE_DIRECTORY/cursor-api-repair"
      exit_status=1
    fi
  fi
  exit "$exit_status"
}

trap 'finish_file_transaction_on_exit $?' EXIT

ensure_cursor_environment_tools() {
  [[ "$(uname -s)" == "Darwin" ]] || {
    [[ "$repair_cursor_envs" == false ]] || fail "Cursor environment repair requires macOS"
    return 0
  }
  local extension_directory="${USE_VENV_CURSOR_EXTENSION_DIRECTORY:-$HOME/.cursor/extensions}"
  python3 - "$extension_directory" "$repair_cursor_envs" \
    "$USE_VENV_WORKSPACE_DIRECTORY" "$USE_VENV_PROJECT_DIRECTORY" \
    "$USE_VENV_DIRECTORY/bin/python" "${1:-ensure}" \
    "$USE_VENV_CURSOR_REPAIR_DIRECTORY" <<'CURSOR_PYTHON'
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ENVS_ID = "ms-python.vscode-python-envs"
PYTHON_ID = "ms-python.python"
PET_RELATIVE_PATH = Path("python-env-tools/bin/pet")


def run_command(command, timeout=30):
    """Bound the command and clean up only its own process group."""
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            if process.returncode:
                raise RuntimeError(
                    f"{Path(command[0]).name} failed: {stderr.strip() or stdout.strip()}"
                )
            return stdout
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            else:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                deadline = time.monotonic() + 1
                while True:
                    try:
                        os.killpg(process.pid, 0)
                    except ProcessLookupError:
                        break
                    if time.monotonic() >= deadline:
                        os.killpg(process.pid, signal.SIGKILL)
                        break
                    time.sleep(0.05)


def installed_extensions(root):
    records = json.loads((root / "extensions.json").read_text())
    extensions = {}
    for record in records:
        identifier = record.get("identifier", {}).get("id", "").lower()
        location = record.get("relativeLocation")
        if location:
            extensions[identifier] = root / location
    return extensions


def selected_pet(extensions):
    # Match the extension's own lookup order. An existing but broken first
    # candidate must be repaired rather than masked by the fallback.
    for identifier in (ENVS_ID, PYTHON_ID):
        directory = extensions.get(identifier)
        if directory is not None:
            executable = directory / PET_RELATIVE_PATH
            if executable.is_file():
                return executable
    raise RuntimeError("Python Environments and Python contain no pet executable")


def check_pet(extensions):
    executable = selected_pet(extensions)
    run_command([str(executable), "--version"], timeout=10)
    return executable


def verify_discovery(executable, project, interpreter):
    output = run_command(
        [
            str(executable),
            "find",
            "--workspace",
            "--json",
            str(project),
            "--environment-directories",
            str(interpreter.parent.parent),
        ]
    )
    environments = json.loads(output).get("environments", [])
    if not any(
        environment.get("executable") == str(interpreter)
        and not environment.get("error")
        for environment in environments
    ):
        raise RuntimeError(
            f"pet did not discover the target interpreter: {interpreter}"
        )


def validate_vsix(path, version, target):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("extension/package.json"))
        identity = ET.fromstring(archive.read("extension.vsixmanifest"))
        identities = identity.findall(".//{*}Identity")
        if (
            manifest.get("publisher") != "ms-python"
            or manifest.get("name") != "vscode-python-envs"
            or manifest.get("version") != version
            or len(identities) != 1
            or identities[0].get("TargetPlatform") != target
        ):
            raise RuntimeError(
                "VSIX publisher, extension, version, or platform does not match"
            )
        if archive.getinfo("extension/" + PET_RELATIVE_PATH.as_posix()).file_size == 0:
            raise RuntimeError("VSIX contains an empty pet executable")


def cached_vsix_candidates(version, target):
    for editor in ("Cursor", "Code"):
        yield (
            Path.home()
            / "Library/Application Support"
            / editor
            / "CachedExtensionVSIXs"
            / f"{ENVS_ID}-{version}-{target}"
        )


def download_vsix(destination, version, target):
    url = (
        "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
        f"ms-python/vsextensions/vscode-python-envs/{version}/vspackage"
        f"?targetPlatform={target}"
    )
    print(f"Downloading: {url}", flush=True)
    with (
        urllib.request.urlopen(url, timeout=30) as response,
        destination.open("wb") as output,
    ):
        shutil.copyfileobj(response, output)


def cursor_cli():
    for root in (Path("/Applications"), Path.home() / "Applications"):
        executable = root / "Cursor.app/Contents/Resources/app/bin/cursor"
        if executable.is_file():
            return executable
    raise RuntimeError(
        "Cannot locate the Cursor CLI in /Applications or ~/Applications"
    )


def backup_package(directory, transaction, version, target, workspace=None):
    """Keep a reinstallable copy until the entire switch has succeeded."""
    manifest = json.loads((directory / "package.json").read_text())
    original_target = manifest.get("__metadata", {}).get("targetPlatform", "universal")
    with zipfile.ZipFile(
        transaction / "original.vsix", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        archive.write(directory / ".vsixmanifest", "extension.vsixmanifest")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise RuntimeError(
                    "Cannot back up an extension containing symbolic links"
                )
            if path.is_file():
                archive.write(
                    path, "extension/" + path.relative_to(directory).as_posix()
                )
    state = {
        "version": version,
        "original_target": original_target,
        "repair_target": target,
        "entry_sha256": hashlib.sha256(
            (directory / "dist/extension.js").read_bytes()
        ).hexdigest(),
        "had_pet": (directory / PET_RELATIVE_PATH).is_file(),
    }
    if workspace is not None:
        state["workspace"] = str(workspace)
    (transaction / "backup.json").write_text(json.dumps(state))


def restore_package(root, transaction):
    state = json.loads((transaction / "backup.json").read_text())
    current = installed_extensions(root).get(ENVS_ID)
    if current is not None:
        manifest = json.loads((current / "package.json").read_text())
        target = manifest.get("__metadata", {}).get("targetPlatform", "universal")
        if manifest.get("version") != state["version"] or target not in (
            state["original_target"],
            state["repair_target"],
        ):
            raise RuntimeError(
                "Cursor extension changed concurrently; keeping the backup for manual recovery"
            )
    run_command(
        [
            str(cursor_cli()),
            "--install-extension",
            str(transaction / "original.vsix"),
            "--force",
            "--do-not-include-pack-dependencies",
        ],
        timeout=60,
    )
    restored = installed_extensions(root)[ENVS_ID]
    manifest = json.loads((restored / "package.json").read_text())
    if (
        manifest.get("version") != state["version"]
        or manifest.get("__metadata", {}).get("targetPlatform", "universal")
        != state["original_target"]
        or hashlib.sha256((restored / "dist/extension.js").read_bytes()).hexdigest()
        != state["entry_sha256"]
        or (restored / PET_RELATIVE_PATH).is_file() != state["had_pet"]
    ):
        raise RuntimeError("Cannot verify restoration of the original Cursor extension")
    print("Restored:    original Cursor Python Environments package", flush=True)


def repair_package(root, workspace, extensions, transaction=None):
    directory = extensions.get(ENVS_ID)
    if directory is None:
        raise RuntimeError(
            "Python Environments is not installed; install it in Cursor first"
        )
    manifest = json.loads((directory / "package.json").read_text())
    version = manifest.get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise RuntimeError("Cannot determine the installed Python Environments version")
    target = {"arm64": "darwin-arm64", "x86_64": "darwin-x64"}.get(platform.machine())
    if target is None:
        raise RuntimeError(
            "Unsupported macOS architecture for Cursor environment repair"
        )
    cli = cursor_cli()
    if transaction is None:
        raise RuntimeError("Package repair requires a rollback transaction directory")
    temporary_root = transaction.parent
    if temporary_root.is_symlink() or transaction.is_symlink():
        raise RuntimeError("The repair temporary directory must not be a symlink")
    with tempfile.TemporaryDirectory(
        prefix="cursor-envs-repair-", dir=temporary_root
    ) as task:
        package = Path(task) / "python-environments.vsix"
        for candidate in cached_vsix_candidates(version, target):
            if not candidate.is_file():
                continue
            try:
                validate_vsix(candidate, version, target)
            except (
                RuntimeError,
                ValueError,
                KeyError,
                zipfile.BadZipFile,
                ET.ParseError,
            ):
                continue
            shutil.copyfile(candidate, package)
            print(f"Using verified cache: {candidate}", flush=True)
            break
        else:
            download_vsix(package, version, target)
        validate_vsix(package, version, target)
        if transaction is None:
            raise RuntimeError(
                "Package repair requires a rollback transaction directory"
            )
        backup_package(directory, transaction, version, target, workspace)
        print(f"Repairing: Cursor {ENVS_ID} {version} ({target})", flush=True)
        run_command(
            [
                str(cli),
                "--install-extension",
                str(package),
                "--force",
                "--do-not-include-pack-dependencies",
            ],
            timeout=60,
        )
    return installed_extensions(root)


def ensure_tools(root, workspace, project, interpreter, repair=False, transaction=None):
    extensions = installed_extensions(root)
    try:
        executable = check_pet(extensions)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        if not repair:
            raise RuntimeError(
                f"Cursor environment discovery is unavailable: {error}"
            ) from error
        extensions = repair_package(root, workspace, extensions, transaction)
        executable = check_pet(extensions)
    verify_discovery(executable, project, interpreter)
    print(f"Checked:     Cursor pet discovered {interpreter}", flush=True)


if __name__ == "__main__":
    try:
        transaction = Path(sys.argv[7]) if sys.argv[7] else None
        if sys.argv[6] == "rollback":
            restore_package(Path(sys.argv[1]), transaction)
        else:
            ensure_tools(
                Path(sys.argv[1]),
                Path(sys.argv[3]),
                Path(sys.argv[4]),
                Path(sys.argv[5]),
                repair=sys.argv[2] == "true" and sys.argv[6] != "check",
                transaction=transaction,
            )
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        subprocess.TimeoutExpired,
        zipfile.BadZipFile,
        ET.ParseError,
    ) as error:
        print(f"use-venv: {error}", file=sys.stderr)
        sys.exit(1)
CURSOR_PYTHON
}

check_cursor_requirements() {
  local tools_status=0 api_status=0
  local tools_message="" api_message=""
  local repair_blocked=false
  if tools_message="$(ensure_cursor_environment_tools check 2>&1)"; then
    print -r -- "$tools_message"
  else
    tools_status=$?
    print -ru2 -- "$tools_message"
  fi
  if api_message="$(run_cursor_automation check-cursor-api 2>&1)"; then
    USE_VENV_CURSOR_API_REQUIRED=false
    print -r -- "$api_message"
  else
    api_status=$?
    USE_VENV_CURSOR_API_REQUIRED=true
    print -ru2 -- "$api_message"
  fi
  if [[ "${1:-}" == verify ]]; then
    ((tools_status == 0 && api_status == 0))
    return
  fi
  if ((tools_status != 0)); then
    if [[ "$repair_cursor_envs" == true ]]; then
      print -ru2 -- "use-venv: Cursor environment package repair is authorized; it has not started."
    else
      print -ru2 -- "use-venv: Rerun the same command with --repair-cursor-envs to allow environment package repair."
      repair_blocked=true
    fi
  fi
  if ((api_status != 0)); then
    if [[ "$cursor_api_action" == repair-cursor-api ]]; then
      print -ru2 -- "use-venv: Cursor API repair is authorized; it has not started."
    else
      print -ru2 -- "use-venv: Rerun the same command with --repair-cursor-api to allow API repair."
      repair_blocked=true
    fi
  fi
  if [[ "$repair_blocked" == true ]]; then
    print -ru2 -- "use-venv: Stopped before repairs or shared editor configuration changes; authorize all required repairs before retrying."
    return 1
  fi
  return 0
}

begin_cursor_repair_transaction() {
  prepare_runtime_state
  local temporary_root="$USE_VENV_STATE_DIRECTORY"
  USE_VENV_CURSOR_REPAIR_DIRECTORY="$(mktemp -d "$temporary_root/cursor-envs-transaction.XXXXXXXX")"
}

cursor_reload_state() {
  local log_directory="${USE_VENV_CURSOR_LOG_DIRECTORY:-$HOME/Library/Application Support/Cursor/logs}"
  local before="${2:-}"
  [[ -n "$before" ]] || before="{}"
  python3 - "$log_directory" "$1" "$before" \
    "$USE_VENV_WORKSPACE_DIRECTORY" "$USE_VENV_DIRECTORY/bin/python" \
    "${3:-discovery}" <<'CURSOR_RELOAD_PYTHON'
import json
import re
import sys
import time
from pathlib import Path


def log_paths(root):
    for pattern in (
        "*/window*/exthost/exthost.log",
        "*/window*/exthost/ms-python.vscode-python-envs/Python Environments.log",
    ):
        yield from root.glob(pattern)


def snapshot(root):
    return {
        str(path): [path.stat().st_ino, path.stat().st_size] for path in log_paths(root)
    }


def fresh_text(path, before):
    try:
        status = path.stat()
        inode, offset = before.get(str(path), [None, 0])
        if inode != status.st_ino or status.st_size < offset:
            offset = 0
        with path.open("rb") as source:
            source.seek(offset)
            return source.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def reload_ready(root, before, workspace, interpreter, discovery=True):
    for path in root.glob(
        "*/window*/exthost/ms-python.vscode-python-envs/Python Environments.log"
    ):
        text = fresh_text(path, before)
        configured = False
        for line in text.splitlines():
            if "configure: Sending configuration update:" not in line:
                continue
            try:
                config = json.loads(line[line.index("{") :])
                if isinstance(config, dict):
                    configured |= str(workspace) in config.get(
                        "workspaceDirectories", []
                    )
            except (ValueError, TypeError):
                continue
        if not configured:
            continue
        host = fresh_text(path.parents[1] / "exthost.log", before)
        # Require a new host, not just an older host's live configuration update.
        starts = list(re.finditer(r"Extension host with pid \d+ started", host))
        if not starts:
            continue
        if (
            "Extension activated success: ms-python.vscode-python-envs"
            not in host[starts[0].start() :]
        ):
            continue
        if not discovery or (
            "Environment discovery complete:" in text
            and f"Discovered env: {interpreter}\n" in text + "\n"
        ):
            return True
    return False


def wait_for_reload(root, before, workspace, interpreter, discovery=True, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if reload_ready(root, before, workspace, interpreter, discovery):
            return
        time.sleep(0.25)
    stage = "target environment discovery" if discovery else "extension activation"
    raise RuntimeError(f"Cursor reload did not finish {stage} within {timeout} seconds")


if __name__ == "__main__":
    try:
        root = Path(sys.argv[1])
        if sys.argv[2] == "snapshot":
            print(json.dumps(snapshot(root)))
        else:
            wait_for_reload(
                root,
                json.loads(sys.argv[3]),
                Path(sys.argv[4]),
                sys.argv[5],
                discovery=sys.argv[6] == "discovery",
            )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"use-venv: {error}", file=sys.stderr)
        sys.exit(1)
CURSOR_RELOAD_PYTHON
}

reload_cursor_after_package_change() {
  local readiness="${1:-discovery}"
  configure_editor cursor
  local editor_state=0
  editor_process_state || editor_state=$?
  case "$editor_state" in
    0) ;;
    1) return 0 ;; # A closed Cursor will load the package when next opened.
    *)
      print -u2 "use-venv: cannot determine whether Cursor is running after replacing its extension"
      return 1
      ;;
  esac
  local before
  if ! before="$(
    cursor_reload_state snapshot
    exit $?
  )"; then
    print -u2 "use-venv: cannot snapshot Cursor startup logs"
    return 1
  fi
  reload_editor || return 1
  print "Waiting:     Cursor extension startup and $readiness..."
  if ! cursor_reload_state wait "$before" "$readiness"; then
    print -u2 "use-venv: Cursor was not ready after reloading its window"
    return 1
  fi
  USE_VENV_CURSOR_RELOADED=true
}

finish_cursor_repair_transaction() {
  local task_directory="$USE_VENV_CURSOR_REPAIR_DIRECTORY"
  [[ -n "$task_directory" ]] || return 0
  if [[ "$USE_VENV_CURSOR_REPAIR_COMMITTED" != true && -f "$task_directory/backup.json" ]]; then
    print -u2 "use-venv: restoring the original Cursor extension package..."
    if ! ensure_cursor_environment_tools rollback; then
      print -u2 "use-venv: extension rollback failed; backup remains at $task_directory"
      return 1
    fi
    # A closed Cursor loads the restored package on its next launch.
    local editor_state=0
    configure_editor cursor
    editor_process_state || editor_state=$?
    if ((editor_state == 0)); then
      if ! reload_cursor_after_package_change activation; then
        print -u2 "use-venv: original package restored on disk, but runtime synchronization failed; backup remains at $task_directory"
        return 1
      fi
    elif ((editor_state != 1)); then
      print -u2 "use-venv: cannot verify Cursor runtime after rollback; backup remains at $task_directory"
      return 1
    fi
  fi
  # Only the files created by this invocation are eligible for cleanup.
  local temporary_root="$USE_VENV_STATE_DIRECTORY"
  [[ ! -L "$temporary_root" && ! -L "$task_directory" && "${task_directory:A:h}" == "${temporary_root:A}" ]] || return 1
  rm -f "$task_directory/original.vsix" "$task_directory/backup.json"
  rmdir "$task_directory" || return 1
  USE_VENV_CURSOR_REPAIR_DIRECTORY=""
}

install_command() {
  local script_path="$USE_VENV_SCRIPT_PATH"
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
    if [[ "${command_path:A}" != "$USE_VENV_SCRIPT_PATH" ]]; then
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

  search_directory="$(absolute_directory "$requested_directory")" ||
    fail "directory does not exist: $requested_directory"

  if [[ -x "$search_directory/bin/python" && -f "$search_directory/bin/activate" ]]; then
    USE_VENV_DIRECTORY="$search_directory"
    USE_VENV_PROJECT_DIRECTORY="${search_directory:h}"
    return
  fi

  while [[ "$search_directory" != "/" ]]; do
    if [[ -x "$search_directory/.venv/bin/python" ]]; then
      USE_VENV_PROJECT_DIRECTORY="$search_directory"
      USE_VENV_DIRECTORY="$search_directory/.venv"
      return
    fi
    search_directory="${search_directory:h}"
  done

  fail "no .venv with an executable Python was found at or above: $requested_directory"
}

find_workspace() {
  local requested_workspace="$1"
  local search_directory="$USE_VENV_PROJECT_DIRECTORY"
  local git_workspace=""

  if [[ -n "$requested_workspace" ]]; then
    USE_VENV_WORKSPACE_DIRECTORY="$(absolute_directory "$requested_workspace")" ||
      fail "workspace directory does not exist: $requested_workspace"
    return
  fi

  while [[ "$search_directory" != "/" ]]; do
    if [[ -f "$search_directory/.vscode/settings.json" ]]; then
      USE_VENV_WORKSPACE_DIRECTORY="$search_directory"
      return
    fi
    if [[ -z "$git_workspace" && -d "$search_directory/.git" ]]; then
      git_workspace="$search_directory"
    fi
    search_directory="${search_directory:h}"
  done

  USE_VENV_WORKSPACE_DIRECTORY="${git_workspace:-$USE_VENV_PROJECT_DIRECTORY}"
}

update_vscode_settings() {
  local settings_directory="$USE_VENV_WORKSPACE_DIRECTORY/.vscode"
  local settings_path="$settings_directory/settings.json"
  local launch_path="$settings_directory/launch.json"

  mkdir -p "$settings_directory"

  python3 - \
    "$settings_path" \
    "$USE_VENV_WORKSPACE_DIRECTORY" \
    "$USE_VENV_PROJECT_DIRECTORY" \
    "$USE_VENV_DIRECTORY" \
    "$launch_path" <<'PYTHON'
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


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


def detect_test_framework(project: Path) -> str | None:
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
    "cursorpyright.analysis.extraPaths": [source_setting],
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
  print "Workspace:   $USE_VENV_WORKSPACE_DIRECTORY"
  print "Project:     $USE_VENV_PROJECT_DIRECTORY"
  print "Interpreter: $USE_VENV_DIRECTORY/bin/python"
  "$USE_VENV_DIRECTORY/bin/python" --version
}

# Reads selection state without writing either extension's private storage.
# Python Environments is preferred; older Python extensions use a separate key.
editor_workspace_selected_venv() {
  local storage_directory="${USE_VENV_EDITOR_STORAGE_DIRECTORY:-$HOME/Library/Application Support/$USE_VENV_EDITOR_STORAGE_NAME/User/workspaceStorage}"
  python3 - "$USE_VENV_WORKSPACE_DIRECTORY" "$storage_directory" <<'PYTHON'
import json
import os
import sqlite3
import sys
import urllib.parse

workspace = sys.argv[1]
folder_uri = "file://" + urllib.parse.quote(workspace)
storage_base = sys.argv[2]
if not os.path.isdir(storage_base):
    sys.exit(0)

for entry_name in os.listdir(storage_base):
    entry_directory = os.path.join(storage_base, entry_name)
    workspace_file = os.path.join(entry_directory, "workspace.json")
    if not os.path.isfile(workspace_file):
        continue
    try:
        with open(workspace_file, encoding="utf-8") as workspace_handle:
            workspace_metadata = json.load(workspace_handle)
    except (OSError, ValueError):
        continue
    if workspace_metadata.get("folder") != folder_uri:
        continue

    database_path = os.path.join(entry_directory, "state.vscdb")
    if not os.path.isfile(database_path):
        sys.exit(0)
    try:
        connection = sqlite3.connect("file:" + database_path + "?mode=ro", uri=True)
        try:
            rows = dict(
                connection.execute(
                    "SELECT key, value FROM ItemTable WHERE key IN (?, ?)",
                    ("ms-python.vscode-python-envs", "ms-python.python"),
                ).fetchall()
            )
        finally:
            connection.close()
        payload = json.loads(rows.get("ms-python.vscode-python-envs", "{}"))
        selected = payload.get(
            "ms-python.vscode-python-envs:venv:WORKSPACE_SELECTED", {}
        )
        stored = selected.get(workspace) if isinstance(selected, dict) else None
        if isinstance(stored, str) and stored:
            print(stored)
            sys.exit(0)

        payload = json.loads(rows.get("ms-python.python", "{}"))
        selected = payload.get("userSelectedEnvPath", {})
        if isinstance(selected, str):
            selected = json.loads(selected)
        stored = selected.get(folder_uri) if isinstance(selected, dict) else None
        if isinstance(stored, str) and stored:
            print(stored)
            sys.exit(0)
        for key in (
            "lastKnownActiveInterpreter:" + workspace,
            "autoSelectedWorkspacePythonInterpreter-" + workspace,
        ):
            interpreter = payload.get(key, {})
            if isinstance(interpreter, dict):
                stored = interpreter.get("path")
                if isinstance(stored, str) and stored:
                    print(stored)
                    sys.exit(0)
    except (sqlite3.Error, ValueError):
        sys.exit(0)
    sys.exit(0)
PYTHON
}

# Re-reads the selection a few times so the read-back verification tolerates
# the extension's own state-write latency after a UI selection.
workspace_environment_is_target() {
  local target_interpreter="$1"
  local attempt
  local stored_interpreter=""
  for attempt in 1 2 3; do
    stored_interpreter="$(editor_workspace_selected_venv)" || return 1
    if [[ "$stored_interpreter" == "$target_interpreter" ]]; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

# Read bundle IDs from installed applications, then query running applications.
# Return 1 only for a successful query with no matching running application;
# return 2 when the query itself fails. This does not launch either editor.
editor_process_state() {
  local running_application=""
  running_application="$(
    osascript -l JavaScript - "$USE_VENV_EDITOR_APPLICATION" <<'JAVASCRIPT'
ObjC.import("AppKit");

function bundleIdentifier(path) {
  const bundle = $.NSBundle.bundleWithPath($(path));
  const identifier = bundle && ObjC.unwrap(bundle.objectForInfoDictionaryKey("CFBundleIdentifier"));
  if (typeof identifier !== "string" || !identifier.trim()) {
    throw new Error("Cannot read CFBundleIdentifier from " + path);
  }
  return identifier;
}

function run(argv) {
  const primary = argv[0];
  const candidates = [primary];
  if (primary === "Visual Studio Code") {
    candidates.push("Visual Studio Code - Insiders");
  }
  const applications = $.NSWorkspace.sharedWorkspace.runningApplications;
  if (!applications) {
    throw new Error("Cannot query running macOS applications");
  }
  let installed = false;
  const home = ObjC.unwrap($.NSHomeDirectory());
  for (const candidate of candidates) {
    const paths = [];
    // Prefer the actual running bundle, including apps installed elsewhere.
    for (let index = 0; index < applications.count; index++) {
      const application = applications.objectAtIndex(index);
      const url = application.bundleURL;
      if (url && ObjC.unwrap(url.lastPathComponent) === candidate + ".app") {
        paths.push(ObjC.unwrap(url.path));
      }
    }
    paths.push("/Applications/" + candidate + ".app");
    paths.push(home + "/Applications/" + candidate + ".app");
    for (const path of paths) {
      if (!$.NSFileManager.defaultManager.fileExistsAtPath($(path))) {
        continue;
      }
      installed = true;
      const identifier = bundleIdentifier(path);
      for (let index = 0; index < applications.count; index++) {
        const application = applications.objectAtIndex(index);
        if (ObjC.unwrap(application.bundleIdentifier) === identifier) {
          return candidate;
        }
      }
    }
  }
  if (!installed) {
    throw new Error("Cannot locate installed application: " + primary);
  }
  return "";
}
JAVASCRIPT
  )" || return 2

  if [[ "$running_application" == "$USE_VENV_EDITOR_APPLICATION" ]]; then
    return 0
  elif [[ "$USE_VENV_EDITOR_APPLICATION" == "Visual Studio Code" &&
    "$running_application" == "Visual Studio Code - Insiders" ]]; then
    USE_VENV_EDITOR_APPLICATION="Visual Studio Code - Insiders"
    USE_VENV_EDITOR_PROCESS="Code - Insiders"
    USE_VENV_EDITOR_STORAGE_NAME="Code - Insiders"
    return 0
  elif [[ -z "$running_application" ]]; then
    return 1
  fi
  return 2
}

# Uses the Python project name when available because Python Environments shows
# it as the environment label. The project directory name can differ (for
# example, a generic scripts/ directory), so it is not a reliable first filter.
vscode_environment_filter_text() {
  local pyproject_path="$USE_VENV_PROJECT_DIRECTORY/pyproject.toml"
  local project_name=""

  if [[ -f "$pyproject_path" ]]; then
    project_name="$(
      "$USE_VENV_DIRECTORY/bin/python" - "$pyproject_path" <<'PYTHON'
import re
import sys
from pathlib import Path

pyproject_path = Path(sys.argv[1])
source = pyproject_path.read_text(encoding="utf-8")

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

if tomllib is not None:
    try:
        project = tomllib.loads(source).get("project", {})
        name = project.get("name") if isinstance(project, dict) else None
    except (OSError, ValueError):
        name = None
else:
    name = None

if not isinstance(name, str) or not name:
    project_section = re.search(r"(?ms)^\[project\]\s*$\n(.*?)(?=^\[|\Z)", source)
    name_match = (
        re.search(r"(?m)^\s*name\s*=\s*['\"]([^'\"]+)['\"]", project_section.group(1))
        if project_section
        else None
    )
    name = name_match.group(1) if name_match else None

if isinstance(name, str) and name:
    print(name)
PYTHON
    )" || project_name=""
  fi

  print -r -- "${project_name:-${USE_VENV_PROJECT_DIRECTORY:t}}"
}

# Cursor uses the local helper and Python Environments API. VS Code retains
# its existing guarded picker workflow. Both paths verify the selected path.
ensure_workspace_environment() {
  local target_interpreter="$USE_VENV_DIRECTORY/bin/python"
  if [[ "$(uname -s)" != "Darwin" ]] || ! command -v osascript >/dev/null; then
    USE_VENV_SELECTION_PENDING=true
    print -u2 "Pending: $USE_VENV_EDITOR_LABEL interpreter selection requires macOS automation; select $target_interpreter manually."
    return
  fi

  local editor_process_status=0
  editor_process_state || editor_process_status=$?
  case "$editor_process_status" in
    0) ;;
    1)
      USE_VENV_SELECTION_PENDING=true
      print -u2 "Pending: $USE_VENV_EDITOR_LABEL is not running; shared settings were updated, but its interpreter selection was not synchronized. Open the target workspace and rerun use-venv with --editor, or select $target_interpreter manually."
      return 0
      ;;
    *)
      fail "cannot determine whether $USE_VENV_EDITOR_LABEL is running because the macOS application query failed; interpreter selection was not attempted"
      ;;
  esac

  if [[ "$USE_VENV_EDITOR_PROCESS" == "Cursor" ]]; then
    run_cursor_automation select-environment || fail "Cursor API interpreter selection failed"
    return
  fi

  local stored_interpreter=""
  stored_interpreter="$(editor_workspace_selected_venv)" || true
  # Different uv virtual environments can share the same resolved executable.
  # Compare environment paths exactly, without resolving interpreter symlinks.
  if [[ "$stored_interpreter" == "$target_interpreter" ]]; then
    print "Selected:    $target_interpreter in $USE_VENV_EDITOR_LABEL (already aligned)"
    return
  fi

  print "Selecting:   $target_interpreter in $USE_VENV_EDITOR_LABEL..."
  select_editor_environment
  if workspace_environment_is_target "$target_interpreter"; then
    print "Selected:    $target_interpreter in $USE_VENV_EDITOR_LABEL"
    return
  fi

  # In a multi-project workspace the picker may ask for the project first;
  # select again inside the now-open environment picker.
  finish_environment_selection
  if ! workspace_environment_is_target "$target_interpreter"; then
    fail "could not verify $USE_VENV_EDITOR_LABEL interpreter selection; select $target_interpreter manually and run use-venv again"
  fi
  print "Selected:    $target_interpreter in $USE_VENV_EDITOR_LABEL"
}

select_editor_environment() {
  local environment_filter_text="$(vscode_environment_filter_text)"
  local project_filter_text="${USE_VENV_PROJECT_DIRECTORY:t}"
  local -a filter_texts=("$environment_filter_text")
  if [[ "$project_filter_text" != "$environment_filter_text" ]]; then
    filter_texts+=("$project_filter_text")
  fi

  local -a select_commands=(
    "Python: Select Interpreter"
    "Python: 选择解释器"
  )

  run_environment_selection_automation() {
    local filter_text="$1"
    osascript - "$USE_VENV_EDITOR_APPLICATION" "$USE_VENV_EDITOR_PROCESS" "${USE_VENV_WORKSPACE_DIRECTORY:t}" "$filter_text" "${select_commands[@]}" <<'APPLESCRIPT'
on run argv
    set applicationName to item 1 of argv as text
    set processName to item 2 of argv as text
    set workspaceName to item 3 of argv as text
    set filterText to item 4 of argv as text
    set previousClipboard to the clipboard
    try
        tell application applicationName to activate
        delay 0.3

        tell application "System Events"
            tell process processName
                if (count of windows) is 0 then error "Target editor has no workspace window"
                if processName is "Cursor" then
                    -- Cursor can expose an auxiliary AXDialog before its IDE window.
                    set targetWindow to value of attribute "AXMainWindow"
                    if name of targetWindow does not contain workspaceName then error "Target editor window does not match workspace " & workspaceName
                    perform action "AXRaise" of targetWindow
                else
                    if name of front window does not contain workspaceName then error "Target editor window does not match workspace " & workspaceName
                end if
            end tell
        end tell

        tell application "System Events"
            tell process processName
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
                if commandPaletteItem is missing value then error "Cannot find the Editor Command Palette menu item"

                click commandPaletteItem
                delay 0.5

                -- Confirm the command palette result list received focus.
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
                if processName is "Cursor" and not commandListFound then set commandListFound to my cursorQuickPickHasFocus(processName)
                if not commandListFound then error "Editor Command Palette result list did not receive focus"
            end tell

            -- Run the interpreter selection command, trying each locale with a
            -- fresh palette. Clearing the query text does not work reliably in
            -- current VS Code versions, so close and reopen the palette
            -- instead.
            set selectCommandFound to false
            repeat with commandIndex from 5 to (count of argv)
                set commandText to item commandIndex of argv as text
                tell process processName
                    set commandPaletteItem to missing value
                    repeat with candidateItem in menu items of menu "View" of menu bar 1
                        try
                            if (value of attribute "AXMenuItemCmdChar" of candidateItem is "P") and (value of attribute "AXMenuItemCmdModifiers" of candidateItem is 1) then
                                set commandPaletteItem to candidateItem
                                exit repeat
                            end if
                        end try
                    end repeat
                    if commandPaletteItem is missing value then error "Cannot find the Editor Command Palette menu item"
                    click commandPaletteItem
                    delay 0.5
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
                    if processName is "Cursor" and not commandListFound then set commandListFound to my cursorQuickPickHasFocus(processName)
                    if not commandListFound then error "Editor Command Palette result list did not receive focus"
                end tell

                set the clipboard to commandText
                keystroke "v" using {command down}
                delay 0.6

                tell process processName
                    set focusedElement to value of attribute "AXFocusedUIElement"
                    try
                        set focusedValue to value of attribute "AXValue" of focusedElement as text
                    on error
                        set focusedValue to ""
                    end try
                end tell

                if focusedValue contains commandText then
                    set selectCommandFound to true
                    exit repeat
                end if

                key code 53
                delay 0.3
            end repeat

            if not selectCommandFound then error "Editor did not select a supported interpreter selection command"

            key code 36
            delay 0.6

            -- Type the environment filter and confirm the picker matched it.
            set pickerListFound to false
            tell process processName
                set currentElement to value of attribute "AXFocusedUIElement"
                repeat 8 times
                    try
                        if value of attribute "AXRole" of currentElement is "AXList" then
                            set pickerListFound to true
                            exit repeat
                        end if
                        set currentElement to value of attribute "AXParent" of currentElement
                    on error
                        exit repeat
                    end try
                end repeat
            end tell
            if processName is "Cursor" and not pickerListFound then set pickerListFound to my cursorQuickPickHasFocus(processName)
            if not pickerListFound then error "Editor environment picker did not receive focus"

            set the clipboard to filterText
            keystroke "v" using {command down}
            delay 0.6

            tell process processName
                set focusedElement to value of attribute "AXFocusedUIElement"
                try
                    set focusedRole to value of attribute "AXRole" of focusedElement as text
                    set focusedValue to value of attribute "AXValue" of focusedElement as text
                on error
                    set focusedValue to ""
                end try
            end tell
            -- A focused text field means the filter matched no result row; the
            -- Quick Pick focuses the first result's static text instead.
            if focusedRole is "AXTextField" or focusedValue does not contain filterText then error "Environment picker did not match " & filterText

            key code 36
            delay 0.4

            set the clipboard to previousClipboard
        end tell
    on error errorMessage number errorNumber
        try
            set the clipboard to previousClipboard
            tell application "System Events" to key code 53
        end try
        error errorMessage number errorNumber
    end try
end run


-- Cursor can publish its Quick Pick focus after the initial menu delay.
-- Keep the original immediate checks for VS Code and retry only for Cursor.
on cursorQuickPickHasFocus(processName)
    repeat 200 times
        delay 0.1
        tell application "System Events"
            tell process processName
                try
                    set currentElement to value of attribute "AXFocusedUIElement"
                    repeat 12 times
                        if value of attribute "AXRole" of currentElement is "AXList" then return true
                        set currentElement to value of attribute "AXParent" of currentElement
                    end repeat
                end try
            end tell
        end tell
    end repeat
    return false
end cursorQuickPickHasFocus
APPLESCRIPT
  }

  local automation_error=""
  local filter_text=""
  for filter_text in "${filter_texts[@]}"; do
    if automation_error="$(run_environment_selection_automation "$filter_text" 2>&1)"; then
      return
    fi
    if [[ "$automation_error" != *"Environment picker did not match"* ]]; then
      break
    fi
  done

  if [[ "$automation_error" != *"not allowed assistive access"* &&
    "$automation_error" != *"不允许辅助访问"* &&
    "$automation_error" != *"(-25211)"* ]]; then
    fail "$USE_VENV_EDITOR_LABEL environment selection was not performed: $automation_error"
  fi

  if [[ ! -t 0 ]]; then
    fail "macOS denied UI control; grant Accessibility access to the terminal application and run use-venv again"
  fi

  print -u2 "macOS denied UI control. Opening Accessibility settings..."
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
  print -u2 "Enable Accessibility access for the calling terminal/editor, then return here."
  read "?Press Enter to retry the environment selection: "

  run_environment_selection_automation "$filter_text" ||
    fail "$USE_VENV_EDITOR_LABEL environment selection was still denied; verify Accessibility access and run use-venv again"
}

# Second selection round for two-step pickers (project first, then
# environment). Refuses to type unless a picker list is focused, so a closed
# picker never writes the filter into an editor.
finish_environment_selection() {
  local filter_text="$(vscode_environment_filter_text)"

  run_environment_selection_finish() {
    osascript - "$USE_VENV_EDITOR_APPLICATION" "$USE_VENV_EDITOR_PROCESS" "${USE_VENV_WORKSPACE_DIRECTORY:t}" "$filter_text" <<'APPLESCRIPT'
on run argv
    set applicationName to item 1 of argv as text
    set processName to item 2 of argv as text
    set workspaceName to item 3 of argv as text
    set filterText to item 4 of argv as text
    set previousClipboard to the clipboard
    try
        tell application applicationName to activate
        delay 0.3

        tell application "System Events"
            tell process processName
                if (count of windows) is 0 then error "Target editor has no workspace window"
                if processName is "Cursor" then
                    -- Cursor can expose an auxiliary AXDialog before its IDE window.
                    set targetWindow to value of attribute "AXMainWindow"
                    if name of targetWindow does not contain workspaceName then error "Target editor window does not match workspace " & workspaceName
                    perform action "AXRaise" of targetWindow
                else
                    if name of front window does not contain workspaceName then error "Target editor window does not match workspace " & workspaceName
                end if
            end tell
        end tell

        tell application "System Events"
            set pickerListFound to false
            tell process processName
                set currentElement to value of attribute "AXFocusedUIElement"
                repeat 8 times
                    try
                        if value of attribute "AXRole" of currentElement is "AXList" then
                            set pickerListFound to true
                            exit repeat
                        end if
                        set currentElement to value of attribute "AXParent" of currentElement
                    on error
                        exit repeat
                    end try
                end repeat
            end tell
            if processName is "Cursor" and not pickerListFound then set pickerListFound to my cursorQuickPickHasFocus(processName)
            if not pickerListFound then error "Editor environment picker is not open"

            set the clipboard to filterText
            keystroke "v" using {command down}
            delay 0.6

            tell process processName
                set focusedElement to value of attribute "AXFocusedUIElement"
                try
                    set focusedRole to value of attribute "AXRole" of focusedElement as text
                    set focusedValue to value of attribute "AXValue" of focusedElement as text
                on error
                    set focusedValue to ""
                end try
            end tell
            -- A focused text field means the filter matched no result row; the
            -- Quick Pick focuses the first result's static text instead.
            if focusedRole is "AXTextField" or focusedValue does not contain filterText then error "Environment picker did not match " & filterText

            key code 36
            delay 0.4

            set the clipboard to previousClipboard
        end tell
    on error errorMessage number errorNumber
        try
            set the clipboard to previousClipboard
            tell application "System Events" to key code 53
        end try
        error errorMessage number errorNumber
    end try
end run


-- Cursor can publish its Quick Pick focus after the initial menu delay.
-- Keep the original immediate checks for VS Code and retry only for Cursor.
on cursorQuickPickHasFocus(processName)
    repeat 200 times
        delay 0.1
        tell application "System Events"
            tell process processName
                try
                    set currentElement to value of attribute "AXFocusedUIElement"
                    repeat 12 times
                        if value of attribute "AXRole" of currentElement is "AXList" then return true
                        set currentElement to value of attribute "AXParent" of currentElement
                    end repeat
                end try
            end tell
        end tell
    end repeat
    return false
end cursorQuickPickHasFocus
APPLESCRIPT
  }

  local automation_error=""
  if automation_error="$(run_environment_selection_finish 2>&1)"; then
    return
  fi

  if [[ "$automation_error" != *"not allowed assistive access"* &&
    "$automation_error" != *"不允许辅助访问"* &&
    "$automation_error" != *"(-25211)"* ]]; then
    fail "$USE_VENV_EDITOR_LABEL environment selection was not completed: $automation_error"
  fi

  if [[ ! -t 0 ]]; then
    fail "macOS denied UI control; grant Accessibility access to the terminal application and run use-venv again"
  fi

  print -u2 "macOS denied UI control. Opening Accessibility settings..."
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
  print -u2 "Enable Accessibility access for the calling terminal/editor, then return here."
  read "?Press Enter to retry the environment selection: "

  run_environment_selection_finish ||
    fail "$USE_VENV_EDITOR_LABEL environment selection was still denied; verify Accessibility access and run use-venv again"
}

reload_editor() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    print -u2 "use-venv: automatic editor reload is currently supported only on macOS"
    return 1
  fi
  if ! command -v osascript >/dev/null; then
    print -u2 "use-venv: osascript is required to reload the editor"
    return 1
  fi

  if [[ "$USE_VENV_EDITOR_PROCESS" == "Cursor" ]]; then
    print "Reloading Cursor..."
    run_cursor_automation reload-window
    return $?
  fi

  local -a reload_commands=(
    "Developer: Reload Window"
    "开发人员: 重新加载窗口"
  )

  run_vscode_reload_automation() {
    osascript - "$USE_VENV_EDITOR_APPLICATION" "$USE_VENV_EDITOR_PROCESS" "${USE_VENV_WORKSPACE_DIRECTORY:t}" "${reload_commands[@]}" <<'APPLESCRIPT'
on run argv
    set applicationName to item 1 of argv as text
    set processName to item 2 of argv as text
    set workspaceName to item 3 of argv as text
    set previousClipboard to the clipboard
    try
        tell application applicationName to activate
        delay 0.3

        tell application "System Events"
            tell process processName
                if (count of windows) is 0 then error "Target editor has no workspace window"
                if name of front window does not contain workspaceName then error "Target editor window does not match workspace " & workspaceName
            end tell
        end tell

        tell application "System Events"
            tell process processName
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
                if commandPaletteItem is missing value then error "Cannot find the Editor Command Palette menu item"

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
                if not commandListFound then error "Editor Command Palette result list did not receive focus"
            end tell

            set reloadCommandFound to false
            repeat with commandIndex from 4 to (count of argv)
                set commandText to item commandIndex of argv as text
                set the clipboard to commandText
                keystroke "v" using {command down}
                delay 0.5

                tell process processName
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

            if not reloadCommandFound then error "Editor did not select a supported Reload Window command"

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

  print "Reloading $USE_VENV_EDITOR_LABEL..."
  local automation_error=""
  # zsh command substitutions in EXIT handlers need an explicit exit status.
  if automation_error="$(
    run_vscode_reload_automation 2>&1
    exit $?
  )"; then
    return
  fi

  if [[ "$automation_error" != *"not allowed assistive access"* &&
    "$automation_error" != *"不允许辅助访问"* &&
    "$automation_error" != *"(-25211)"* ]]; then
    print -u2 "use-venv: $USE_VENV_EDITOR_LABEL reload was not performed: $automation_error"
    return 1
  fi

  if [[ ! -t 0 ]]; then
    print -u2 "use-venv: macOS denied UI control; grant Accessibility access to the terminal application and run use-venv again"
    return 1
  fi

  print -u2 "macOS denied UI control. Opening Accessibility settings..."
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
  print -u2 "Enable Accessibility access for the calling terminal/editor, then return here."
  read "?Press Enter to retry the $USE_VENV_EDITOR_LABEL reload: "

  if ! run_vscode_reload_automation; then
    print -u2 "use-venv: $USE_VENV_EDITOR_LABEL reload was still denied; verify Accessibility access and run use-venv again"
    return 1
  fi
}

run_cursor_automation() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "Cursor automation requires macOS"
  python3 - "$1" "$USE_VENV_WORKSPACE_DIRECTORY" "$USE_VENV_DIRECTORY/bin/python" <<'CURSOR_API_PYTHON'
import base64
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import types
import zipfile
from contextlib import contextmanager
from pathlib import Path

EXTENSION = "ms-python.vscode-python-envs"
PROPOSAL = "terminalDataWriteEvent"


# Generated by scripts/cursor-helper/build.py; edit the helper sources instead.
HELPER_ARCHIVE_B64 = "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"
HELPER_ARCHIVE = base64.b64decode(HELPER_ARCHIVE_B64)
with zipfile.ZipFile(io.BytesIO(HELPER_ARCHIVE)) as helper_archive:
    helper_manifest = json.loads(helper_archive.read("extension/package.json"))
    helper_transport = types.ModuleType("use_venv_helper_transport")
    exec(  # noqa: S102 -- bundled transport source, never external input
        compile(helper_archive.read("client.py"), "use-venv-helper/client.py", "exec"),
        helper_transport.__dict__,
    )
HELPER_REVISION = helper_manifest["useVenvRevision"]


def helper_ready(app, workspace, force=False):
    if not force:
        try:
            return helper_transport.find(workspace, HELPER_REVISION)
        except helper_transport.HelperUnavailable:
            pass
    extensions = Path(
        os.environ.get(
            "USE_VENV_CURSOR_EXTENSION_DIRECTORY",
            str(Path.home() / ".cursor/extensions"),
        )
    )
    installed = False
    registry = extensions / "extensions.json"
    if registry.exists():
        for entry in json.loads(registry.read_text()):
            if entry.get("identifier", {}).get("id") == "ai-demo-local.use-venv-helper":
                manifest = extensions / entry["relativeLocation"] / "package.json"
                installed = (
                    json.loads(manifest.read_text()).get("useVenvRevision")
                    == HELPER_REVISION
                )
    if installed and not force:
        return helper_transport.wait(workspace, HELPER_REVISION)
    executable = Path(app["path"]) / "Contents/Resources/app/bin/cursor"
    with tempfile.TemporaryDirectory(
        prefix="helper-install-", dir=runtime_directory()
    ) as folder:
        package = Path(folder) / "use-venv-helper.vsix"
        package.write_bytes(HELPER_ARCHIVE)
        run(
            [
                str(executable),
                "--extensions-dir",
                str(extensions),
                "--install-extension",
                str(package),
                "--force",
            ],
            timeout=60,
            environment=editor_environment(),
        )
    try:
        helper_transport.find(workspace)
    except helper_transport.HelperUnavailable:
        external_process(app["pid"])
        print(
            "Loading newly installed Cursor helper; restarting Cursor normally...",
            flush=True,
        )
        restart(app, workspace)
        return helper_transport.wait(workspace, HELPER_REVISION)
    return helper_transport.reload(workspace, HELPER_REVISION)


def runtime_directory():
    root = Path(
        os.environ.get(
            "USE_VENV_STATE_DIRECTORY",
            str(Path.home() / "Library/Application Support/use-venv/transactions"),
        )
    ).expanduser()
    if not root.is_absolute() or root.is_symlink():
        raise RuntimeError(
            "Runtime state directory must be an absolute non-symlink path"
        )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root.resolve()


APP_QUERY = r"""
ObjC.import("AppKit");
function run() {
  const apps = $.NSWorkspace.sharedWorkspace.runningApplications;
  for (let i = 0; i < apps.count; i++) {
    const app = apps.objectAtIndex(i);
    if (app.bundleURL && ObjC.unwrap(app.bundleURL.lastPathComponent) === "Cursor.app") {
      return JSON.stringify({path: ObjC.unwrap(app.bundleURL.path), pid: Number(app.processIdentifier)});
    }
  }
  return "null";
}
"""


def run(arguments, *, source=None, timeout=30, environment=None):
    process = subprocess.Popen(
        arguments,
        stdin=subprocess.PIPE if source is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(source, timeout=timeout)
        if process.returncode:
            raise subprocess.CalledProcessError(
                process.returncode, arguments, stdout, stderr
            )
        return stdout.strip()
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                process.poll()
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def editor_environment():
    environment = os.environ.copy()
    # GUI launches should use the desktop's color policy, not an automation
    # runner's NO_COLOR=1 / TERM=dumb output settings.
    for key in (
        "NO_COLOR",
        "FORCE_COLOR",
        "CLICOLOR",
        "CLICOLOR_FORCE",
        "TERM",
        "COLORTERM",
    ):
        result = subprocess.run(
            ["launchctl", "getenv", key],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.rstrip("\n"):
            environment[key] = result.stdout.rstrip("\n")
        elif result.returncode in (0, 1):
            environment.pop(key, None)
        else:
            raise RuntimeError(f"Cannot read desktop environment variable {key}")
    return environment


def app_info():
    return json.loads(run(["osascript", "-l", "JavaScript", "-"], source=APP_QUERY))


def external_process(pid):
    parent = os.getpid()
    while parent > 1:
        if parent == pid:
            raise RuntimeError("Run this repair from a terminal outside Cursor")
        parent = int(run(["ps", "-p", str(parent), "-o", "ppid="]))


def process_table():
    processes = {}
    for line in run(
        ["ps", "-axo", "pid=,ppid=,state=,lstart=,command="], timeout=5
    ).splitlines():
        fields = line.split(None, 8)
        if len(fields) == 9:
            processes[int(fields[0])] = {
                "parent": int(fields[1]),
                "state": fields[2],
                "started": tuple(fields[3:8]),
                "command": fields[8],
            }
    return processes


def process_cwd(pid):
    try:
        output = run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], timeout=5)
    except subprocess.CalledProcessError as error:
        if error.returncode == 1:
            return None  # The process may have exited during the snapshot.
        raise
    paths = [
        Path(line[1:]).resolve() for line in output.splitlines() if line.startswith("n")
    ]
    return paths[0] if len(paths) == 1 else None


def discovery_snapshot(app, project):
    processes = process_table()
    extension_root = Path(
        os.environ.get(
            "USE_VENV_CURSOR_EXTENSION_DIRECTORY",
            str(Path.home() / ".cursor/extensions"),
        )
    ).resolve()
    pattern = re.compile(
        re.escape(str(extension_root))
        + r"/ms-python\.python-[^/\n]+/python_files/unittestadapter/discovery\.py\s+--udiscovery(?:\s|$)"
    )
    recorded = {}
    for pid, process in processes.items():
        if not pattern.search(process["command"]) or process["state"].startswith("Z"):
            continue
        ancestors = []
        parent = process["parent"]
        while parent in processes and parent != app["pid"] and parent not in ancestors:
            ancestors.append(parent)
            parent = processes[parent]["parent"]
        if parent != app["pid"]:
            continue
        owner = next(
            (
                ancestor
                for ancestor in ancestors
                if app["path"] + "/Contents/" in processes[ancestor]["command"]
                and "Cursor Helper (Plugin)" in processes[ancestor]["command"]
            ),
            None,
        )
        if owner is None or process_cwd(pid) != project.resolve():
            continue
        recorded[pid] = {
            **process,
            "owner": owner,
            "owner_started": processes[owner]["started"],
        }
    return recorded


def live_discoveries(recorded, processes):
    return {
        pid: processes[pid]
        for pid, original in recorded.items()
        if pid in processes
        and not processes[pid]["state"].startswith("Z")
        and processes[pid]["started"] == original["started"]
        and processes[pid]["command"] == original["command"]
    }


def orphan_discovery(pid, original, processes):
    current = live_discoveries({pid: original}, processes).get(pid)
    owner = processes.get(original["owner"])
    return (
        current is not None
        and current["parent"] == 1
        and (owner is None or owner["started"] != original["owner_started"])
    )


def wait_for_discoveries(recorded, timeout=2):
    deadline = time.monotonic() + timeout
    while True:
        processes = process_table()
        remaining = live_discoveries(recorded, processes)
        if not remaining or time.monotonic() >= deadline:
            return processes
        time.sleep(0.1)


def clean_discoveries(recorded):
    if not recorded:
        return
    processes = wait_for_discoveries(recorded)
    targets = {
        pid: original
        for pid, original in recorded.items()
        if orphan_discovery(pid, original, processes)
    }
    if not targets:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid, original in targets.items():
            # Re-read identity and ownership immediately before each signal.
            if orphan_discovery(pid, original, process_table()):
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
        processes = wait_for_discoveries(targets)
        if not live_discoveries(targets, processes):
            print(
                f"Cleaned:     {len(targets)} orphan Cursor unittest discovery task(s).",
                flush=True,
            )
            return
    remaining = live_discoveries(targets, processes)
    raise RuntimeError(
        "Cannot confirm exit of Cursor discovery processes: "
        + ", ".join(map(str, remaining))
    )


@contextmanager
def discovery_cleanup(app, project):
    recorded = discovery_snapshot(app, project)
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        try:
            clean_discoveries(recorded)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            if not failed:
                raise
            print(f"Cursor discovery cleanup was incomplete: {error}", file=sys.stderr)


def patch_product(original):
    document = json.loads(original)
    grants = document.get("extensionEnabledApiProposals", {}).get(EXTENSION)
    if not isinstance(grants, list):
        raise TypeError("Unexpected Cursor API grant structure; no changes made")
    if PROPOSAL in grants:
        return original
    # Preserve all unrelated bytes, including product.json's original formatting.
    pattern = re.compile(r'("ms-python\.vscode-python-envs"\s*:\s*)(\[[^\]]*\])')
    matches = list(pattern.finditer(original.decode()))
    if len(matches) != 1 or json.loads(matches[0][2]) != grants:
        raise RuntimeError("Cannot uniquely locate Cursor's API grant list")
    match = matches[0]
    changed = (
        original.decode()[: match.start(2)]
        + json.dumps([*grants, PROPOSAL])
        + original.decode()[match.end(2) :]
    )
    expected = json.loads(original)
    expected["extensionEnabledApiProposals"][EXTENSION].append(PROPOSAL)
    if json.loads(changed) != expected:
        raise RuntimeError("API patch changed unrelated settings")
    return changed.encode()


def preflight(app):
    extension_root = Path.home() / ".cursor/extensions"
    registry = json.loads((extension_root / "extensions.json").read_text())
    entries = [e for e in registry if e.get("identifier", {}).get("id") == EXTENSION]
    if len(entries) != 1:
        raise RuntimeError(
            "Cannot uniquely identify the installed Python Environments extension"
        )
    extension = (extension_root / entries[0]["relativeLocation"]).resolve()
    if extension_root.resolve() not in extension.parents:
        raise RuntimeError("Extension path escapes its installation directory")
    manifest = json.loads((extension / "package.json").read_text())
    if PROPOSAL not in manifest.get("enabledApiProposals", []):
        print("Checked:     installed Python Environments does not require this API.")
        return False
    host = (
        Path(app["path"])
        / "Contents/Resources/app/out/vs/workbench/api/node/extensionHostProcess.js"
    )
    if PROPOSAL not in host.read_text():
        raise RuntimeError("Installed Cursor does not expose the required API")
    return True


def check_api():
    app = app_info()
    if app is None:
        candidates = [
            Path("/Applications/Cursor.app"),
            Path.home() / "Applications/Cursor.app",
        ]
        bundle = next((path for path in candidates if path.is_dir()), None)
        if bundle is None:
            raise RuntimeError("Cannot locate the Cursor application")
        app = {"path": str(bundle)}
    if preflight(app) is False:
        return
    product = Path(app["path"]) / "Contents/Resources/app/product.json"
    original = product.read_bytes()
    if patch_product(original) != original:
        raise RuntimeError("Cursor is missing the terminalDataWriteEvent grant")
    print("Checked:     Cursor grants Python Environments terminalDataWriteEvent.")


def replace_guarded(product, expected, replacement, transaction):
    if product.read_bytes() != expected:
        raise RuntimeError("Cursor product.json changed concurrently; backup retained")
    # Preserve the application file's inode, permissions and extended attributes.
    # The original bytes are already backed up before opening it for writing.
    with product.open("r+b") as stream:
        if stream.read() != expected:
            raise RuntimeError(
                "Cursor product.json changed concurrently; backup retained"
            )
        stream.seek(0)
        stream.write(replacement)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
    if product.read_bytes() != replacement:
        raise RuntimeError("Cursor product.json write could not be verified")


def restart(app, workspace, project=None):
    current = app_info()
    if current:
        if current["path"] != app["path"]:
            raise RuntimeError("A different Cursor installation is now running")
        with discovery_cleanup(current, project or workspace):
            run(
                ["osascript", "-l", "JavaScript", "-", app["path"]],
                source="function run(argv) { Application(argv[0]).quit(); }",
            )
            deadline = time.monotonic() + 30
            while app_info():
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Cursor did not quit; check for an unsaved-file dialog"
                    )
                time.sleep(0.3)
    run(["open", "-a", app["path"], str(workspace)], environment=editor_environment())
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        current = app_info()
        if current and current["path"] == app["path"]:
            return current
        time.sleep(0.3)
    raise RuntimeError("Cursor did not restart within 40 seconds")


def reload_window(workspace, project=None):
    app = app_info()
    if not app:
        raise RuntimeError("Open the target Cursor workspace before reloading")
    with discovery_cleanup(app, project or workspace):
        reload_workspace_window(app, workspace)


def reload_workspace_window(app, workspace):
    helper_ready(app, workspace)
    helper_transport.reload(workspace, HELPER_REVISION)
    print("Confirmed:  Cursor helper reconnected after window reload.", flush=True)


def probe_terminal(
    app, workspace, interpreter, transaction, *, require_activation=True
):
    endpoint = helper_ready(app, workspace)
    return helper_transport.request(
        endpoint,
        workspace,
        "probe",
        interpreter=str(interpreter),
        project=str(interpreter.parent.parent.parent),
        requireActivation=require_activation,
        timeout=80,
    )


def verify_terminal(app, workspace, interpreter, transaction):
    data = probe_terminal(app, workspace, interpreter, transaction)
    print(
        f"Verified terminal environment: {data['venv']}; python: {data['python']}",
        flush=True,
    )


def clean(transaction):
    allowed = {
        "original.json",
        "applied.json",
        "state.json",
        "staged.json",
        "terminal.json",
        "probe.sh",
    }
    if any(
        p.name not in allowed or not p.is_file() or p.is_symlink()
        for p in transaction.iterdir()
    ):
        raise RuntimeError("Unexpected transaction contents; backup retained")
    for path in transaction.iterdir():
        path.unlink()
    transaction.rmdir()


def execute(action, workspace, interpreter):
    if action == "check-cursor-api":
        check_api()
        return
    if action in ("prepare-helper", "reinstall-helper", "select-environment"):
        app = app_info()
        if not app:
            raise RuntimeError(
                "Open the target Cursor workspace before using the helper"
            )
        endpoint = helper_ready(app, workspace, force=action == "reinstall-helper")
        if action == "select-environment":
            helper_transport.request(
                endpoint,
                workspace,
                "select",
                interpreter=str(interpreter),
                project=str(interpreter.parent.parent.parent),
            )
            print(f"Selected:    {interpreter} in Cursor (API read-back verified)")
        return
    if action == "reload-window":
        reload_window(workspace, interpreter.parent.parent.parent)
        return
    temporary = runtime_directory()
    transaction = temporary / "cursor-api-repair"
    if transaction.is_symlink():
        raise RuntimeError("Repair directory must not be a symlink")
    app = app_info()
    if not app:
        raise RuntimeError("Open the target Cursor workspace before repairing")
    product = Path(app["path"]) / "Contents/Resources/app/product.json"
    if action == "commit-cursor-api":
        state = json.loads((transaction / "state.json").read_text())
        if (
            state["product"] != str(product)
            or product.read_bytes() != (transaction / "applied.json").read_bytes()
        ):
            raise RuntimeError(
                "Cursor product.json changed before commit; backup retained"
            )
        clean(transaction)
        return
    if action == "rollback-cursor-api":
        external_process(app["pid"])
        state = json.loads((transaction / "state.json").read_text())
        if state["product"] != str(product):
            raise RuntimeError("Backup belongs to another Cursor installation")
        original = (transaction / "original.json").read_bytes()
        if product.read_bytes() != original:
            replace_guarded(
                product,
                (transaction / "applied.json").read_bytes(),
                original,
                transaction,
            )
        restart(app, workspace, interpreter.parent.parent.parent)
        clean(transaction)
        print("Cursor API repair rolled back and Cursor restarted.")
        return
    if transaction.exists():
        raise RuntimeError(
            f"Unfinished repair at {transaction}; use --rollback-cursor-api first"
        )
    if preflight(app) is False:
        return
    original = product.read_bytes()
    applied = patch_product(original)
    if applied == original:
        print(
            "Cursor already grants terminalDataWriteEvent; no patch or restart needed."
        )
        return
    external_process(app["pid"])
    transaction.mkdir(mode=0o700)
    (transaction / "original.json").write_bytes(original)
    (transaction / "applied.json").write_bytes(applied)
    (transaction / "state.json").write_text(json.dumps({"product": str(product)}))
    changed = False
    try:
        replace_guarded(product, original, applied, transaction)
        changed = True
        print("Cursor API grant patched; restarting Cursor...", flush=True)
        restarted = restart(app, workspace, interpreter.parent.parent.parent)
        verify_terminal(restarted, workspace, interpreter, transaction)
    except BaseException:
        try:
            if product.read_bytes() != original:
                replace_guarded(product, applied, original, transaction)
            if changed:
                restart(app, workspace, interpreter.parent.parent.parent)
            clean(transaction)
            print(
                "Cursor API repair failed; original configuration restored."
                + (" Cursor restarted." if changed else " No restart needed."),
                file=sys.stderr,
            )
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as rollback_error:
            print(
                f"Rollback incomplete; backup retained at {transaction}: {rollback_error}",
                file=sys.stderr,
            )
        raise
    if action == "repair-cursor-api-staged":
        print(
            "Verified:    Cursor API repair; backup retained until the workspace switch commits."
        )
        return
    clean(transaction)
    print(
        "Verified: a new Cursor terminal automatically activates the selected virtual environment. Backup removed."
    )


if __name__ == "__main__":
    try:
        execute(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        detail = (
            error.stderr
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        operation = (
            "window reload" if sys.argv[1] == "reload-window" else "API check/repair"
        )
        print(f"use-venv: Cursor {operation} failed: {detail}", file=sys.stderr)
        sys.exit(1)
CURSOR_API_PYTHON
}

requested_path="$PWD"
requested_workspace=""
requested_editor="vscode"
should_reload=false
repair_cursor_envs=false
reinstall_cursor_helper=false
cursor_api_action=""

while (($# > 0)); do
  case "$1" in
    -h | --help)
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
      (($# >= 2)) || fail "--workspace requires a directory"
      requested_workspace="$2"
      shift 2
      ;;
    --editor)
      (($# >= 2)) || fail "--editor requires vscode, cursor, or both"
      requested_editor="$2"
      case "$requested_editor" in
        vscode | cursor | both) ;;
        *) fail "--editor must be vscode, cursor, or both" ;;
      esac
      shift 2
      ;;
    --no-reload)
      should_reload=false
      shift
      ;;
    --reinstall-cursor-helper)
      reinstall_cursor_helper=true
      shift
      ;;
    --repair-cursor-envs)
      repair_cursor_envs=true
      shift
      ;;
    --repair-cursor-api | --rollback-cursor-api)
      [[ -z "$cursor_api_action" ]] || fail "choose only one Cursor API repair action"
      cursor_api_action="${1#--}"
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

if [[ "$reinstall_cursor_helper" == true ]]; then
  [[ "$requested_editor" != vscode ]] || fail "--reinstall-cursor-helper requires --editor cursor or both"
  [[ "$cursor_api_action" != rollback-cursor-api ]] || fail "run helper reinstall separately from rollback"
fi
if [[ "$repair_cursor_envs" == true && "$requested_editor" == "vscode" ]]; then
  fail "--repair-cursor-envs requires --editor cursor or --editor both"
fi
if [[ "$cursor_api_action" == "rollback-cursor-api" ]]; then
  [[ "$requested_editor" == "cursor" ]] || fail "Cursor API rollback requires --editor cursor"
  [[ "$repair_cursor_envs" == false && "$should_reload" == false ]] ||
    fail "run Cursor API rollback separately from package repair and --reload"
elif [[ "$cursor_api_action" == "repair-cursor-api" && "$requested_editor" == "vscode" ]]; then
  fail "Cursor API repair requires --editor cursor or --editor both"
fi

find_project_and_venv "$requested_path"
find_workspace "$requested_workspace"

case "$USE_VENV_PROJECT_DIRECTORY/" in
  "$USE_VENV_WORKSPACE_DIRECTORY/"*) ;;
  *) fail "project must be inside the selected workspace" ;;
esac

if [[ "$requested_editor" == cursor || "$requested_editor" == both ]]; then
  prepare_runtime_state
  runtime_state migrate "$USE_VENV_WORKSPACE_DIRECTORY" || exit 1
fi

if [[ "$cursor_api_action" == "rollback-cursor-api" ]]; then
  run_cursor_automation "$cursor_api_action" || exit 1
  exit 0
fi

if [[ "$requested_editor" == "cursor" || "$requested_editor" == "both" ]]; then
  [[ ! -e "$USE_VENV_STATE_DIRECTORY/cursor-api-repair" && ! -L "$USE_VENV_STATE_DIRECTORY/cursor-api-repair" ]] ||
    fail "unfinished Cursor API repair; run with --editor cursor --rollback-cursor-api first"
  check_cursor_requirements || exit 1
  configure_editor cursor
  if editor_process_state; then
    if [[ "$reinstall_cursor_helper" == true ]]; then
      run_cursor_automation reinstall-helper || exit 1
    else
      run_cursor_automation prepare-helper || exit 1
    fi
  elif [[ "$reinstall_cursor_helper" == true ]]; then
    fail "Open the target Cursor workspace before reinstalling its helper"
  fi
  if [[ "$repair_cursor_envs" == true ]]; then
    begin_cursor_repair_transaction
  fi
  ensure_cursor_environment_tools || exit 1
fi

begin_file_transaction
update_vscode_settings
capture_applied_file_transaction

if [[ -n "$USE_VENV_CURSOR_REPAIR_DIRECTORY" && -f "$USE_VENV_CURSOR_REPAIR_DIRECTORY/backup.json" ]]; then
  reload_cursor_after_package_change discovery || exit 1
fi

typeset -a editor_targets=("$requested_editor")
if [[ "$requested_editor" == "both" ]]; then
  editor_targets=(vscode cursor)
fi
for editor_target in "${editor_targets[@]}"; do
  configure_editor "$editor_target"
  USE_VENV_SELECTION_PENDING=false
  ensure_workspace_environment
  if [[ "$USE_VENV_SELECTION_PENDING" == true ]]; then
    [[ "$cursor_api_action" != repair-cursor-api || "$USE_VENV_CURSOR_API_REQUIRED" != true || "$editor_target" != cursor ]] ||
      fail "Cursor selection is pending; API repair cannot be verified"
    if [[ -n "$USE_VENV_CURSOR_REPAIR_DIRECTORY" && -f "$USE_VENV_CURSOR_REPAIR_DIRECTORY/backup.json" ]]; then
      fail "$USE_VENV_EDITOR_LABEL selection is pending; restoring the original extension until a switch can be verified"
    fi
    if [[ "$should_reload" == true ]]; then
      print "Skipped:     $USE_VENV_EDITOR_LABEL reload because its selection is pending."
    fi
  elif [[ "$should_reload" == true ]]; then
    if [[ "$editor_target" != "cursor" || "$USE_VENV_CURSOR_RELOADED" != true ]]; then
      reload_editor || exit 1
    else
      print "Skipped:     Cursor was already reloaded after replacing its extension."
    fi
  else
    print "$USE_VENV_EDITOR_LABEL reload is unnecessary; Python Environments observes these settings live."
  fi
done

if [[ "$cursor_api_action" == repair-cursor-api && "$USE_VENV_CURSOR_API_REQUIRED" == true ]]; then
  USE_VENV_CURSOR_API_ACTIVE=true
  run_cursor_automation repair-cursor-api-staged || exit 1
fi
if [[ "$repair_cursor_envs" == true || "$cursor_api_action" == repair-cursor-api ]]; then
  check_cursor_requirements verify || exit 1
fi
if [[ "$USE_VENV_CURSOR_API_ACTIVE" == true ]]; then
  if [[ -d "$USE_VENV_STATE_DIRECTORY/cursor-api-repair" ]]; then
    run_cursor_automation commit-cursor-api || exit 1
  fi
  USE_VENV_CURSOR_API_ACTIVE=false
fi
commit_file_transaction
USE_VENV_CURSOR_REPAIR_COMMITTED=true
