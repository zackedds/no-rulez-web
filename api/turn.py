"""Vercel serverless function — submit turn in online game."""

from http.server import BaseHTTPRequestHandler
import json
import time
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from _shared import (
    kv_set, kv_get, sanitize_action, call_deepseek, parse_response,
    clamp_hp, build_turn_prompt, REFEREE_PROMPT, generate_image,
)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 10240:
            self._respond(413, {"error": "Request too large"})
            return

        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            self._respond(400, {"error": "Invalid JSON"})
            return

        code = str(data.get("code", "")).strip().upper()
        player_num = data.get("player_num")
        action = sanitize_action(str(data.get("action", "")))

        if not code or player_num not in (1, 2) or not action:
            self._respond(400, {"error": "Missing or invalid fields"})
            return

        game = kv_get(f"game:{code}")
        if game is None:
            self._respond(404, {"error": "Game not found"})
            return

        if game.get("status") == "finished":
            self._respond(400, {"error": "Game is already over"})
            return

        if game.get("status") != "active":
            self._respond(400, {"error": "Game hasn't started yet"})
            return

        if game.get("current_player") != player_num:
            self._respond(400, {"error": "Not your turn"})
            return

        player_name = game.get(f"p{player_num}_name", f"Player {player_num}")
        p1_hp = game.get("p1_hp", 100)
        p2_hp = game.get("p2_hp", 100)

        turn_prompt = build_turn_prompt(game, player_name, player_num, action)

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

        game["p1_hp"] = new_p1
        game["p2_hp"] = new_p2
        game["situation"] = state_update.get("situation", "")
        game["last_action"] = state_update.get("last_action", "")
        game["narrative"] = narrative
        game["scene"] = scene
        game["image_safe"] = state_update.get("image_safe", False)
        game["image_prompt"] = state_update.get("image_prompt", "")

        # Persist character appearances for visual consistency across turns
        if state_update.get("p1_look"):
            game["p1_look"] = state_update["p1_look"]
        if state_update.get("p2_look"):
            game["p2_look"] = state_update["p2_look"]

        # Generate image server-side so both players share the same one
        image_url = None
        if game["image_safe"] and game["image_prompt"]:
            image_url = generate_image(game["image_prompt"])
        game["image_url"] = image_url

        game["turn"] = game.get("turn", 1) + 1
        game["current_player"] = 2 if player_num == 1 else 1
        game["last_updated"] = time.time()
        game["last_actor"] = player_num
        game["last_actor_action"] = action

        if new_p1 <= 0 or new_p2 <= 0:
            game["status"] = "finished"

        kv_set(f"game:{code}", game, ex=3600)

        self._respond(200, {"game": game})

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
