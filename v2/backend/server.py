from __future__ import annotations

import argparse
import json
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from scripts.fetch_attendance import AnalyzerError, build_error_result
from v2.backend.api import build_analysis_response

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_ALLOW_ORIGIN = ""
API_PATH = "/api/analyze"
MAX_REQUEST_BODY_BYTES = 16 * 1024
REQUEST_BODY_TIMEOUT_SECONDS = 15
CORS_HEADERS = {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


class AnalyzeHandler(BaseHTTPRequestHandler):
    server_version = "EventernoteAttendanceV2/0.1"

    @property
    def request_path(self) -> str:
        return urlsplit(self.path).path.rstrip("/") or "/"

    @property
    def allowed_origin(self) -> str:
        return getattr(self.server, "allow_origin", "")

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler name.
        if self.request_path != API_PATH:
            self._send_json(HTTPStatus.NOT_FOUND, build_error_result("", "", "", AnalyzerError("接口不存在。")))
            return
        if not self._is_origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, build_error_result("", "", "", AnalyzerError("当前来源未被允许访问该接口。")))
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers(content_type="application/json; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name.
        if self.request_path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, build_error_result("", "", "", AnalyzerError("接口不存在。")))

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name.
        if self.request_path != API_PATH:
            self._send_json(HTTPStatus.NOT_FOUND, build_error_result("", "", "", AnalyzerError("接口不存在。")))
            return

        if not self._is_origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, build_error_result("", "", "", AnalyzerError("当前来源未被允许访问该接口。")))
            return

        transfer_encoding = (self.headers.get("Transfer-Encoding") or "").strip().lower()
        if transfer_encoding and transfer_encoding != "identity":
            self.close_connection = True
            self._send_json(
                HTTPStatus.NOT_IMPLEMENTED,
                build_error_result("", "", "", AnalyzerError("当前仅支持带 Content-Length 的请求体。")),
            )
            return

        if "Content-Length" not in self.headers:
            self.close_connection = True
            self._send_json(
                HTTPStatus.LENGTH_REQUIRED,
                build_error_result("", "", "", AnalyzerError("请求必须提供 Content-Length 请求头。")),
            )
            return

        try:
            content_length = int(self.headers["Content-Length"])
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                build_error_result("", "", "", AnalyzerError("Content-Length 请求头无效。")),
            )
            return
        if content_length < 0:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                build_error_result("", "", "", AnalyzerError("Content-Length 请求头无效。")),
            )
            return
        if content_length > MAX_REQUEST_BODY_BYTES:
            self.close_connection = True
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                build_error_result("", "", "", AnalyzerError("请求体过大。")),
            )
            return

        original_timeout = self.connection.gettimeout()
        self.connection.settimeout(REQUEST_BODY_TIMEOUT_SECONDS)
        try:
            raw_body = self.rfile.read(content_length)
        except socket.timeout:
            self.close_connection = True
            self._send_json(
                HTTPStatus.REQUEST_TIMEOUT,
                build_error_result("", "", "", AnalyzerError("读取请求体超时。")),
            )
            return
        finally:
            self.connection.settimeout(original_timeout)
        if len(raw_body) != content_length:
            self.close_connection = True
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                build_error_result("", "", "", AnalyzerError("请求体长度与 Content-Length 不一致。")),
            )
            return

        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                build_error_result("", "", "", AnalyzerError("请求体不是合法 JSON。")),
            )
            return

        status_code, result = build_analysis_response(payload)
        self._send_json(status_code, result)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - stdlib signature.
        return

    def _is_origin_allowed(self) -> bool:
        if not self.allowed_origin:
            return True
        origin = (self.headers.get("Origin") or "").strip()
        return bool(origin) and origin == self.allowed_origin

    def _send_common_headers(self, *, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        if self.allowed_origin:
            self.send_header("Vary", "Origin")
        origin = (self.headers.get("Origin") or "").strip()
        if self.allowed_origin and origin == self.allowed_origin:
            self.send_header("Access-Control-Allow-Origin", self.allowed_origin)
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
    parser.add_argument("--allow-origin", default=DEFAULT_ALLOW_ORIGIN, help="Allowed browser Origin for CORS")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), AnalyzeHandler)
    server.allow_origin = args.allow_origin.strip()
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
