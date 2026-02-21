"""Vercel serverless function — referee endpoint."""

from http.server import BaseHTTPRequestHandler
import json
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from _shared import (
    call_deepseek, parse_response, sanitize_name, sanitize_action,
    clamp_hp, build_turn_prompt, REFEREE_PROMPT,
)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 10240:
            self._respond(413, {"error": "Request too large"})
            return

        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except Exception:
            self._respond(400, {"error": "Invalid JSON"})
            return

        state = data.get("state")
        player_name = sanitize_name(str(data.get("player_name", "")))
        player_num = data.get("player_num")
        action = sanitize_action(str(data.get("action", "")))

        if not state or not action or player_num not in (1, 2):
            self._respond(400, {"error": "Missing or invalid fields"})
            return

        p1_hp = state.get("p1_hp", 100)
        p2_hp = state.get("p2_hp", 100)

        turn_prompt = build_turn_prompt(state, player_name, player_num, action)

        try:
            response = call_deepseek(REFEREE_PROMPT, turn_prompt)
        except Exception as e:
            self._respond(502, {"error": str(e)})
            return

        narrative, scene, state_update = parse_response(response)
        if state_update is None:
            self._respond(500, {"error": "Referee fumbled — could not parse response"})
            return

        new_p1, new_p2 = clamp_hp(p1_hp, p2_hp, state_update)

        self._respond(200, {
            "narrative": narrative,
            "scene": scene,
            "state": {
                "p1_hp": new_p1,
                "p2_hp": new_p2,
                "situation": state_update.get("situation", ""),
                "last_action": state_update.get("last_action", ""),
                "image_safe": state_update.get("image_safe", False),
                "image_prompt": state_update.get("image_prompt", ""),
            },
        })

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
