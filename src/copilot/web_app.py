#!/usr/bin/env python3
"""Serve the dashboard and local copilot as one localhost-only demo app."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .service import CopilotService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = PROJECT_ROOT / "copilot" / "index.html"
DASHBOARD_PATH = PROJECT_ROOT / "dashboard" / "kpi_performance_tracker.html"


class CopilotRequestHandler(BaseHTTPRequestHandler):
    service: CopilotService

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[copilot-web] {self.address_string()} - {format % args}")

    def _send_bytes(self, content: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self) -> None:
        if self.path == "/":
            self._send_bytes(INDEX_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if self.path == "/dashboard":
            self._send_bytes(DASHBOARD_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if self.path == "/api/agents":
            self._send_json(
                {
                    "agents": self.service.repository.list_agents(),
                    "provider": self.service.provider.name,
                    "snapshot_generated_at": self.service.repository.snapshot_generated_at,
                }
            )
            return
        if self.path == "/health":
            self._send_json({"status": "ok", "provider": self.service.provider.name})
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 32_000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            response = self.service.ask(
                question=str(payload.get("question", "")),
                agent=str(payload.get("agent", "")),
                stage=str(payload.get("stage", "live")),
            )
            self._send_json(response.to_dict())
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def build_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    service = CopilotService()
    handler = type("BoundCopilotRequestHandler", (CopilotRequestHandler,), {"service": service})
    return ThreadingHTTPServer((host, port), handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("The portfolio copilot binds to localhost only")
    server = build_server(args.host, args.port)
    print(f"Local copilot: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
