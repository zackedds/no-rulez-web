"""Vercel serverless function — poll game state."""

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
from _shared import kv_get


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        code = (params.get("code", [""])[0]).strip().upper()
        since = params.get("since", [None])[0]

        if not code:
            self._respond(400, {"error": "Missing code"})
            return

        game = kv_get(f"game:{code}")
        if game is None:
            self._respond(404, {"error": "Game not found or expired"})
            return

        if since:
            try:
                since_ts = float(since)
                if game.get("last_updated", 0) <= since_ts:
                    self._respond(200, {"changed": False})
                    return
            except (ValueError, TypeError):
                pass

        self._respond(200, {"changed": True, "game": game})

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
