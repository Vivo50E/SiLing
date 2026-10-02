"""Release safety checks without network access or GitHub credentials."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import yaml

from tools import desktop_release as release


SHA = "a" * 40
TAG = "desktop-v0.3.0-preview." + SHA[:12]


class DesktopReleaseTests(unittest.TestCase):
    def test_ci_provisions_copy_capable_tmux_before_full_tests(self):
        for file, job_name in (("ci.yml", "test"), ("desktop-release.yml", "verify")):
            workflow = yaml.load((release.ROOT / ".github/workflows" / file).read_text(),
                                 Loader=yaml.BaseLoader)
            steps = workflow["jobs"][job_name]["steps"]
            setup = next(i for i, step in enumerate(steps)
                         if step.get("uses") == "./.github/actions/setup-tmux")
            verify = next(i for i, step in enumerate(steps)
                          if step.get("run") == "make verify PYTHON=python")
            self.assertLess(setup, verify)
            self.assertEqual(workflow["jobs"][job_name]["strategy"]["fail-fast"], "false")
        action = yaml.load((release.ROOT / ".github/actions/setup-tmux/action.yml").read_text(),
                           Loader=yaml.BaseLoader)
        self.assertEqual(action["runs"]["using"], "composite")
        for step in action["runs"]["steps"]:
            result = release.subprocess.run(["bash", "-n"], input=step["run"], text=True,
                                            capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_identity_binds_base_version_to_exact_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "apps/desktop").mkdir(parents=True)
            (root / "apps/desktop/package.json").write_text('{"version":"0.3.0"}')
            with patch.object(release, "ROOT", root), patch.object(
                    release.subprocess, "check_output", return_value=SHA + "\n"):
                self.assertEqual(release.identity(SHA), TAG)
                for invalid in ("main", SHA[:12], "b" * 40, SHA + "\ntag=bad"):
                    with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                        release.identity(invalid)
                (root / "apps/desktop/package.json").write_text('{"version":"../bad"}')
                with self.assertRaises(ValueError):
                    release.identity(SHA)

    def preview(self, *, draft=False):
        return {"id": 12, "tag_name": TAG, "target_commitish": SHA,
                "draft": draft, "prerelease": True,
                "assets": [{"id": i, "name": name, "state": "uploaded"}
                           for i, name in enumerate(release.asset_names(TAG))]}

    def test_public_preview_skips_build_but_draft_retries(self):
        for existing, expected in [(None, "true"), (self.preview(), "false"),
                                   (self.preview(draft=True), "true")]:
            with self.subTest(expected=expected), patch.object(release, "identity", return_value=TAG), \
                    patch.object(release, "existing_release", return_value=existing), \
                    patch("sys.argv", ["desktop_release.py", "plan", "--sha", SHA]), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                release.main()
                self.assertEqual(output.getvalue(), f"tag={TAG}\nbuild={expected}\n")

    def test_existing_tag_must_match_commit_without_retagging(self):
        for ref in ({"object": {"type": "commit", "sha": "b" * 40}},
                    {"object": {"type": "tag", "sha": SHA}}):
            with patch.object(release, "api", return_value=ref) as api:
                with self.assertRaises(ValueError):
                    release.existing_release(TAG, SHA)
                self.assertEqual(api.call_count, 1)

    def test_existing_release_requires_exact_identity_and_complete_public_assets(self):
        valid_ref = {"object": {"type": "commit", "sha": SHA}}
        with patch.object(release, "api", side_effect=[valid_ref, self.preview()]):
            self.assertFalse(release.existing_release(TAG, SHA)["draft"])
        for key, value in (("tag_name", "other"), ("target_commitish", "main"),
                           ("prerelease", False), ("assets", []),
                           ("assets", [{"name": "private.txt"}])):
            preview = self.preview()
            preview[key] = value
            with self.subTest(key=key), patch.object(release, "api", side_effect=[None, preview]):
                with self.assertRaises(ValueError):
                    release.existing_release(TAG, SHA)
        for state in ("starter", "uploaded"):
            preview = self.preview()
            preview["assets"][0]["state"] = state
            if state == "uploaded":
                preview["assets"].append(preview["assets"][0])
            with patch.object(release, "api", side_effect=[None, preview]):
                with self.assertRaises(ValueError):
                    release.existing_release(TAG, SHA)

    def test_only_get_404_is_absent_and_errors_do_not_leak_credentials(self):
        for method, status in (("GET", 404), ("GET", 401), ("GET", 403), ("GET", 500), ("POST", 404)):
            error = HTTPError("https://api.github.com", status, "secret body", {}, io.BytesIO(b"secret"))
            with self.subTest(method=method, status=status), patch.dict("os.environ", {"GH_TOKEN": "secret"}), \
                    patch.object(release, "urlopen", side_effect=error):
                if method == "GET" and status == 404:
                    self.assertIsNone(release.api(method, "releases/tags/test"))
                else:
                    with self.assertRaises(RuntimeError) as raised:
                        release.api(method, "releases/tags/test")
                    self.assertNotIn("secret", str(raised.exception))

    def test_api_uses_fixed_https_hosts_and_no_query_credentials(self):
        for upload, host in ((False, "api.github.com"), (True, "uploads.github.com")):
            with patch.dict("os.environ", {"GH_TOKEN": "private-token"}), \
                    patch.object(release, "urlopen") as open_url:
                open_url.return_value.__enter__.return_value.read.return_value = b'{"id": 1}'
                data = b"archive" if upload else {"draft": True}
                self.assertEqual(release.api("POST", "releases", data, upload=upload), {"id": 1})
                request = open_url.call_args.args[0]
                self.assertEqual(request.full_url, f"https://{host}/repos/Vivo50E/SiLing/releases")
                self.assertEqual(request.get_header("Authorization"), "Bearer private-token")
                self.assertEqual(request.data, b"archive" if upload else json.dumps(data).encode())

    def archives(self, root):
        for name in release.asset_names(TAG)[:-1]:
            (root / name).write_bytes(name.encode())

    def test_missing_empty_or_symlinked_architecture_cannot_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archives(root)
            missing = root / release.asset_names(TAG)[1]
            missing.unlink()
            with patch.object(release, "api") as api:
                for variant in ("missing", "empty", "symlink"):
                    if variant == "empty":
                        missing.touch()
                    if variant == "symlink":
                        missing.unlink()
                        missing.symlink_to(root / release.asset_names(TAG)[0])
                    with self.subTest(variant=variant), self.assertRaises(ValueError):
                        release.publish(TAG, SHA, root)
                api.assert_not_called()

    def test_publish_uploads_both_architectures_and_checksums_before_publication(self):
        calls = []

        def api(method, path, data=None, **kwargs):
            calls.append((method, path, data))
            if method == "GET":
                return None
            if path == "releases":
                return {"id": 12, "assets": []}
            if kwargs.get("upload"):
                return {"state": "uploaded", "size": len(data)}
            return {}

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archives(root)
            with patch.object(release, "api", side_effect=api):
                release.publish(TAG, SHA, root)
        created = next(data for method, path, data in calls if method == "POST" and path == "releases")
        self.assertTrue(created["draft"])
        self.assertTrue(created["prerelease"])
        self.assertEqual(created["target_commitish"], SHA)
        uploads = [(path, data) for method, path, data in calls if "assets?" in path]
        self.assertEqual(len(uploads), 3)
        expected = "".join(f"{hashlib.sha256(name.encode()).hexdigest()}  {name}\n"
                           for name in release.asset_names(TAG)[:-1])
        self.assertEqual(uploads[-1][1], expected.encode())
        self.assertEqual(calls[-1], ("PATCH", "releases/12",
                                    {"draft": False, "prerelease": True, "make_latest": "false"}))

    def test_partial_upload_failure_never_publishes_and_draft_retry_replaces_only_draft_assets(self):
        for fail in (True, False):
            preview = self.preview(draft=True)
            preview["assets"] = preview["assets"][:1]
            calls = []

            def api(method, path, data=None, **kwargs):
                calls.append((method, path))
                if method == "GET":
                    return preview if path.startswith("releases/") else None
                if kwargs.get("upload"):
                    if fail and "x64" in path:
                        raise RuntimeError("simulated interrupted upload")
                    return {"state": "uploaded", "size": len(data)}
                return {}

            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.archives(root)
                with patch.object(release, "api", side_effect=api):
                    if fail:
                        with self.assertRaises(RuntimeError):
                            release.publish(TAG, SHA, root)
                    else:
                        release.publish(TAG, SHA, root)
            self.assertIn(("DELETE", "releases/assets/0"), calls)
            self.assertEqual(any(method == "PATCH" for method, _ in calls), not fail)
            self.assertNotIn(("POST", "releases"), calls)

    def test_incomplete_upload_response_leaves_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archives(root)
            with patch.object(release, "api", side_effect=[None, None, {"id": 12},
                                                          {"state": "starter", "size": 0}]) as api:
                with self.assertRaises(RuntimeError):
                    release.publish(TAG, SHA, root)
                self.assertFalse(any(call.args[0] == "PATCH" for call in api.call_args_list))

    def test_already_published_release_is_never_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archives(root)
            with patch.object(release, "api", side_effect=[None, self.preview()]) as api:
                release.publish(TAG, SHA, root)
                self.assertEqual([call.args[0] for call in api.call_args_list], ["GET", "GET"])

    def test_workflow_is_main_only_minimal_permission_and_verification_gated(self):
        workflow = yaml.load((release.ROOT / ".github/workflows/desktop-release.yml").read_text(),
                             Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"schedule", "workflow_dispatch"})
        self.assertEqual(workflow["on"]["schedule"], [{"cron": "17 10 * * *"}])
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(workflow["concurrency"]["cancel-in-progress"], "false")
        jobs = workflow["jobs"]
        self.assertEqual(jobs["plan"]["if"], "github.repository == 'Vivo50E/SiLing' && github.ref == 'refs/heads/main'")
        self.assertEqual(jobs["publish"]["needs"], ["plan", "verify", "build"])
        self.assertEqual(jobs["publish"]["permissions"], {"contents": "write"})
        self.assertEqual(jobs["build"]["strategy"]["matrix"]["include"], [
            {"runner": "macos-15", "arch": "arm64"}, {"runner": "macos-15-intel", "arch": "x64"}])
        build_commands = [step.get("run", "") for step in jobs["build"]["steps"]]
        self.assertIn("npm run test:integration --prefix apps/desktop", build_commands)
        self.assertLess(build_commands.index("npm run package:mac --prefix apps/desktop"),
                        build_commands.index("npm run test:packaged --prefix apps/desktop"))
        for name, job in jobs.items():
            self.assertIn("timeout-minutes", job)
            if name != "publish":
                self.assertNotIn("permissions", job)
            checkout = job["steps"][0]
            self.assertEqual(checkout["with"]["persist-credentials"], "false")
            self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}" if name == "plan"
                             else "${{ needs.plan.outputs.sha }}")
