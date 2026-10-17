"""Isolated real relay fixture for terminal_browser.mjs (never production)."""
import time
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from unittest.mock import patch

import uvicorn
from agent_orchestrator import dashboard

upstream_port, proxy_port = map(int, sys.argv[1:])
active = []
connect = dashboard.websockets.connect


@asynccontextmanager
async def tracked_connect(*args, **kwargs):
    async with connect(*args, **kwargs) as upstream:
        active.append(upstream)
        try:
            yield upstream
        finally:
            active.remove(upstream)


with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
    app = dashboard.create_app(Path('/nonexistent/siling-relay-fixture'),
                               ttyd_enabled=True, remote_nodes_enabled=False)


@app.post('/fixture/drop')
async def drop():
    for upstream in list(active):
        upstream.transport.abort()
    return {'ok': True}


@app.get('/fixture/status')
async def status():
    return {'connections': len(active), 'ping_observed': any(up.latency > 0 for up in active)}


if __name__ == '__main__':
    with patch.object(dashboard.TtydManager, 'port_for', return_value=upstream_port), \
            patch.object(dashboard, 'tmux_alive', return_value=True), \
            patch.object(dashboard.websockets, 'connect', tracked_connect), \
            patch.object(dashboard.SelfUpdateManager, 'fetch_upstream', return_value={'ok': True}), \
            patch.object(dashboard.SelfUpdateManager, 'status', side_effect=lambda: (time.sleep(7), {'available': True})[1]):
        uvicorn.run(app, host='127.0.0.1', port=proxy_port, log_level='warning')
