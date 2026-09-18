from __future__ import annotations

from http import HTTPStatus
from typing import Any

from scripts.fetch_attendance import AnalyzerError, EventernoteClient, analyze_attendance, build_error_result, parse_year


JsonObject = dict[str, Any]


def extract_request_fields(payload: Any) -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        return "", "", ""

    def clean(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    return clean(payload.get("user_id")), clean(payload.get("actor_name")), clean(payload.get("year"))


def validate_request_payload(payload: Any) -> tuple[str, str, int]:
    user_id, actor_name, year_value = extract_request_fields(payload)
    if not user_id:
        raise AnalyzerError("请填写 Eventernote 用户 ID。")
    if not actor_name:
        raise AnalyzerError("请填写艺人名称。")
    return user_id, actor_name, parse_year(year_value)


def build_analysis_response(
    payload: Any,
    *,
    client: EventernoteClient | None = None,
) -> tuple[int, JsonObject]:
    user_id, actor_name, year_value = extract_request_fields(payload)

    try:
        user_id, actor_name, year = validate_request_payload(payload)
    except Exception as exc:  # noqa: BLE001 - return structured API errors.
        return HTTPStatus.BAD_REQUEST, build_error_result(user_id, actor_name, year_value, exc)

    try:
        return HTTPStatus.OK, analyze_attendance(
            user_id=user_id,
            actor_name=actor_name,
            year=year,
            client=client,
        )
    except Exception as exc:  # noqa: BLE001 - upstream failures should still return JSON.
        return HTTPStatus.BAD_GATEWAY, build_error_result(user_id, actor_name, year, exc)
