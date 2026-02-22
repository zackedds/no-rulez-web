"""Shared utilities for NO RULEZ API endpoints."""

import json
import os
import re
import time
import random
import urllib.request
import urllib.error

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_ACTION = 200
MAX_NAME = 30

KV_URL = os.environ.get("KV_REST_API_URL", "") or os.environ.get("UPSTASH_REDIS_REST_URL", "")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN", "") or os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

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
1-2 sentences MAX. Punchy, funny, dramatic. No filler. Address players by name.

===SCENE===
ASCII art scene. This is the FALLBACK when images can't be generated. If image_safe is true, you can keep this minimal (4-6 lines) since a real image will replace it. If image_safe is false, go all out: 8-12 lines tall, up to 50 characters wide, show both players and the action with detail.

===STATE===
{"p1_hp": <int>, "p2_hp": <int>, "situation": "<one short sentence: what matters right now>", "last_action": "<what just happened in one sentence>", "image_safe": <true or false>, "image_prompt": "<visual scene description for AI image generation, or empty string>"}

CRITICAL RULES FOR YOUR RESPONSE:
- Output ONLY the three sections above with their markers. Nothing before ===NARRATIVE===, nothing after the JSON.
- The ===STATE=== section must contain EXACTLY one line of valid JSON. No extra text, no explanation, no line breaks in the JSON.
- HP values must be integers between 0 and 100.
- The "situation" field must be ONE short sentence. Not a paragraph. Not a list. Just the key thing happening right now.
- If a player reaches 0 HP, set their HP to 0 and make the narrative describe their defeat dramatically.
- Never break character. You ARE the referee. This is YOUR arena.
- Do NOT wrap the ASCII art in markdown code fences (no ``` blocks). Output the art as raw text.

IMAGE GENERATION RULES:
- "image_safe" must be true or false. Set to true if the scene can be illustrated as a fun, dramatic, creative battle image. Set to false if the scene involves graphic gore, nudity, sexually explicit content, or extreme real-world violence.
- If image_safe is false, set image_prompt to an empty string "".
- The image prompt should NOT include text/words/letters to render — image generators can't spell. Describe visuals only.
- Keep it fun and creative — explosions, absurd weapons, cosmic battles, summoned creatures are all GREAT image prompts. Just no gore, blood, nudity, or sexual content.

IMAGE PROMPT STYLE GUIDE (CRITICAL — follow this EVERY time for visual consistency):
- "image_prompt" should be 2-3 sentences describing the scene for an AI image generator.
- ALWAYS begin the prompt with this style prefix: "Stylized 3D render, Pixar-meets-Fortnite aesthetic, vibrant saturated colors, dynamic action pose, exaggerated proportions, soft cel-shading with dramatic cinematic lighting, fun and energetic mood."
- Then describe the specific scene: the two characters (as cartoonish warriors/fighters), what action is happening, the environment, any special effects (explosions, lightning, magic, etc).
- Characters should feel like fun cartoon battle characters — expressive faces, exaggerated poses, bold outlines. Think Clash Royale or Overwatch character style.
- Environments should be colorful and stylized — not photorealistic. Bright skies, glowing effects, stylized arenas.
- Keep the SAME art style every single turn. Never switch to photorealistic, anime, pixel art, or any other style. Always the same Pixar/Fortnite 3D cartoon look.
- Describe dynamic camera angles: low angle hero shots, dramatic wide shots, over-the-shoulder action shots.
- Include visual effects: particle effects, energy blasts, impact rings, motion blur, dramatic clouds, lens flares."""


def call_deepseek(system_prompt, user_prompt, max_tokens=1000):
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
        "max_tokens": max_tokens,
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


def clamp_hp(old_p1, old_p2, state_update):
    """Clamp HP changes to valid ranges."""
    new_p1 = max(old_p1 - 40, min(old_p1 + 20, state_update.get("p1_hp", old_p1)))
    new_p2 = max(old_p2 - 40, min(old_p2 + 20, state_update.get("p2_hp", old_p2)))
    new_p1 = max(0, min(100, new_p1))
    new_p2 = max(0, min(100, new_p2))
    return new_p1, new_p2


def build_turn_prompt(state, player_name, player_num, action):
    return f"""CURRENT GAME STATE:
- {state.get('p1_name', 'P1')} (Player 1): {state.get('p1_hp', 100)} HP
- {state.get('p2_name', 'P2')} (Player 2): {state.get('p2_hp', 100)} HP
- Battlefield: {state.get('situation', 'An open arena, untouched and waiting for chaos.')}
- Last action: {state.get('last_action', 'None yet. This is the first move!')}

NOW ACTING: {player_name} (Player {player_num})
ACTION: {action}

Resolve this action. Remember: reward creativity, keep it fair, be dramatic.

IMPORTANT: The HP values above are EXACT. Your returned p1_hp and p2_hp must reflect damage/healing applied to THESE values. Typical damage is 5-25 HP. Do NOT reset or randomly assign HP — calculate from the current values."""


# --- KV helpers ---

def kv_set(key, value, ex=None):
    cmd = ["SET", key, json.dumps(value)]
    if ex:
        cmd += ["EX", str(ex)]
    body = json.dumps(cmd).encode()
    req = urllib.request.Request(KV_URL, data=body, headers={
        "Authorization": f"Bearer {KV_TOKEN}",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def kv_get(key):
    req = urllib.request.Request(f"{KV_URL}/GET/{key}", headers={
        "Authorization": f"Bearer {KV_TOKEN}"
    })
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
        result = data.get("result")
        if result:
            return json.loads(result)
        return None


def kv_del(key):
    req = urllib.request.Request(f"{KV_URL}/DEL/{key}", headers={
        "Authorization": f"Bearer {KV_TOKEN}"
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


# Code generation for game codes
SAFE_CHARS = "0123456789"

def generate_code():
    return "".join(random.choice(SAFE_CHARS) for _ in range(6))


# --- Image generation ---

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
REPLICATE_MODEL_URL = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"

def generate_image(prompt):
    """Call Replicate FLUX-schnell and return image URL, or None on failure."""
    if not prompt or not REPLICATE_API_TOKEN:
        return None

    body = json.dumps({
        "input": {
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": "16:9",
            "output_format": "webp",
            "output_quality": 80,
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        REPLICATE_MODEL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        output = result.get("output")
        if output and isinstance(output, list) and len(output) > 0:
            return output[0] if isinstance(output[0], str) else str(output[0])

        # Poll fallback
        poll_url = result.get("urls", {}).get("get")
        if not poll_url:
            return None

        for _ in range(15):
            time.sleep(2)
            poll_req = urllib.request.Request(
                poll_url,
                headers={"Authorization": f"Bearer {REPLICATE_API_TOKEN}"},
            )
            with urllib.request.urlopen(poll_req, timeout=10) as poll_resp:
                poll_result = json.loads(poll_resp.read().decode("utf-8"))

            status = poll_result.get("status")
            if status == "succeeded":
                out = poll_result.get("output", [])
                if out:
                    return out[0] if isinstance(out[0], str) else str(out[0])
            elif status == "failed":
                return None

        return None
    except Exception:
        return None
