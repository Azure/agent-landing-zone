"""Minimal Foundry hosted agent for Agent Landing Zone.

Serves the responses protocol on port 8088 and answers every request with a
short message that names the Foundry project endpoint it found in the platform
outputs contract (AGENTLZ_PLATFORM_OUTPUTS, label agent-lz). Replace
``answer`` with your agent logic.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from azure.appconfiguration import AzureAppConfigurationClient
from azure.identity import DefaultAzureCredential

LABEL = "agent-lz"
OUTPUTS_KEY = "AGENTLZ_PLATFORM_OUTPUTS"
LOGGER = logging.getLogger("sample-agent")


def platform_outputs() -> dict[str, object]:
    endpoint = os.environ["APP_CONFIG_ENDPOINT"]
    client = AzureAppConfigurationClient(endpoint, DefaultAzureCredential())
    setting = client.get_configuration_setting(key=OUTPUTS_KEY, label=LABEL)
    return json.loads(setting.value or "{}")


def answer() -> str:
    try:
        foundry = platform_outputs().get("foundry") or {}
        project = foundry.get("projectEndpoint", "unknown") if isinstance(foundry, dict) else "unknown"
    except Exception:
        LOGGER.exception("Could not read platform outputs.")
        project = "unavailable"
    return f"Hello! Sample agent running on project {project}."


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path in ("/health", "/readiness", "/liveness"):
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.path.rstrip("/") != "/responses":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._send(
            200,
            {
                "id": f"resp_{uuid.uuid4().hex}",
                "object": "response",
                "created_at": int(time.time()),
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": answer()}],
                    }
                ],
            },
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ThreadingHTTPServer(("0.0.0.0", 8088), Handler).serve_forever()
