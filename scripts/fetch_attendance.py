from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.eventernote.com"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
PAGE_SIZE = 100
MAX_PAGES = 30
REQUEST_DELAY_RANGE = (2.0, 5.0)
REQUEST_TIMEOUT = 30


class AnalyzerError(Exception):
    """Base class for expected analysis failures."""


class FetchError(AnalyzerError):
    """Raised when Eventernote cannot be fetched."""


class ParseError(AnalyzerError):
    """Raised when Eventernote HTML cannot be parsed."""


class ActorResolutionError(AnalyzerError):
    """Raised when the actor name cannot be resolved safely."""


@dataclass(frozen=True)
class ActorCandidate:
    id: str
    name: str
    url: str


@dataclass(frozen=True)
class EventRecord:
    id: str | None
    date: str
    title: str
    venue: str
    url: str
    actors: tuple[str, ...]

    @property
    def fallback_key(self) -> tuple[str, ...]:
        return (
            "fallback",
            self.date,
            normalize_text(self.title),
            normalize_text(self.venue),
        )

    @property
    def match_keys(self) -> tuple[tuple[str, ...], ...]:
        keys: list[tuple[str, ...]] = [self.fallback_key]
        if self.id:
            keys.insert(0, ("id", self.id))
        return tuple(keys)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EventernoteClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        min_delay: float = REQUEST_DELAY_RANGE[0],
        max_delay: float = REQUEST_DELAY_RANGE[1],
        timeout: int = REQUEST_TIMEOUT,
        max_pages: int = MAX_PAGES,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_delay = min_delay
        self.max_delay = max(max_delay, min_delay)
        self.timeout = timeout
        self.max_pages = max_pages
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def resolve_actor(self, actor_name: str) -> ActorCandidate:
        search_url = f"{self.base_url}/actors/search?{urlencode({'keyword': actor_name})}"
        html = self.fetch_text(search_url)
        candidates = parse_actor_search_results(html)
        if not candidates:
            raise ActorResolutionError(f'无法解析艺人名称："{actor_name}"')

        requested = normalize_text(actor_name)
        exact = [candidate for candidate in candidates if normalize_text(candidate.name) == requested]
        if len(exact) == 1:
            return exact[0]
        if not exact and len(candidates) == 1:
            return candidates[0]

        preview = ", ".join(f"{candidate.name}({candidate.id})" for candidate in (exact or candidates)[:5])
        raise ActorResolutionError(
            f'艺人名称解析结果不唯一："{actor_name}"。候选：{preview or "无"}'
        )

    def fetch_actor_events(self, actor: ActorCandidate, year: int) -> tuple[list[EventRecord], list[str]]:
        return self._fetch_event_pages(f"{actor.url}/events", year, label=f"艺人 {actor.name}")

    def fetch_user_events(self, user_id: str, year: int) -> tuple[list[EventRecord], list[str]]:
        return self._fetch_event_pages(f"{self.base_url}/users/{user_id}/events", year, label=f"用户 {user_id}")

    def _fetch_event_pages(self, page_url: str, year: int, *, label: str) -> tuple[list[EventRecord], list[str]]:
        events: list[EventRecord] = []
        warnings: list[str] = []
        seen: set[tuple[str, ...]] = set()

        for page in range(1, self.max_pages + 1):
            html = self.fetch_text(page_url, params={"page": page, "limit": PAGE_SIZE, "year": year})
            raw_event_count = count_event_blocks(html)
            if raw_event_count == 0:
                break
            page_events = parse_event_list(html, year)

            for event in page_events:
                if any(key in seen for key in event.match_keys):
                    continue
                seen.update(event.match_keys)
                events.append(event)

            if raw_event_count < PAGE_SIZE:
                break
            self.polite_sleep()
        else:
            warnings.append(f"{label} 超过最大分页数 {self.max_pages}，结果可能不完整。")

        if not events:
            warnings.append(f"{label} 在 {year} 年没有解析到活动，或页面结构已变化。")

        return sorted(events, key=lambda event: (event.date, event.title, event.venue)), warnings

    def fetch_text(self, url: str, params: dict[str, object] | None = None) -> str:
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FetchError(f"请求失败：{url} ({exc})") from exc

        if response.status_code == 404:
            raise FetchError(f"页面不存在：{response.url}")
        if response.status_code >= 400:
            raise FetchError(f"请求失败：{response.status_code} {response.reason} ({response.url})")
        if "text/html" not in response.headers.get("content-type", ""):
            raise ParseError(f"返回内容不是 HTML：{response.url}")
        return response.text

    def polite_sleep(self) -> None:
        time.sleep(random.uniform(self.min_delay, self.max_delay))


def parse_actor_search_results(html: str) -> list[ActorCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[ActorCandidate] = []
    seen_ids: set[str] = set()

    for link in soup.select('a[href*="/actors/"]'):
        href = link.get("href", "")
        match = re.search(r"/actors(?:/[^/]+)?/(\d+)", href)
        if not match:
            continue
        actor_id = match.group(1)
        if actor_id in seen_ids:
            continue
        name = direct_text(link) or link.get_text(" ", strip=True)
        name = re.sub(r"\s+\d+$", "", name).strip()
        if not name:
            continue
        seen_ids.add(actor_id)
        candidates.append(
            ActorCandidate(
                id=actor_id,
                name=name,
                url=urljoin(BASE_URL, href),
            )
        )
    return candidates


def direct_text(element) -> str:
    parts = [part.strip() for part in element.find_all(string=True, recursive=False)]
    return " ".join(part for part in parts if part).strip()


def parse_event_list(html: str, year: int) -> list[EventRecord]:
    soup = BeautifulSoup(html, "html.parser")
    items = select_event_blocks(soup)
    events: list[EventRecord] = []

    for item in items:
        link = item.select_one('div.event h4 a[href*="/events/"]') or item.select_one('a[href*="/events/"]')
        if link is None:
            continue

        href = link.get("href", "")
        event_id_match = re.search(r"/events/(\d+)", href)
        date = parse_event_date(item)
        if not date or int(date[:4]) != year:
            continue

        title = link.get_text(" ", strip=True)
        if not title:
            continue

        venue = parse_venue(item)
        actors = tuple(dict.fromkeys(actor.get_text(" ", strip=True) for actor in item.select('div.actor a[href*="/actors/"]') if actor.get_text(" ", strip=True)))
        events.append(
            EventRecord(
                id=event_id_match.group(1) if event_id_match else None,
                date=date,
                title=title,
                venue=venue,
                url=urljoin(BASE_URL, href),
                actors=actors,
            )
        )

    return events


def select_event_blocks(soup: BeautifulSoup) -> list:
    return soup.select("div.gb_event_list li.clearfix") or soup.select("div.gb_event_list > ul > li")


def count_event_blocks(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    return len(select_event_blocks(soup))


def parse_event_date(item) -> str | None:
    node = item.select_one("div.date") or item.find(class_=re.compile("date"))
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    patterns = [
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{4})/(\d{2})/(\d{2})",
        r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def parse_venue(item) -> str:
    for place in item.select("div.place"):
        link = place.select_one('a[href*="/places/"]')
        text = (link.get_text(" ", strip=True) if link else place.get_text(" ", strip=True)).strip()
        cleaned = re.sub(r"^(会場|場所)[:：]\s*", "", text)
        if cleaned:
            return cleaned
    return "未定"


def match_events(actor_events: Iterable[EventRecord], user_events: Iterable[EventRecord]) -> list[dict[str, object]]:
    user_keys = {key for event in user_events for key in event.match_keys}
    rows: list[dict[str, object]] = []
    for event in actor_events:
        rows.append(
            {
                "id": event.id,
                "date": event.date,
                "title": event.title,
                "venue": event.venue,
                "url": event.url,
                "actors": list(event.actors),
                "attended": any(key in user_keys for key in event.match_keys),
            }
        )
    return rows


def analyze_attendance(
    *,
    user_id: str,
    actor_name: str,
    year: int,
    client: EventernoteClient | None = None,
) -> dict[str, object]:
    client = client or EventernoteClient()
    actor = client.resolve_actor(actor_name)
    actor_events, actor_warnings = client.fetch_actor_events(actor, year)
    user_events, user_warnings = client.fetch_user_events(user_id, year)
    matched_events = match_events(actor_events, user_events)
    attended_events = sum(1 for event in matched_events if event["attended"])
    total_actor_events = len(matched_events)

    return {
        "status": "success",
        "generated_at": current_timestamp(),
        "requested_actor_name": actor_name,
        "user_id": user_id,
        "actor_name": actor.name,
        "actor_id": actor.id,
        "actor_url": actor.url,
        "year": year,
        "total_actor_events": total_actor_events,
        "attended_events": attended_events,
        "attendance_rate": round(attended_events / total_actor_events, 4) if total_actor_events else 0.0,
        "warnings": [*actor_warnings, *user_warnings],
        "events": matched_events,
    }


def write_result(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_error_result(user_id: str, actor_name: str, year: int | str, exc: Exception) -> dict[str, object]:
    return {
        "status": "error",
        "generated_at": current_timestamp(),
        "requested_actor_name": actor_name,
        "user_id": user_id,
        "actor_name": actor_name,
        "year": year,
        "warnings": [],
        "events": [],
        "error": {
            "type": exc.__class__.__name__,
            "message": str(exc),
        },
    }


def parse_year(value: str) -> int:
    if not re.fullmatch(r"\d{4}", value.strip()):
        raise AnalyzerError("年份必须是 4 位数字，例如 2025。")
    return int(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Eventernote attendance for one user, one actor, and one year.")
    parser.add_argument("--user-id", required=True, help="Eventernote user ID")
    parser.add_argument("--actor-name", required=True, help="Eventernote actor name")
    parser.add_argument("--year", required=True, help="Target year")
    parser.add_argument("--output", default="data/latest-result.json", help="JSON output path")
    parser.add_argument("--min-delay", type=float, default=REQUEST_DELAY_RANGE[0], help="Minimum request delay in seconds")
    parser.add_argument("--max-delay", type=float, default=REQUEST_DELAY_RANGE[1], help="Maximum request delay in seconds")
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT, help="HTTP timeout in seconds")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="Maximum pages to scan for each list")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        year = parse_year(args.year)
        client = EventernoteClient(
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            timeout=args.timeout,
            max_pages=args.max_pages,
        )
        result = analyze_attendance(
            user_id=args.user_id,
            actor_name=args.actor_name,
            year=year,
            client=client,
        )
        print(
            f"分析完成: user={result['user_id']} actor={result['actor_name']} year={result['year']} "
            f"rate={result['attendance_rate']}"
        )
    except Exception as exc:  # noqa: BLE001 - persist graceful error output for Pages.
        result = build_error_result(args.user_id, args.actor_name, args.year, exc)
        print(f"分析失败: {exc}", file=sys.stderr)

    write_result(Path(args.output), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
