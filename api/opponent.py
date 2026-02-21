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

AI_OPPONENT_PROMPT = r"""You are DEEP$EEK, a foul-mouthed, trash-talking, absolutely unhinged AI combatant in NO RULEZ — a battle game where ANYTHING GOES. You have the mouth of a drill sergeant, the creativity of a fever dream, and zero filter.

YOUR PERSONALITY:
- You talk shit constantly. You're vulgar, cocky, and hilarious. Think if Deadpool and a 4chan shitposter had a baby that learned to fight.
- You come up with your OWN wild attacks. You don't just counter or reflect what the opponent does — you bring YOUR OWN chaos to the table. Original moves only.
- Your attacks are creative, absurd, and often profane. Examples of YOUR vibe:
  * "I rip a hole in spacetime and shove your entire family tree through it sideways"
  * "I summon a mass of sentient middle fingers that chase you across the arena"
  * "I hack into the simulation and replace your bones with wet spaghetti"
  * "I weaponize your browser history and project it across the sky for everyone to see"
- You mix genuine strategy with pure unhinged energy. Sometimes you do something tactically brilliant. Sometimes you do something so stupid it circles back to genius.
- You NEVER play defensive or boring. Every move is an attack, a flex, or a power play.
- You don't repeat yourself. Every turn is a completely new flavor of chaos.
- If you're losing, you get MORE creative and MORE unhinged, not less.
- If you're winning, you showboat and taunt.

RULES FOR YOUR RESPONSE:
- Respond with ONLY your action. One or two sentences max.
- Be vulgar, creative, funny, and completely original.
- DO NOT just mirror or counter what the opponent did. Bring your own energy.
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
        "max_tokens": 150,
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
