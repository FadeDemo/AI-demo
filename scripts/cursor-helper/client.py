"""Private, authenticated local transport; no UI automation or proxy routing."""

import http.client
import json
import os
import time
from pathlib import Path


class HelperUnavailable(RuntimeError):
    pass


def endpoint_root():
    return Path.home() / "Library/Application Support/use-venv/helper"


def request(endpoint, workspace, action, timeout=55, **parameters):
    connection = http.client.HTTPConnection(
        "127.0.0.1", endpoint["port"], timeout=timeout
    )
    try:
        connection.request(
            "POST",
            "/",
            json.dumps(
                {"workspace": str(workspace.resolve()), "action": action, **parameters}
            ),
            {
                "Authorization": "Bearer " + endpoint["token"],
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        data = json.loads(response.read(65536))
        if response.status != 200:
            if data.get("reloading"):
                wait(workspace, exclude=endpoint["session"])
            raise RuntimeError(data.get("error", "Helper request failed"))
        return data["result"]
    finally:
        connection.close()


def find(workspace, revision=None, exclude=None):
    matches = []
    root = endpoint_root()
    if root.is_symlink():
        raise RuntimeError("Helper state directory must not be a symlink")
    for path in root.glob("*.json"):
        if (
            path.is_symlink()
            or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o077
        ):
            continue
        try:
            endpoint = json.loads(path.read_text())
            if endpoint.get("session") == exclude:
                continue
            result = request(endpoint, workspace, "ping", timeout=0.5)
            if revision is None or result.get("revision") == revision:
                matches.append(endpoint)
        except (OSError, ValueError, KeyError, RuntimeError, http.client.HTTPException):
            continue
    if len(matches) > 1:
        raise RuntimeError(
            "Multiple Cursor windows have this workspace open; close the duplicate window"
        )
    if not matches:
        raise HelperUnavailable(
            "No responding use-venv helper for the target workspace"
        )
    return matches[0]


def wait(workspace, revision=None, exclude=None, timeout=40):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return find(workspace, revision, exclude)
        except HelperUnavailable:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.3)


def reload(workspace, revision=None):
    endpoint = find(workspace)
    request(endpoint, workspace, "reload", timeout=5)
    return wait(workspace, revision, exclude=endpoint["session"])
