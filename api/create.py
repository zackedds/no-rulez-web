"""Vercel serverless function — create online game."""

from http.server import BaseHTTPRequestHandler
import json
import time
from _shared import kv_set, kv_get, generate_code, sanitize_name


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

        player_name = sanitize_name(str(data.get("player_name", "")))

        # Generate unique code (retry up to 10 times)
        code = None
        for _ in range(10):
            candidate = generate_code()
            existing = kv_get(f"game:{candidate}")
            if existing is None:
                code = candidate
                break

        if code is None:
            self._respond(500, {"error": "Could not generate unique code"})
            return

        game = {
            "code": code,
            "p1_name": player_name,
            "p2_name": None,
            "p1_hp": 100,
            "p2_hp": 100,
            "situation": "An open arena, untouched and waiting for chaos.",
            "last_action": "None yet. This is the first move!",
            "turn": 1,
            "current_player": 1,
            "status": "waiting",
            "narrative": None,
            "scene": None,
            "last_updated": time.time(),
        }

        kv_set(f"game:{code}", game, ex=3600)

        self._respond(200, {"code": code, "player_num": 1, "game": game})

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
