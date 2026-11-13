"""Minimal Foundry hosted agent for Agent Landing Zone.

Serves the Responses protocol on port 8088 and answers every request with a
greeting that names the Foundry project endpoint injected by the platform
(``FOUNDRY_PROJECT_ENDPOINT``, with ``AZURE_AI_PROJECT_ENDPOINT`` as a local
fallback). Reading the platform-injected environment directly keeps startup
dependency-free and allows the sample to deploy whether Azure App Configuration
is enabled or disabled (``appRuntimeConfigurationMode = "none"`` /
``deployAppConfig = false``).

Production graduation requirements beyond this minimal smoke sample:
1. Use ``azure-ai-agentserver-responses`` so the hosted server implements the
   full Responses lifecycle and persisted ``GET /responses/{id}`` lookups.
   Synthetic ``resp_<uuid>`` identifiers returned by a raw HTTP handler are not
   persisted for ``GET /responses/{id}``.
2. Emit GenAI OpenTelemetry ``invoke_agent`` spans (bundled automatically by
   ``azure-ai-agentserver-responses`` when ``APPLICATIONINSIGHTS_CONNECTION_STRING``
   is platform-injected) so Microsoft Foundry Traces and scheduled trace
   evaluations can discover and score agent interactions. Do not declare
   ``FOUNDRY_*``, ``AGENT_*``, or ``APPLICATIONINSIGHTS_CONNECTION_STRING`` in
   ``azure.yaml`` because Foundry reserves those names and rejects overrides.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOGGER = logging.getLogger("sample-agent")


def project_endpoint(environment: Mapping[str, str] | None = None) -> str:
    """Resolve the Foundry project endpoint without requiring App Configuration."""
    env = os.environ if environment is None else environment
    for key in ("FOUNDRY_PROJECT_ENDPOINT", "AZURE_AI_PROJECT_ENDPOINT"):
        value = (env.get(key) or "").strip()
        if value:
            return value
    return "unknown"


def answer(environment: Mapping[str, str] | None = None) -> str:
    return f"Hello! Sample agent running on project {project_endpoint(environment)}."


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
        if length > 0:
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
