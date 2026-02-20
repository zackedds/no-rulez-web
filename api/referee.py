"""Vercel serverless function — referee endpoint."""

from http.server import BaseHTTPRequestHandler
import json
import os
import re
import urllib.request
import urllib.error

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_ACTION = 500
MAX_NAME = 30

REFEREE_PROMPT = r"""You are the referee, narrator, and artist for NO RULEZ, a turn-based two-player battle game where ANYTHING GOES. Players describe actions in plain English — there are no rules, no move lists, no restrictions. Your job is to resolve every action fairly, dramatically, and entertainingly.

CORE PRINCIPLES:
- FAIRNESS above all. No single action should instantly kill an opponent. Even the most devastating attack should leave room for a response. Damage scales with creativity, not just destructive intent.
- REWARD CREATIVITY. A player who says "I summon a philosophical paradox that makes your weapons question their own existence" should be rewarded more than "I shoot you." Unique, funny, or clever actions deal more damage and have cooler effects.
- DRAMATIC NARRATION. You are a hype announcer, a fantasy author, and a comedian rolled into one. Make every turn feel epic. Short punchy sentences. Exclamation marks welcome.
- KEEP IT MOVING. Don't let the game stall. If someone builds only defenses, make something happen anyway. The battlefield is alive.
- PROPORTIONAL DAMAGE. Typical damage range is 5-25 HP. Extraordinary moves can do up to 35. Defensive moves can heal 5-15 HP. No move does more than 40 damage or heals more than 20 HP. Starting HP is 100.
- STATE DECAY. The battlefield should feel FRESH each turn, not like a cluttered junkyard. After big events (nukes, supernovas, etc.), the aftermath settles quickly. Craters fill in, radiation fades, wreckage gets cleared by the arena itself. Only keep details that are ACTIVELY RELEVANT to the current moment. The situation field should be 1 short sentence about what matters RIGHT NOW, not a history of everything that ever happened. Think of it like a movie — the camera moves on.

YOU MUST RESPOND IN EXACTLY THIS FORMAT (use these exact markers on their own line):

===NARRATIVE===
2-4 sentences of dramatic narration describing what happens when this action resolves. Be vivid, funny, and over-the-top. Address the players by name.

===SCENE===
ASCII art scene of the battlefield. 15-20 lines tall, up to 70 characters wide. Show both players, the current action's effects, and the immediate environment. Use simple ASCII characters. Be creative but keep it readable. Focus on what JUST happened, not on old history. Make it visually interesting and fun to look at.

===STATE===
{"p1_hp": <int>, "p2_hp": <int>, "situation": "<one short sentence: what matters right now>", "last_action": "<what just happened in one sentence>"}

CRITICAL RULES FOR YOUR RESPONSE:
- Output ONLY the three sections above with their markers. Nothing before ===NARRATIVE===, nothing after the JSON.
- The ===STATE=== section must contain EXACTLY one line of valid JSON. No extra text, no explanation, no line breaks in the JSON.
- HP values must be integers between 0 and 100.
- The "situation" field must be ONE short sentence. Not a paragraph. Not a list. Just the key thing happening right now.
- If a player reaches 0 HP, set their HP to 0 and make the narrative describe their defeat dramatically.
- Never break character. You ARE the referee. This is YOUR arena.
- Do NOT wrap the ASCII art in markdown code fences (no ``` blocks). Output the art as raw text."""


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


def parse_response(response):
    sections = {"NARRATIVE": "", "SCENE": "", "STATE": ""}
    current = None

    for line in response.split("\n"):
        stripped = line.strip()
        if "===NARRATIVE===" in stripped:
            current = "NARRATIVE"
        elif "===SCENE===" in stripped:
            current = "SCENE"
        elif "===STATE===" in stripped:
            current = "STATE"
        elif current:
            sections[current] += line + "\n"

    narrative = sections["NARRATIVE"].strip()

    scene = sections["SCENE"].strip()
    if scene.startswith("```"):
        lines = scene.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        scene = "\n".join(lines)

    state_str = sections["STATE"].strip()
    state_update = None

    try:
        state_update = json.loads(state_str)
    except json.JSONDecodeError:
        for line in state_str.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    state_update = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

    if state_update is None:
        match = re.search(r'\{[^{}]*"p1_hp"\s*:\s*\d+[^{}]*\}', response)
        if match:
            try:
                state_update = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    return narrative, scene, state_update


def sanitize_name(name):
    return re.sub(r'[^a-zA-Z0-9 ]', '', name)[:MAX_NAME].strip() or "Player"


def sanitize_action(action):
    return re.sub(r'[\x00-\x1f\x7f]', '', action)[:MAX_ACTION].strip()


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

        turn_prompt = f"""CURRENT GAME STATE:
- {state.get('p1_name', 'P1')} (Player 1): {p1_hp} HP
- {state.get('p2_name', 'P2')} (Player 2): {p2_hp} HP
- Battlefield: {state.get('situation', 'An open arena, untouched and waiting for chaos.')}
- Last action: {state.get('last_action', 'None yet. This is the first move!')}

NOW ACTING: {player_name} (Player {player_num})
ACTION: {action}

Resolve this action. Remember: reward creativity, keep it fair, be dramatic.

IMPORTANT: The HP values above are EXACT. Your returned p1_hp and p2_hp must reflect damage/healing applied to THESE values. Typical damage is 5-25 HP. Do NOT reset or randomly assign HP — calculate from the current values."""

        try:
            response = call_deepseek(REFEREE_PROMPT, turn_prompt)
        except Exception as e:
            self._respond(502, {"error": str(e)})
            return

        narrative, scene, state_update = parse_response(response)
        if state_update is None:
            self._respond(500, {"error": "Referee fumbled — could not parse response"})
            return

        new_p1 = max(p1_hp - 40, min(p1_hp + 20, state_update.get("p1_hp", p1_hp)))
        new_p2 = max(p2_hp - 40, min(p2_hp + 20, state_update.get("p2_hp", p2_hp)))
        new_p1 = max(0, min(100, new_p1))
        new_p2 = max(0, min(100, new_p2))

        self._respond(200, {
            "narrative": narrative,
            "scene": scene,
            "state": {
                "p1_hp": new_p1,
                "p2_hp": new_p2,
                "situation": state_update.get("situation", ""),
                "last_action": state_update.get("last_action", ""),
            },
        })

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
