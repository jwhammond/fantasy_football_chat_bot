import sys
import os
import urllib.request
import pytest
sys.path.insert(1, os.path.abspath('.'))

import app


def test_get_port_reads_render_port_env_var(monkeypatch):
    monkeypatch.setenv('PORT', '4321')
    assert app.get_port() == 4321


def test_get_port_defaults_to_render_default_when_unset(monkeypatch):
    monkeypatch.delenv('PORT', raising=False)
    assert app.get_port() == 10000


def test_start_health_server_serves_http_in_background_thread():
    server = app.start_health_server(port=0)
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/') as resp:
            assert resp.status == 200
    finally:
        server.shutdown()


def test_main_starts_health_server_then_runs_bot(monkeypatch):
    calls = []
    monkeypatch.setattr(app, 'start_health_server', lambda port: calls.append(('server', port)))
    monkeypatch.setattr(app, 'get_port', lambda: 5555)
    monkeypatch.setattr(app, 'run_bot', lambda: calls.append(('bot',)))

    app.main()

    assert calls == [('server', 5555), ('bot',)]
