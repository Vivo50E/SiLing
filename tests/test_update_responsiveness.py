"""Periodic update checks must not block terminal I/O on the ASGI loop."""
import asyncio
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

import httpx
from agent_orchestrator import dashboard


class UpdateResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_status_allows_other_requests_while_git_is_slow(self):
        entered, finished, release = threading.Event(), threading.Event(), threading.Event()

        def slow_status():
            entered.set()
            release.wait(2)
            finished.set()
            return {'available': True, 'candidates': []}

        with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
            app = dashboard.create_app(Path('/nonexistent/siling-update-test'), ttyd_enabled=False, remote_nodes_enabled=False)
        with patch.object(dashboard.SelfUpdateManager, 'fetch_upstream', return_value={'ok': True}), \
                patch.object(dashboard.SelfUpdateManager, 'status', side_effect=slow_status):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
                request = asyncio.create_task(client.post('/api/self-update/fetch', json={}, headers={'X-Orch-Self-Update': 'reviewed'}))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                    # A blocked event loop cannot resume here until status ends.
                    self.assertFalse(finished.is_set(), 'Git status blocked terminal event-loop scheduling')
                    response = await asyncio.wait_for(client.get('/api/health'), 1)
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(finished.is_set(), 'Other requests must finish before slow Git status')
                finally:
                    release.set()
                    response = await request
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['fetch'], {'ok': True})
