import json
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_DIR / "static"


class ProgressiveWebAppContractTests(unittest.TestCase):
    def test_manifest_has_installable_app_metadata_and_icons(self):
        manifest = json.loads((STATIC_DIR / "manifest.webmanifest").read_text())

        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["theme_color"], "#0d1117")
        self.assertIn("standalone", manifest["display_override"])
        self.assertTrue(any(icon.get("sizes") == "192x192"
                            for icon in manifest["icons"]))
        self.assertTrue(any(icon.get("sizes") == "512x512"
                            for icon in manifest["icons"]))
        for icon in manifest["icons"]:
            icon_path = PROJECT_DIR / icon["src"].removeprefix("/")
            self.assertTrue(icon_path.is_file(), icon_path)

    def test_index_registers_root_scoped_worker_and_macos_metadata(self):
        index = (STATIC_DIR / "index.html").read_text()

        self.assertIn('rel="manifest" href="/static/manifest.webmanifest"', index)
        self.assertIn('rel="apple-touch-icon"', index)
        self.assertIn('name="apple-mobile-web-app-capable"', index)
        self.assertIn(
            'navigator.serviceWorker.register("/service-worker.js", { scope: "/" })',
            index,
        )

    def test_worker_never_caches_live_dashboard_or_api_responses(self):
        worker = (STATIC_DIR / "service-worker.js").read_text()

        self.assertNotIn('"/"', worker.split("OFFLINE_ASSETS", 1)[1].split("];", 1)[0])
        self.assertNotIn("/api/", worker)
        self.assertIn('request.mode !== "navigate"', worker)
        self.assertIn('fetch(request).catch(', worker)

    def test_backend_serves_worker_at_root_without_caching(self):
        backend = (PROJECT_DIR / "agent_orchestrator" / "dashboard.py").read_text()
        route_start = backend.index('@app.get("/service-worker.js"')
        route = backend[route_start:route_start + 800]

        self.assertIn('"Service-Worker-Allowed": "/"', route)
        self.assertIn('"Cache-Control": "no-cache, no-store, must-revalidate"', route)


if __name__ == "__main__":
    unittest.main()
