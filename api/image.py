"""Vercel serverless function — generate image via Replicate FLUX-schnell."""

from http.server import BaseHTTPRequestHandler
import json
import os
import time
import urllib.request
import urllib.error

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
REPLICATE_MODEL_URL = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"

IMAGE_STYLE_SUFFIX = "chaotic cartoon battle art, indie game style, exaggerated proportions, dynamic action pose, dark arena setting, vibrant saturated colors, warm fire accents, slightly rough and messy rendering, fun and over-the-top, comic book energy, no text, no watermark"


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

        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            self._respond(400, {"error": "Missing prompt"})
            return

        if not REPLICATE_API_TOKEN:
            self._respond(500, {"error": "Image generation not configured"})
            return

        styled_prompt = f"{prompt} {IMAGE_STYLE_SUFFIX}"

        # Create prediction
        body = json.dumps({
            "input": {
                "prompt": styled_prompt,
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
                "Prefer": "wait",  # Sync mode — waits for result
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # With Prefer: wait, output should be ready
            output = result.get("output")
            if output and isinstance(output, list) and len(output) > 0:
                # Output items can be strings (URLs) or objects with .url()
                image_url = output[0] if isinstance(output[0], str) else str(output[0])
                self._respond(200, {"image_url": image_url})
                return

            # If not ready (shouldn't happen with Prefer: wait), poll
            poll_url = result.get("urls", {}).get("get")
            if not poll_url:
                self._respond(500, {"error": "No poll URL returned"})
                return

            # Poll up to 30 seconds
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
                    output = poll_result.get("output", [])
                    if output:
                        image_url = output[0] if isinstance(output[0], str) else str(output[0])
                        self._respond(200, {"image_url": image_url})
                        return
                elif status == "failed":
                    self._respond(500, {"error": "Image generation failed"})
                    return

            self._respond(504, {"error": "Image generation timed out"})

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self._respond(e.code, {"error": f"Replicate API error: {error_body[:200]}"})
        except Exception as e:
            self._respond(500, {"error": str(e)[:200]})

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
