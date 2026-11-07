import base64
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer

import app
from companion import Companion, FeatureError, MAX_FILE
from relay_server import Broker, RelayHandler


class QuietHandler(app.RemoteHandler):
    def log_message(self, *args):
        pass


class QuietRelay(RelayHandler):
    def log_message(self, *args):
        pass


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner = Mock()
        self.features = Companion({"share_dir": self.temp.name}, self.runner)

    def call(self, action, **args):
        return self.features.dispatch({"action": action, **args})

    def test_binary_round_trip_and_no_overwrite(self):
        data = bytes(range(256)) * 10
        payload = base64.b64encode(data).decode()
        self.call("files.put", name="test.bin", data=payload)
        result = self.call("files.get", name="test.bin")
        self.assertEqual(base64.b64decode(result["data"]), data)
        with self.assertRaises(FeatureError) as raised:
            self.call("files.put", name="test.bin", data="")
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(self.call("files.list")["files"][0]["size"], len(data))

    def test_paths_rejected(self):
        for name in ("../secret", "..\\secret", "C:\\file", "x:secret", "CON", "nul.txt", "file.", " file", "", "a\x00b", "a/b"):
            with self.subTest(name=name), self.assertRaises(FeatureError):
                self.call("files.get", name=name)

    def test_symlink_not_shared(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "private.txt"
            target.write_text("private")
            link = Path(self.temp.name) / "link.txt"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            self.assertEqual(self.call("files.list")["files"], [])
            with self.assertRaises(FeatureError):
                self.call("files.get", name="link.txt")

    def test_size_and_encoding_limits(self):
        with self.assertRaises(FeatureError):
            self.call("files.put", name="invalid.bin", data="!!!")
        with self.assertRaises(FeatureError):
            self.call("files.put", name="large.bin", data="a" * ((MAX_FILE + 2) // 3 * 4 + 1))
        with self.assertRaises(FeatureError):
            self.call("note.set", text="x" * 65537)

    def test_shared_text_persists_and_pc_edits_are_visible(self):
        self.call("note.set", text="Hello \u65e5\u672c\u8a9e")
        second = Companion({"share_dir": self.temp.name})
        self.assertEqual(second.dispatch({"action": "note.get"})["text"], "Hello \u65e5\u672c\u8a9e")
        (Path(self.temp.name) / "shared-note.txt").write_text("From PC", "utf-8")
        self.assertEqual(self.call("note.get")["text"], "From PC")

    def test_invalid_actions_and_types(self):
        for payload in ([], None, {}, {"action": []}, {"action": "shell"}, {"action": "command", "command": []}):
            with self.subTest(payload=payload), self.assertRaises(FeatureError):
                self.features.dispatch(payload)
        self.runner.assert_not_called()

    def test_commands_are_allowlisted(self):
        self.call("command", command="lock")
        self.runner.assert_called_once_with("lock")
        with self.assertRaises(FeatureError):
            self.call("command", command="unlock")

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_timer_validation_and_cancellation_use_fixed_arguments(self):
        with patch("companion.subprocess.run", return_value=Mock(returncode=0)) as run:
            for minutes in (0, 181, True, "10"):
                with self.assertRaises(FeatureError):
                    self.call("timer.set", minutes=minutes)
            run.assert_not_called()
            self.call("timer.set", minutes=30)
            self.assertEqual(run.call_args.args[0], ["shutdown.exe", "/s", "/t", "1800"])
            self.call("timer.cancel")
            self.assertEqual(run.call_args.args[0], ["shutdown.exe", "/a"])

    def test_wol_magic_packet_and_validation(self):
        with self.assertRaises(FeatureError):
            self.call("wol.wake", mac="invalid-mac")
        with patch("companion.socket.socket") as sock_cls:
            sock = sock_cls.return_value.__enter__.return_value
            res = self.call("wol.wake", mac="AA:BB:CC:DD:EE:FF")
            self.assertTrue(res["sent"])
            packet = sock.sendto.call_args.args[0]
            self.assertEqual(len(packet), 6 + 16 * 6)
            self.assertTrue(packet.startswith(b"\xff" * 6))

    def test_unlock_actions_validation_and_ipc_forwarding(self):
        with self.assertRaises(FeatureError):
            self.call("unlock.enroll", enroll_token="")
        with self.assertRaises(FeatureError):
            self.call("unlock.submit", challenge_id="only-one-field")
        with patch("companion.pipe_transact", return_value={"ok": True, "enrolled": True, "device_id": "dev-1", "qualified_user": "PC\\User"}) as mock_pipe:
            st = self.call("unlock.status")
            self.assertTrue(st["available"])
            self.assertTrue(st["enrolled"])
            self.assertEqual(st["device_id"], "dev-1")
            mock_pipe.assert_called()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        app.SESSIONS.clear()
        app.LOGIN_FAILURES.clear()
        self.server = self.serve(QuietHandler)
        self.server.pin = "test-access"
        self.server.companion = Companion({"share_dir": self.temp.name}, Mock())

    def serve(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, path, body=None, cookie=None, server=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", (server or self.server).server_port, timeout=5)
        headers = dict(headers or {})
        if cookie:
            headers["Cookie"] = cookie
        if isinstance(body, dict):
            body = json.dumps(body)
            headers["Content-Type"] = "application/json"
        try:
            connection.request("GET" if body is None else "POST", path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def login(self, server=None):
        status, headers, _ = self.request("/login", "pin=test-access", server=server)
        self.assertEqual(status, 303)
        return headers["Set-Cookie"].split(";")[0]

    def test_authentication_required_for_every_feature(self):
        for action in ("status", "files.list", "files.get", "files.put", "note.get", "note.set", "media", "command", "timer.set"):
            self.assertEqual(self.request("/api/v2", {"action": action})[0], 401)
        self.assertEqual(self.request("/login", "pin=wrong")[0], 403)
        self.assertEqual(self.request("/api/v2", {"action": "files.list"}, self.login())[0], 200)

    def test_pairing_rejects_remote_host_header(self):
        self.assertEqual(self.request("/pair", headers={"Host": "external.invalid"})[0], 403)

    def test_pairing_local_and_share_authenticated(self):
        self.assertEqual(self.request("/pair")[0], 200)
        _, _, page = self.request("/share", cookie=self.login())
        self.assertIn(b"Shared text", page)

    def test_bad_json_and_oversized_request(self):
        cookie = self.login()
        for body in ("[]", "{", '{"action":[]}'):
            self.assertEqual(self.request("/api/v2", body, cookie)[0], 400)
        self.assertEqual(self.request("/api/v2", "", cookie, headers={"Content-Length": "999999999"})[0], 413)

    def test_rate_limit_and_expired_session(self):
        for _ in range(10):
            self.assertEqual(self.request("/login", "pin=wrong")[0], 403)
        self.assertEqual(self.request("/login", "pin=wrong")[0], 429)
        app.LOGIN_FAILURES.clear()
        cookie = self.login()
        app.SESSIONS[cookie.split("=", 1)[1]] = 0
        self.assertEqual(self.request("/api/v2", {"action": "files.list"}, cookie)[0], 401)

    def test_relay_round_trip_with_real_http_agent(self):
        relay = self.serve(QuietRelay)
        relay.pin = "test-access"
        relay.agent_token = "test-agent-token-for-integration"
        relay.broker = Broker(timeout=3)
        cookie = self.login(relay)
        self.assertEqual(self.request("/agent/poll?token=" + relay.agent_token, server=relay)[0], 401)
        agent_headers = {"X-Agent-Token": relay.agent_token}
        failures = []
        def agent():
            try:
                for _ in range(2):
                    status, _, body = self.request("/agent/poll", server=relay, headers=agent_headers)
                    self.assertEqual(status, 200)
                    job = json.loads(body)["command"]
                    data = self.server.companion.dispatch(job["payload"])
                    status, _, _ = self.request("/agent/result", {"id": job["id"], "ok": True, "data": data}, server=relay, headers=agent_headers)
                    self.assertEqual(status, 200)
            except Exception as exc:
                failures.append(exc)
        thread = threading.Thread(target=agent)
        thread.start()
        encoded = base64.b64encode(b"remote transfer").decode()
        self.assertEqual(self.request("/api/v2", {"action": "files.put", "name": "remote.txt", "data": encoded}, cookie, relay)[0], 200)
        status, _, body = self.request("/api/v2", {"action": "files.get", "name": "remote.txt"}, cookie, relay)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, failures)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["data"], encoded)
        self.assertEqual(relay.broker.pending, {})

    def test_offline_relay_drops_unclaimed_commands(self):
        broker = Broker(timeout=0.03)
        with self.assertRaises(FeatureError) as raised:
            broker.submit({"action": "command", "command": "restart"})
        self.assertEqual(raised.exception.status, 504)
        self.assertIsNone(broker.poll(timeout=0.01))
        self.assertEqual(broker.pending, {})


if __name__ == "__main__":
    unittest.main()
