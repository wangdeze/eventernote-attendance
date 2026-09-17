from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.fetch_attendance import AnalyzerError, build_error_result
from v2.backend.api import build_analysis_response

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
API_PATH = "/api/analyze"
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


class AnalyzeHandler(BaseHTTPRequestHandler):
    server_version = "EventernoteAttendanceV2/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler name.
        if self.path.rstrip("/") != API_PATH:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers(content_type="application/json; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name.
        if self.path.rstrip("/") == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name.
        if self.path.rstrip("/") != API_PATH:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                build_error_result("", "", "", AnalyzerError("请求体不是合法 JSON。")),
            )
            return

        status_code, result = build_analysis_response(payload)
        self._send_json(status_code, result)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - stdlib signature.
        return

    def _send_common_headers(self, *, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)

    def _send_json(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self._send_common_headers(content_type="application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the v2 Eventernote attendance analysis API.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), AnalyzeHandler)
    print(f"Serving Eventernote v2 API on http://{args.host}:{args.port}{API_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
