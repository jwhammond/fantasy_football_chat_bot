"""Entrypoint for hosts that require a bound HTTP port (e.g. Render Web Services).

The bot itself is a scheduler with no network listener. Render's free tier only
offers Web Services, which must open a port or the deploy fails, so this starts a
tiny Flask health endpoint in a background thread and then runs the bot in the
main thread.
"""
import os
import threading

from flask import Flask
from werkzeug.serving import make_server

app = Flask(__name__)

RENDER_DEFAULT_PORT = 10000


@app.route("/")
def health():
    return "ok"


def get_port():
    """Port to bind. Render injects PORT; fall back to Render's default."""
    return int(os.environ.get("PORT", RENDER_DEFAULT_PORT))


def start_health_server(port):
    """Serve the Flask app on all interfaces in a daemon thread.

    Returns the server so callers can read the bound port or shut it down.
    """
    server = make_server("0.0.0.0", port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_bot():
    from gamedaybot.espn.espn_bot import espn_bot
    from gamedaybot.espn.scheduler import scheduler

    espn_bot("init")
    scheduler()


def main():
    start_health_server(get_port())
    run_bot()


if __name__ == "__main__":
    main()
