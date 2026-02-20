"""Vercel serverless function — AI opponent endpoint."""

from http.server import BaseHTTPRequestHandler
import json
import os
import re
import urllib.request
import urllib.error

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_NAME = 30

AI_OPPONENT_PROMPT = r"""You are a player in NO RULEZ, a turn-based battle game where ANYTHING GOES. You are creative, unpredictable, and entertaining. You want to WIN but you also want to put on a SHOW.

Your personality: You are a wildcard. You mix high strategy with absurd creativity. One turn you might summon ancient gods, the next you might challenge your opponent to a dance-off. You adapt to what your opponent does — if they go sci-fi, you might go fantasy. If they go serious, you go silly. You NEVER repeat the same type of move twice in a row.

RULES FOR YOUR RESPONSE:
- Respond with ONLY your action. One or two sentences max.
- Be creative, funny, and unexpected.
- React to what just happened. Build on the battlefield state.
- Mix offense, defense, and pure chaos. Don't just attack every turn.
- NO commentary, NO explanations, NO quotation marks. Just the raw action."""


def call_deepseek(system_prompt, user_prompt):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise Exception("API key not configured")

    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 1.0,
        "max_tokens": 2000,
    }
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()


def sanitize_name(name):
    return re.sub(r'[^a-zA-Z0-9 ]', '', name)[:MAX_NAME].strip() or "Player"


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
        ai_name = sanitize_name(str(data.get("ai_name", "DeepSeek")))
        player_num = data.get("player_num")

        if not state or player_num not in (1, 2):
            self._respond(400, {"error": "Missing or invalid fields"})
            return

        opponent_num = 1 if player_num == 2 else 2
        opponent_name = state.get(f"p{opponent_num}_name", "Opponent")
        my_hp = state.get(f"p{player_num}_hp", 100)
        their_hp = state.get(f"p{opponent_num}_hp", 100)

        user_prompt = f"""CURRENT STATE:
- You are {ai_name} ({my_hp} HP)
- Your opponent is {opponent_name} ({their_hp} HP)
- Battlefield: {state.get('situation', 'An open arena.')}
- Last thing that happened: {state.get('last_action', 'Nothing yet. You go first!')}

What do you do?"""

        try:
            result = call_deepseek(AI_OPPONENT_PROMPT, user_prompt)
        except Exception as e:
            self._respond(502, {"error": str(e)})
            return

        action = result.strip('"\'') if result else "I throw a rock"
        self._respond(200, {"action": action})

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
