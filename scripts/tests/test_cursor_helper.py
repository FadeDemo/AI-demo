import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "helper_client", ROOT / "scripts/cursor-helper/client.py"
)
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


class HelperTransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            dir=ROOT / ".agent-tmp", prefix="helper-client-tests-"
        )
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.patch = mock.patch.object(CLIENT, "endpoint_root", return_value=self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def endpoint(self, name):
        path = self.root / (name + ".json")
        path.write_text(
            json.dumps({"session": name, "port": 1234, "token": "test-only"})
        )
        path.chmod(0o600)

    def test_dead_endpoint_is_ignored_and_live_workspace_is_verified(self):
        self.endpoint("dead")
        self.endpoint("live")

        def ping(endpoint, workspace, action, **kwargs):
            self.assertEqual((workspace, action), (ROOT, "ping"))
            if endpoint["session"] == "dead":
                raise ConnectionRefusedError()
            return {"revision": "current"}

        with mock.patch.object(CLIENT, "request", side_effect=ping):
            self.assertEqual(CLIENT.find(ROOT, "current")["session"], "live")

    def test_duplicate_workspace_is_rejected(self):
        self.endpoint("one")
        self.endpoint("two")
        with (
            mock.patch.object(CLIENT, "request", return_value={}),
            self.assertRaisesRegex(RuntimeError, "Multiple Cursor"),
        ):
            CLIENT.find(ROOT)

    def test_reload_excludes_old_session(self):
        with (
            mock.patch.object(CLIENT, "find", return_value={"session": "old"}),
            mock.patch.object(CLIENT, "request") as request,
            mock.patch.object(CLIENT, "wait") as wait,
        ):
            CLIENT.reload(ROOT, "new-revision")
        self.assertEqual(request.call_args.args[2], "reload")
        wait.assert_called_once_with(ROOT, "new-revision", exclude="old")

    def test_wait_has_bounded_deadline(self):
        with (
            mock.patch.object(
                CLIENT, "find", side_effect=CLIENT.HelperUnavailable("offline")
            ),
            mock.patch.object(CLIENT.time, "monotonic", side_effect=[0, 41]),
            self.assertRaises(CLIENT.HelperUnavailable),
        ):
            CLIENT.wait(ROOT)

    def test_world_readable_token_is_ignored(self):
        self.endpoint("public")
        (self.root / "public.json").chmod(0o644)
        with (
            mock.patch.object(CLIENT, "request") as request,
            self.assertRaises(CLIENT.HelperUnavailable),
        ):
            CLIENT.find(ROOT)
        request.assert_not_called()


class EmbeddedHelperTests(unittest.TestCase):
    def test_standalone_payload_matches_sources(self):
        spec = importlib.util.spec_from_file_location(
            "helper_build", ROOT / "scripts/cursor-helper/build.py"
        )
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        source = (ROOT / "scripts/use-venv.zsh").read_text()
        encoded = source.split('HELPER_ARCHIVE_B64 = "', 1)[1].split('"', 1)[0]
        self.assertEqual(base64.b64decode(encoded), build.payload())
