import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from agent_orchestrator import browser_open, dashboard


class BrowserOpenTests(unittest.TestCase):
    def request(self, peer="127.0.0.1", server="127.0.0.1", headers=()):
        return Request({"type": "http", "client": (peer, 1234) if peer else None,
                        "server": (server, 7860), "headers": headers})

    def test_only_direct_same_mac_connections_are_available(self):
        with patch.object(browser_open.sys, "platform", "darwin"):
            for peer, server, expected in [
                ("127.0.0.1", "127.0.0.1", True), ("::1", "::1", True),
                ("::ffff:127.0.0.1", "127.0.0.1", True),
                ("192.168.10.5", "192.168.10.5", True),
                ("192.168.10.6", "192.168.10.5", False),
                ("192.168.10.6", "0.0.0.0", False),
                ("203.0.113.3", "127.0.0.1", False),
                ("testclient", "localhost", False), (None, "127.0.0.1", False),
            ]:
                with self.subTest(peer=peer, server=server):
                    self.assertEqual(browser_open.system_browser_available(self.request(peer, server)), expected)
            for header in [b"forwarded", b"x-forwarded-for", b"x-forwarded-host", b"x-forwarded-proto"]:
                self.assertFalse(browser_open.system_browser_available(self.request(headers=[(header, b"127.0.0.1")])))
        with patch.object(browser_open.sys, "platform", "linux"):
            self.assertFalse(browser_open.system_browser_available(self.request()))

    def test_web_urls_preserve_queries_and_reject_other_targets(self):
        url = "https://example.invalid/authorize?redirect_uri=http%3A%2F%2Flocalhost%3A1234%2Fcallback&state=a_b-c#fragment"
        self.assertEqual(browser_open.validate_web_url(url), url)
        for value in [None, [], {}, "", "-a", "file:///tmp/x", "javascript:alert(1)",
                      "https://", "https://u:p@example.com", "https://example.com:bad", "https://[bad",
                      "https://example.com/\nsecret", "https://example.com/ a", "https://example.com\\x", "https://example.com/" + "x" * 16384]:
            with self.subTest(value=str(value)[:50]), self.assertRaises(HTTPException):
                browser_open.validate_web_url(value)

    def test_native_open_uses_argument_array_without_profile_or_shell(self):
        url = "https://example.invalid/?a=1&b=$(not-a-command)"
        with patch.object(browser_open.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            browser_open.open_system_browser(url)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/open", url])
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_native_open_failures_are_reported_without_leaking_url(self):
        for outcome, code in [(OSError("sensitive-url"), 503),
                              (subprocess.TimeoutExpired("sensitive-url", 5), 504),
                              (subprocess.CompletedProcess([], 1), 502)]:
            with self.subTest(code=code), patch.object(browser_open.subprocess, "run") as run:
                if isinstance(outcome, Exception):
                    run.side_effect = outcome
                else:
                    run.return_value = outcome
                with self.assertRaises(HTTPException) as caught:
                    browser_open.open_system_browser("https://example.invalid/?secret=fixture")
                self.assertEqual(caught.exception.status_code, code)
                self.assertNotIn("sensitive", caught.exception.detail)

    def test_route_checks_auth_locality_intent_json_origin_and_url(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "ORCH_DASHBOARD_CONFIG": "/nonexistent/browser-open-config.json",
            "ORCH_ACTIVE_SNAPSHOT_AUTOSAVE": "0",
        }), patch.object(browser_open.sys, "platform", "darwin"):
            app = dashboard.create_app(Path(directory), token="fixture", ttyd_enabled=False, remote_nodes_enabled=False)
            with TestClient(app, client=("127.0.0.1", 1234)) as client, patch.object(dashboard, "open_system_browser") as opened:
                headers = {"Authorization": "Bearer fixture", "X-SiLing-Browser-Open": "user-click"}
                url = "https://example.invalid/?state=full-query&code_challenge=fixture"
                self.assertEqual(client.post("/api/browser/open", json={"url": url}).status_code, 401)
                self.assertTrue(client.get("/api/config", headers=headers).json()["system_browser_available"])
                for body in [{}, [], {"url": "file:///tmp/x"}]:
                    self.assertEqual(client.post("/api/browser/open", json=body, headers=headers).status_code, 400)
                self.assertEqual(client.post("/api/browser/open", json={"url": url}, headers={"Authorization": "Bearer fixture"}).status_code, 403)
                self.assertEqual(client.post("/api/browser/open", content="{}", headers=headers).status_code, 415)
                self.assertEqual(client.post("/api/browser/open", content="{", headers={**headers, "Content-Type": "application/json"}).status_code, 400)
                for extra in [{"Origin": "https://evil.invalid"}, {"Sec-Fetch-Site": "cross-site"}, {"X-Forwarded-For": "127.0.0.1"}]:
                    self.assertEqual(client.post("/api/browser/open", json={"url": url}, headers={**headers, **extra}).status_code, 403)
                opened.assert_not_called()
                self.assertEqual(client.post("/api/browser/open", json={"url": url}, headers={**headers, "Origin": "http://testserver"}).status_code, 200)
                opened.assert_called_once_with(url)
                opened.reset_mock()
                with patch.object(dashboard, "system_browser_available", return_value=False):
                    self.assertFalse(client.get("/api/config", headers=headers).json()["system_browser_available"])
                    self.assertEqual(client.post("/api/browser/open", json={"url": url}, headers=headers).status_code, 403)
                opened.assert_not_called()

    def test_same_mac_lan_address_works_but_phone_and_spoofed_host_do_not(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "ORCH_DASHBOARD_CONFIG": "/nonexistent/browser-open-config.json",
            "ORCH_ACTIVE_SNAPSHOT_AUTOSAVE": "0",
        }), patch.object(browser_open.sys, "platform", "darwin"):
            app = dashboard.create_app(Path(directory), token="fixture", ttyd_enabled=False, remote_nodes_enabled=False)
            for peer, expected in [("192.168.10.5", 200), ("192.168.10.6", 403)]:
                with self.subTest(peer=peer), TestClient(app, client=(peer, 1234), base_url="http://192.168.10.5:7860") as client, patch.object(dashboard, "open_system_browser") as opened:
                    headers = {"Authorization": "Bearer fixture", "X-SiLing-Browser-Open": "user-click", "Host": peer}
                    config = client.get("/api/config", headers=headers)
                    self.assertEqual(config.json()["system_browser_available"], expected == 200)
                    self.assertEqual(config.headers["cache-control"], "no-store")
                    result = client.post("/api/browser/open", json={"url": "https://example.invalid/"}, headers=headers)
                    self.assertEqual(result.status_code, expected)
                    self.assertEqual(opened.call_count, int(expected == 200))


if __name__ == "__main__":
    unittest.main()
