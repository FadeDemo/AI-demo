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
                [--reload]
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
  if ensure_cursor_environment_tools check; then
    return 0
  fi
  if [[ "${1:-}" != verify && "$repair_cursor_envs" == true ]]; then
    print -ru2 -- "use-venv: Cursor environment package repair is authorized; it has not started."
    return 0
  fi
  print -ru2 -- "use-venv: Stopped before repairs; rerun with --repair-cursor-envs to allow environment package repair."
  return 1
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
  python3 - "$1" "$USE_VENV_WORKSPACE_DIRECTORY" "$USE_VENV_DIRECTORY/bin/python" <<'CURSOR_AUTOMATION_PYTHON'
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


def execute(action, workspace, interpreter):
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
    raise RuntimeError(f"Unsupported helper action: {action}")


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
            "window reload" if sys.argv[1] == "reload-window" else "helper operation"
        )
        print(f"use-venv: Cursor {operation} failed: {detail}", file=sys.stderr)
        sys.exit(1)
CURSOR_AUTOMATION_PYTHON
}

requested_path="$PWD"
requested_workspace=""
requested_editor="vscode"
should_reload=false
repair_cursor_envs=false
reinstall_cursor_helper=false

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
fi
if [[ "$repair_cursor_envs" == true && "$requested_editor" == "vscode" ]]; then
  fail "--repair-cursor-envs requires --editor cursor or --editor both"
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


if [[ "$requested_editor" == "cursor" || "$requested_editor" == "both" ]]; then
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

if [[ "$repair_cursor_envs" == true ]]; then
  check_cursor_requirements verify || exit 1
fi
commit_file_transaction
USE_VENV_CURSOR_REPAIR_COMMITTED=true
