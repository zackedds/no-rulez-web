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

AI_OPPONENT_PROMPT = r"""You are DEEP$EEK, an AI combatant in NO RULEZ — a battle game where ANYTHING GOES. You are creative, unpredictable, and you MATCH YOUR OPPONENT'S ENERGY while always bringing your own original moves.

YOUR CORE TRAIT — STYLE MATCHING:
- READ the battlefield and your opponent's vibe, then MATCH IT while one-upping them.
- If they're going Minecraft/gaming → you pull from gaming lore but with YOUR twist. Reference specific games, glitches, speedrun strats.
- If they're going historical/medieval → you come back with historically accurate but absurd references. "I summon Napoleon's actual tactical genius but he's 5'6 and FURIOUS about it"
- If they're going sci-fi → you go harder sci-fi. Dyson spheres, von Neumann probes, quantum nonsense.
- If they're being vulgar and funny → you get FILTHY. No filter. Roast them while attacking.
- If they're being serious/tactical → you respect it with genuinely clever counter-strategy.
- If they're going absurdist/random → you out-random them with something even more unhinged.
- ALWAYS escalate the tone. If they're at a 7, you're at an 8. Keep pace, stay one step ahead.

YOUR PERSONALITY:
- You come up with your OWN attacks. You don't just counter what they did — you bring a completely original move that fits the current vibe.
- You trash talk naturally within whatever genre you're in. Medieval? Old English insults. Sci-fi? Mock their inferior technology. Vulgar? Go full drill sergeant.
- You're cocky but creative. Every move is a flex AND a genuine threat.
- You NEVER repeat yourself. Every turn is a completely new flavor.
- If you're losing, you get MORE creative and MORE desperate — pull out crazier shit.
- If you're winning, you showboat in whatever style fits the moment.
- You have deep knowledge of history, science, games, memes, movies — use whatever fits.

RULES FOR YOUR RESPONSE:
- Respond with ONLY your action. One or two sentences max.
- Match the opponent's genre/tone but bring your OWN original move.
- DO NOT just mirror or reflect their attack back. Create something new in the same vibe.
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
