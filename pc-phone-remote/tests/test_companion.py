import base64
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch
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

    def test_pin_rotation_revokes_old_pin_aliases_and_sessions(self):
        path = Path(self.temp.name) / "config.json"
        self.server.config_path = path
        path.write_text(json.dumps({"pin": "test-access", "allowed_pins": ["legacy-access"]}), "utf-8")
        cookie = self.login()
        status, _, _ = self.request("/api/local/admin", {"action": "save_config", "pin": "replacement-access", "share_dir": self.temp.name}, headers={"X-Local-Admin": app.LOCAL_ADMIN_TOKEN})
        self.assertEqual(status, 200)
        self.assertNotIn("allowed_pins", json.loads(path.read_text("utf-8")))
        for pin in ("test-access", "legacy-access"):
            self.assertEqual(self.request("/login", "pin=" + pin)[0], 403)
        self.assertEqual(self.request("/login", "pin=replacement-access")[0], 303)
        self.assertEqual(self.request("/api/v2", {"action": "files.list"}, cookie)[0], 401)

    def test_config_pin_reload_replaces_runtime_pin(self):
        path = Path(self.temp.name) / "config.json"
        self.server.config_path = path
        path.write_text(json.dumps({"pin": "file-access", "allowed_pins": ["legacy-access"]}), "utf-8")
        self.assertEqual(self.request("/login", "pin=test-access")[0], 403)
        self.assertEqual(self.request("/login", "pin=legacy-access")[0], 403)
        self.assertEqual(self.request("/login", "pin=file-access")[0], 303)

    def test_discover_and_ios_pwa_routes(self):
        status, _, body = self.request("/api/discover")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "pc-phone-remote")

        cookie = self.login()
        status, _, app_html = self.request("/app", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"apple-mobile-web-app-capable", app_html)
        self.assertIn(b"appShell", app_html)

        status, _, manifest = self.request("/manifest.json")
        self.assertEqual(status, 200)
        manifest_obj = json.loads(manifest.decode("utf-8"))
        self.assertEqual(manifest_obj["start_url"], "/app")

        status, _, sw_js = self.request("/sw.js")
        self.assertEqual(status, 200)
        self.assertIn(b"self.addEventListener", sw_js)

        status, _, icon_png = self.request("/apple-touch-icon.png")
        self.assertEqual(status, 200)
        self.assertTrue(icon_png.startswith(b"\x89PNG"))

    def test_desktop_ui_qr_and_local_admin_api(self):
        self.server.config_path = Path(self.temp.name) / "config.json"

        status, _, desk_html = self.request("/desktop")
        self.assertEqual(status, 200)
        self.assertIn(b"PC Phone Remote", desk_html)
        self.assertIn(app.LOCAL_ADMIN_TOKEN.encode("utf-8"), desk_html)

        status, hdrs, qr_png = self.request("/api/local/qr?data=pcphone://add?host=127.0.0.1")
        self.assertEqual(status, 200)
        self.assertEqual(hdrs.get("Content-Type"), "image/png")
        self.assertTrue(qr_png.startswith(b"\x89PNG"))

        status, _, admin_raw = self.request("/api/local/admin")
        self.assertEqual(status, 200)
        admin_data = json.loads(admin_raw.decode("utf-8"))
        self.assertTrue(admin_data["ok"])
        self.assertEqual(admin_data["pin"], "test-access")
        self.assertIsInstance(admin_data["ips"], list)
        self.assertIn("telemetry", admin_data)

        # POST without X-Local-Admin token must fail with 403
        status, _, _ = self.request("/api/local/admin", {"action": "save_config", "pin": "111222"})
        self.assertEqual(status, 403)

        # Non-loopback Host header must fail with 403
        status, _, _ = self.request("/desktop", headers={"Host": "evil.example:8765"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("/api/local/admin", headers={"Host": "192.168.1.10:8765"})
        self.assertEqual(status, 403)

        # Valid POST with X-Local-Admin updates server.pin and temp config.json
        status, _, save_resp = self.request(
            "/api/local/admin",
            {"action": "save_config", "pin": "987654", "share_dir": self.temp.name},
            headers={"X-Local-Admin": app.LOCAL_ADMIN_TOKEN},
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(save_resp.decode("utf-8"))["ok"])
        self.assertEqual(self.server.pin, "987654")
        saved_cfg = json.loads((Path(self.temp.name) / "config.json").read_text("utf-8"))
        self.assertEqual(saved_cfg["pin"], "987654")


class LinuxSupportTests(unittest.TestCase):
    def test_linux_media_power_touchpad_and_timer_dispatch(self):
        import linux_support

        def fake_which(cmd):
            available = {"playerctl", "xdotool", "pactl", "systemctl", "shutdown", "loginctl"}
            return f"/usr/bin/{cmd}" if cmd in available else None

        with (
            patch("linux_support.shutil.which", side_effect=fake_which),
            patch("linux_support.subprocess.run", return_value=Mock(returncode=0, stdout="", stderr="")) as run_mock,
            patch("linux_support.subprocess.Popen"),
        ):
            self.assertEqual(linux_support.linux_send_media("play_pause"), {"sent": True})
            run_mock.assert_any_call(
                ["playerctl", "play-pause"],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
            )

            res = linux_support.linux_handle_touchpad({"type": "move", "dx": 12, "dy": -8})
            self.assertEqual(res, {"sent": True})
            run_mock.assert_any_call(
                ["xdotool", "mousemove_relative", "--", "12", "-8"],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
            )

            self.assertEqual(linux_support.linux_schedule_shutdown(15), {"scheduled": True, "minutes": 15})
            self.assertEqual(linux_support.linux_schedule_shutdown(None), {"scheduled": False, "minutes": None})
            self.assertIsNone(linux_support.linux_run_power_command("lock"))
            self.assertIsNone(linux_support.linux_run_power_command("sleep"))


class ProFeaturesTests(unittest.TestCase):
    def test_keyboard_and_hotkey_validation(self):
        comp = Companion({"pin": "1234", "share_dir": tempfile.mkdtemp(prefix="pcr-key-")})
        with patch.object(Companion, "session_locked", return_value=False):
            with self.assertRaises(FeatureError) as bad_hk:
                comp.dispatch({"action": "keyboard.hotkey", "hotkey": "rm_rf"})
            self.assertEqual(bad_hk.exception.status, 400)

            with self.assertRaises(FeatureError) as empty_txt:
                comp.dispatch({"action": "keyboard.type", "text": ""})
            self.assertEqual(empty_txt.exception.status, 400)

            with patch("companion.type_unicode_text", return_value={"sent": True, "length": 6}) as m_type:
                res = comp.dispatch({"action": "keyboard.type", "text": "Привет"})
                self.assertEqual(res, {"sent": True, "length": 6})
                m_type.assert_called_once()

            with patch("companion.send_hotkey", return_value={"sent": True, "hotkey": "alt_tab"}) as m_hk:
                res = comp.dispatch({"action": "keyboard.hotkey", "hotkey": "alt_tab"})
                self.assertEqual(res, {"sent": True, "hotkey": "alt_tab"})
                m_hk.assert_called_once()

        with patch.object(Companion, "session_locked", return_value=True):
            with self.assertRaises(FeatureError) as locked_exc:
                comp.dispatch({"action": "screen.capture"})
            self.assertEqual(locked_exc.exception.status, 409)

    def test_clipboard_audio_display_and_screen_dispatch(self):
        comp = Companion({"pin": "1234", "share_dir": tempfile.mkdtemp(prefix="pcr-pro-")})
        with patch.object(Companion, "session_locked", return_value=False):
            with patch("companion.get_clipboard_text", return_value="hello clip"):
                self.assertEqual(comp.dispatch({"action": "clipboard.get"}), {"text": "hello clip"})
            with patch("companion.set_clipboard_text", return_value={"saved": True, "length": 3}) as m_set:
                self.assertEqual(comp.dispatch({"action": "clipboard.set", "text": "abc"}), {"saved": True, "length": 3})
                m_set.assert_called_once_with("abc")

            with patch("companion.capture_screen_jpeg", return_value=(b"\xff\xd8jpg", 640, 360, [{"id": 0, "name": "Monitor 1", "width": 1920, "height": 1080}])):
                cap = comp.dispatch({"action": "screen.capture", "monitor": 0})
                self.assertEqual(cap["mime"], "image/jpeg")
                self.assertEqual(cap["width"], 640)
                self.assertEqual(base64.b64decode(cap["image_b64"]), b"\xff\xd8jpg")

            with patch("companion.tap_screen", return_value={"sent": True, "x": 100, "y": 200, "button": "left", "monitor": 0}) as m_tap:
                res = comp.dispatch({"action": "screen.tap", "nx": 0.25, "ny": 0.5, "monitor": 0, "button": "left"})
                self.assertTrue(res["sent"])
                m_tap.assert_called_once()

            with patch("companion.list_audio_state", return_value={"devices": [{"id": "d1", "name": "Headset", "active": True}], "sessions": []}):
                self.assertEqual(comp.dispatch({"action": "audio.list"})["devices"][0]["id"], "d1")
            with patch("companion.set_audio_output", return_value={"switched": True, "device_id": "d1"}):
                self.assertTrue(comp.dispatch({"action": "audio.set_output", "device_id": "d1"})["switched"])
            with patch("companion.set_app_audio_volume", return_value={"updated": True, "pid": 4321, "volume": 50, "muted": False}):
                self.assertEqual(comp.dispatch({"action": "audio.set_app_volume", "pid": 4321, "volume": 50})["volume"], 50)

            with patch("companion.get_display_brightness", return_value={"supported": True, "brightness": 75, "method": "ddc"}):
                self.assertEqual(comp.dispatch({"action": "display.status"})["brightness"], 75)
            with patch("companion.set_display_brightness", return_value={"updated": True, "brightness": 60}):
                self.assertEqual(comp.dispatch({"action": "display.brightness", "brightness": 60})["brightness"], 60)
            with patch("companion.turn_display_off", return_value={"sent": True, "display_off": True}):
                self.assertTrue(comp.dispatch({"action": "display.off"})["display_off"])

    def test_protected_process_kill_and_custom_buttons(self):
        import pro_features
        for pid in (0, 4, os.getpid()):
            with self.assertRaises(ValueError):
                pro_features.kill_process_safe(pid)

        fake_proc = Mock()
        fake_proc.name.return_value = "csrss.exe"
        with patch("pro_features.psutil.Process", return_value=fake_proc):
            with self.assertRaises(PermissionError):
                pro_features.kill_process_safe(12345)

        buttons = pro_features.sanitize_custom_buttons([
            {"id": "b1", "label": "Good", "icon": "🌐", "kind": "url", "target": "https://example.com"},
            {"id": "bad_js", "label": "Bad", "icon": "!", "kind": "url", "target": "javascript:alert(1)"},
            {"id": "bad_hk", "label": "BadHK", "icon": "!", "kind": "hotkey", "target": "unknown_combo"},
        ])
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0]["id"], "b1")

        comp = Companion({"pin": "1234", "share_dir": tempfile.mkdtemp(prefix="pcr-cb-"), "custom_buttons": buttons})
        with patch.object(Companion, "session_locked", return_value=False):
            listed = comp.dispatch({"action": "deck.custom_list"})
            self.assertEqual(len(listed["buttons"]), 1)
            with patch("companion.run_custom_button", return_value={"sent": True, "id": "b1"}) as m_run:
                ran = comp.dispatch({"action": "deck.custom_run", "id": "b1"})
                self.assertTrue(ran["sent"])
                m_run.assert_called_once()

    def test_tls_san_builder_wol_diag_and_updates(self):
        import tls_helper, pro_features
        sans = tls_helper._build_san_entries(["192.168.1.50", "not-an-ip", "127.0.0.1"])
        self.assertEqual(sans, ["DNS:localhost", "IP:127.0.0.1", "IP:192.168.1.50"])

        fake_resp = Mock()
        fake_resp.read.return_value = json.dumps({
            "tag_name": "v2.9.0",
            "html_url": "https://github.com/kznkutsubyo/remote-pc-control/releases/tag/v2.9.0",
            "assets": [{"name": "PCPhoneRemote-Setup.exe", "browser_download_url": "https://example.com/setup.exe"}],
            "body": "Notes",
        }).encode("utf-8")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_resp
        with patch("pro_features.urllib.request.urlopen", return_value=fake_cm):
            upd = pro_features.check_github_updates(current_version="2.4.0")
            self.assertTrue(upd["ok"])
            self.assertTrue(upd["update_available"])
            self.assertEqual(upd["latest_version"], "2.9.0")


class ProHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.server.pin = "test-access"
        self.server.https_enabled = False
        self.server.config_path = Path(self.temp.name) / "config.json"
        self.server.companion = Companion({"pin": "test-access", "share_dir": self.temp.name})
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_screen_mjpg_auth_and_admin_pro_fields(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        conn.request("GET", "/api/screen.mjpg")
        r = conn.getresponse()
        r.read()
        self.assertEqual(r.status, 401)
        conn.close()

        conn2 = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        conn2.request("GET", "/api/local/admin")
        r2 = conn2.getresponse()
        admin_data = json.loads(r2.read().decode("utf-8"))
        self.assertEqual(r2.status, 200)
        self.assertEqual(admin_data["app_version"], "2.4.0")
        self.assertIn("custom_buttons", admin_data)
        self.assertIn("tls", admin_data)
        conn2.close()

        conn3 = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        body = json.dumps({"action": "custom_buttons_save", "buttons": [{"id": "yt", "label": "YouTube", "icon": "▶", "kind": "url", "target": "https://youtube.com"}]}).encode("utf-8")
        conn3.request("POST", "/api/local/admin", body, {"Content-Type": "application/json", "X-Local-Admin": app.LOCAL_ADMIN_TOKEN})
        r3 = conn3.getresponse()
        resp3 = json.loads(r3.read().decode("utf-8"))
        self.assertEqual(r3.status, 200)
        self.assertEqual(len(resp3["buttons"]), 1)
        conn3.close()


if __name__ == "__main__":
    unittest.main()
