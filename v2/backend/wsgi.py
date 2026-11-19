from __future__ import annotations

import json
from http import HTTPStatus
from wsgiref.types import StartResponse, WSGIEnvironment

from scripts.fetch_attendance import AnalyzerError, build_error_result
from v2.backend.api import build_analysis_response

MAX_REQUEST_BODY_BYTES = 16 * 1024


def application(environ: WSGIEnvironment, start_response: StartResponse) -> list[bytes]:
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "")
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")]

    def respond(status: HTTPStatus, payload: dict) -> list[bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(f"{status.value} {status.phrase}", headers + [("Content-Length", str(len(body)))])
        return [body]

    def error(status: HTTPStatus, message: str) -> list[bytes]:
        return respond(status, build_error_result("", "", "", AnalyzerError(message)))

    if path == "/health" and method == "GET":
        return respond(HTTPStatus.OK, {"status": "ok"})
    if path != "/api/analyze":
        return error(HTTPStatus.NOT_FOUND, "接口不存在。")
    if method != "POST":
        headers.append(("Allow", "POST"))
        return error(HTTPStatus.METHOD_NOT_ALLOWED, "请使用 POST 请求。")
    if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
        return error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "请使用 application/json 请求体。")
    if not environ.get("CONTENT_LENGTH"):
        return error(HTTPStatus.LENGTH_REQUIRED, "请求必须提供 Content-Length 请求头。")
    try:
        content_length = int(environ["CONTENT_LENGTH"])
    except ValueError:
        return error(HTTPStatus.BAD_REQUEST, "Content-Length 请求头无效。")
    if content_length < 0:
        return error(HTTPStatus.BAD_REQUEST, "Content-Length 请求头无效。")
    if content_length > MAX_REQUEST_BODY_BYTES:
        return error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "请求体过大。")

    raw_body = environ["wsgi.input"].read(content_length)
    if len(raw_body) != content_length:
        return error(HTTPStatus.BAD_REQUEST, "请求体长度与 Content-Length 不一致。")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return error(HTTPStatus.BAD_REQUEST, "请求体不是合法 JSON。")

    status, result = build_analysis_response(payload)
    return respond(HTTPStatus(status), result)
