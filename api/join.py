"""Vercel serverless function — join online game."""

from http.server import BaseHTTPRequestHandler
import json
import time
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from _shared import kv_set, kv_get, sanitize_name


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 4096:
            self._respond(413, {"error": "Request too large"})
            return

        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            self._respond(400, {"error": "Invalid JSON"})
            return

        code = str(data.get("code", "")).strip().upper()
        player_name = sanitize_name(str(data.get("player_name", "")))

        if not code or len(code) != 6:
            self._respond(400, {"error": "Invalid game code"})
            return

        game = kv_get(f"game:{code}")
        if game is None:
            self._respond(404, {"error": "Game not found. Check the code and try again."})
            return

        if game.get("p2_name") is not None:
            self._respond(409, {"error": "Game is already full."})
            return

        game["p2_name"] = player_name
        game["status"] = "active"
        game["last_updated"] = time.time()

        kv_set(f"game:{code}", game, ex=3600)

        self._respond(200, {"player_num": 2, "game": game})

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
