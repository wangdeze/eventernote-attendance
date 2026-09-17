import json
import http.client
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from scripts.fetch_attendance import (
    ActorCandidate,
    AnalyzerError,
    EventRecord,
    EventernoteClient,
    main,
    match_events,
    parse_year,
    parse_actor_search_results,
    parse_event_list,
)
from v2.backend.api import build_analysis_response
from v2.backend.server import AnalyzeHandler


class ParseActorSearchResultsTests(unittest.TestCase):
    def test_extracts_unique_actor_candidates(self) -> None:
        html = """
        <html><body>
          <div class="container"><div><div class="span8 page">
            <ul>
              <li><a href="/actors/suzuki-aina/11198">鈴木愛奈</a></li>
              <li><a href="/actors/suzuki-aina/11198">鈴木愛奈</a></li>
              <li><a href="/actors/another/22222">別の人</a></li>
            </ul>
          </div></div></div>
        </body></html>
        """

        candidates = parse_actor_search_results(html)

        self.assertEqual(
            candidates,
            [
                ActorCandidate(id="11198", name="鈴木愛奈", url="https://www.eventernote.com/actors/suzuki-aina/11198"),
                ActorCandidate(id="22222", name="別の人", url="https://www.eventernote.com/actors/another/22222"),
            ],
        )

    def test_builds_candidate_urls_from_provided_base_url(self) -> None:
        html = """
        <html><body>
          <ul>
            <li><a href="/actors/suzuki-aina/11198">鈴木愛奈</a></li>
          </ul>
        </body></html>
        """

        candidates = parse_actor_search_results(html, base_url="https://staging.example")

        self.assertEqual(candidates[0].url, "https://staging.example/actors/suzuki-aina/11198")


class ParseEventListTests(unittest.TestCase):
    def test_parses_only_requested_year(self) -> None:
        html = """
        <html><body>
          <div class="gb_event_list clearfix">
            <ul>
              <li class="clearfix">
                <div class="date"><p>2025-03-15(土)</p></div>
                <div class="event"><h4><a href="/events/100">Aqours Event</a></h4></div>
                <div class="place"><a href="/places/1">Tokyo Dome</a></div>
                <div class="actor"><ul><li><a href="/actors/suzuki-aina/11198">鈴木愛奈</a></li></ul></div>
              </li>
              <li class="clearfix">
                <div class="date"><p>2024-12-31(火)</p></div>
                <div class="event"><h4><a href="/events/101">Old Event</a></h4></div>
                <div class="place"><a href="/places/2">Osaka Hall</a></div>
              </li>
            </ul>
          </div>
        </body></html>
        """

        events = parse_event_list(html, 2025)

        self.assertEqual(
            events,
            [
                EventRecord(
                    id="100",
                    date="2025-03-15",
                    title="Aqours Event",
                    venue="Tokyo Dome",
                    url="https://www.eventernote.com/events/100",
                    actors=("鈴木愛奈",),
                )
            ],
        )

    def test_builds_event_urls_from_provided_base_url(self) -> None:
        html = """
        <html><body>
          <div class="gb_event_list clearfix">
            <ul>
              <li class="clearfix">
                <div class="date"><p>2025-03-15(土)</p></div>
                <div class="event"><h4><a href="/events/100">Aqours Event</a></h4></div>
                <div class="place"><a href="/places/1">Tokyo Dome</a></div>
              </li>
            </ul>
          </div>
        </body></html>
        """

        events = parse_event_list(html, 2025, base_url="https://staging.example")

        self.assertEqual(events[0].url, "https://staging.example/events/100")


class MatchEventsTests(unittest.TestCase):
    def test_marks_attended_by_event_id(self) -> None:
        actor_events = [
            EventRecord(id="100", date="2025-03-15", title="A", venue="Tokyo", url="https://www.eventernote.com/events/100", actors=("鈴木愛奈",)),
            EventRecord(id="200", date="2025-06-01", title="B", venue="Nagoya", url="https://www.eventernote.com/events/200", actors=("鈴木愛奈",)),
        ]
        user_events = [
            EventRecord(id="200", date="2025-06-01", title="B", venue="Nagoya", url="https://www.eventernote.com/events/200", actors=("鈴木愛奈",)),
        ]

        rows = match_events(actor_events, user_events)

        self.assertEqual([row["attended"] for row in rows], [False, True])

    def test_marks_attended_by_fallback_key_without_event_id(self) -> None:
        actor_events = [
            EventRecord(id=None, date="2025-08-10", title="Special Live", venue="Zepp Haneda", url="https://www.eventernote.com/events/special", actors=("鈴木愛奈",)),
        ]
        user_events = [
            EventRecord(id=None, date="2025-08-10", title="Special   Live", venue="Zepp Haneda", url="", actors=()),
        ]

        rows = match_events(actor_events, user_events)

        self.assertEqual([row["attended"] for row in rows], [True])

    def test_marks_attended_when_only_one_side_has_event_id(self) -> None:
        actor_events = [
            EventRecord(id="300", date="2025-09-01", title="Aina Talk", venue="Pacifico", url="https://www.eventernote.com/events/300", actors=("鈴木愛奈",)),
        ]
        user_events = [
            EventRecord(id=None, date="2025-09-01", title="Aina  Talk", venue="Pacifico", url="", actors=()),
        ]

        rows = match_events(actor_events, user_events)

        self.assertEqual([row["attended"] for row in rows], [True])

    def test_does_not_use_fallback_when_both_sides_have_different_ids(self) -> None:
        actor_events = [
            EventRecord(id="100", date="2025-03-15", title="Same Event", venue="Tokyo", url="https://www.eventernote.com/events/100", actors=()),
        ]
        user_events = [
            EventRecord(id="200", date="2025-03-15", title="Same Event", venue="Tokyo", url="https://www.eventernote.com/events/200", actors=()),
        ]

        rows = match_events(actor_events, user_events)

        self.assertEqual([row["attended"] for row in rows], [False])


def build_events_html(entries) -> str:
    items = []
    for event_id, date_text, title, venue in entries:
        href = f"/events/{event_id}" if event_id is not None else "/events/special"
        items.append(
            f'''
            <li class="clearfix">
              <div class="date"><p>{date_text}</p></div>
              <div class="event"><h4><a href="{href}">{title}</a></h4></div>
              <div class="place"><a href="/places/1">{venue}</a></div>
            </li>
            '''
        )
    return f'<html><body><div class="gb_event_list clearfix"><ul>{"".join(items)}</ul></div></body></html>'


class FakeEventernoteClient(EventernoteClient):
    def __init__(self, pages_by_number: dict[int, str]) -> None:
        super().__init__(min_delay=0, max_delay=0, max_pages=5)
        self.pages_by_number = pages_by_number
        self.pages_requested: list[int] = []

    def fetch_text(self, url: str, params=None) -> str:
        page = int((params or {}).get("page", 1))
        self.pages_requested.append(page)
        return self.pages_by_number.get(page, "<html><body></body></html>")

    def polite_sleep(self) -> None:
        return


class EventernoteClientTests(unittest.TestCase):
    def test_continues_pagination_when_page_has_few_target_year_matches(self) -> None:
        page_one_entries = [(1000 + index, "2024-12-01(月)", f"Other {index}", "Venue") for index in range(99)]
        page_one_entries.append((2001, "2025-01-10(金)", "Target Page 1", "Venue A"))
        client = FakeEventernoteClient(
            {
                1: build_events_html(page_one_entries),
                2: build_events_html([(2002, "2025-02-11(火)", "Target Page 2", "Venue B")]),
            }
        )

        events, warnings = client.fetch_user_events("Tokuzawa353567", 2025)

        self.assertEqual([event.title for event in events], ["Target Page 1", "Target Page 2"])
        self.assertEqual(client.pages_requested, [1, 2])
        self.assertEqual(warnings, [])

    def test_keeps_distinct_events_with_different_ids(self) -> None:
        client = FakeEventernoteClient(
            {
                1: build_events_html(
                    [
                        (100, "2025-03-15(土)", "Duplicate Title", "Same Venue"),
                        (200, "2025-03-15(土)", "Duplicate Title", "Same Venue"),
                    ]
                )
            }
        )

        events, warnings = client.fetch_actor_events(
            ActorCandidate(id="11198", name="鈴木愛奈", url="https://www.eventernote.com/actors/suzuki-aina/11198"),
            2025,
        )

        self.assertEqual([event.id for event in events], ["100", "200"])
        self.assertEqual(warnings, [])


class MainTests(unittest.TestCase):
    def test_writes_structured_error_for_invalid_year(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "result.json"

            exit_code = main(
                [
                    "--user-id",
                    "Tokuzawa353567",
                    "--actor-name",
                    "鈴木愛奈",
                    "--year",
                    "20xx",
                    "--output",
                    str(output),
                ]
            )

            result = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["year"], "20xx")
        self.assertEqual(result["error"]["type"], "AnalyzerError")


class ParseYearTests(unittest.TestCase):
    def test_rejects_year_out_of_supported_range(self) -> None:
        with self.assertRaises(AnalyzerError):
            parse_year("1999")


class StubAnalyzeClient(EventernoteClient):
    def __init__(self) -> None:
        super().__init__(min_delay=0, max_delay=0)

    def resolve_actor(self, actor_name: str) -> ActorCandidate:
        return ActorCandidate(id="11198", name=actor_name, url="https://www.eventernote.com/actors/suzuki-aina/11198")

    def fetch_actor_events(self, actor: ActorCandidate, year: int) -> tuple[list[EventRecord], list[str]]:
        return (
            [
                EventRecord(
                    id="100",
                    date=f"{year}-03-15",
                    title="Aqours Event",
                    venue="Tokyo Dome",
                    url="https://www.eventernote.com/events/100",
                    actors=(actor.name,),
                )
            ],
            [],
        )

    def fetch_user_events(self, user_id: str, year: int) -> tuple[list[EventRecord], list[str]]:
        return (
            [
                EventRecord(
                    id="100",
                    date=f"{year}-03-15",
                    title="Aqours Event",
                    venue="Tokyo Dome",
                    url="https://www.eventernote.com/events/100",
                    actors=("鈴木愛奈",),
                )
            ],
            [],
        )


class BrokenAnalyzeClient(EventernoteClient):
    def __init__(self) -> None:
        super().__init__(min_delay=0, max_delay=0)

    def resolve_actor(self, actor_name: str) -> ActorCandidate:
        raise AnalyzerError("上游抓取失败")


class ApiResponseTests(unittest.TestCase):
    def test_rejects_missing_request_fields(self) -> None:
        status_code, result = build_analysis_response({"user_id": "", "actor_name": "鈴木愛奈", "year": "2025"})

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["type"], "AnalyzerError")

    def test_returns_live_analysis_payload(self) -> None:
        status_code, result = build_analysis_response(
            {"user_id": "Tokuzawa353567", "actor_name": "鈴木愛奈", "year": "2025"},
            client=StubAnalyzeClient(),
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["attended_events"], 1)
        self.assertEqual(result["total_actor_events"], 1)
        self.assertEqual(result["attendance_rate"], 1.0)

    def test_rejects_non_object_payload(self) -> None:
        status_code, result = build_analysis_response("not-a-dict")

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["type"], "AnalyzerError")

    def test_returns_bad_gateway_for_upstream_failure(self) -> None:
        status_code, result = build_analysis_response(
            {"user_id": "Tokuzawa353567", "actor_name": "鈴木愛奈", "year": "2025"},
            client=BrokenAnalyzeClient(),
        )

        self.assertEqual(status_code, 502)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["type"], "AnalyzerError")


class AnalyzeHandlerTests(unittest.TestCase):
    def start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), AnalyzeHandler)
        server.allow_origin = ""
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def stop_server(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    def test_returns_json_error_for_malformed_json_body(self) -> None:
        server, thread = self.start_server()
        try:
            connection = http.client.HTTPConnection(*server.server_address)
            connection.request("POST", "/api/analyze", body="{", headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()
            self.stop_server(server, thread)

        self.assertEqual(response.status, 400)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["message"], "请求体不是合法 JSON。")

    def test_returns_json_error_for_invalid_content_length(self) -> None:
        server, thread = self.start_server()
        try:
            with socket.create_connection(server.server_address, timeout=5) as sock:
                sock.sendall(
                    (
                        "POST /api/analyze HTTP/1.1\r\n"
                        f"Host: {server.server_address[0]}:{server.server_address[1]}\r\n"
                        "Content-Type: application/json\r\n"
                        "Content-Length: abc\r\n"
                        "Connection: close\r\n\r\n"
                    ).encode("utf-8")
                )
                response = b""
                while chunk := sock.recv(4096):
                    response += chunk
        finally:
            self.stop_server(server, thread)

        body = json.loads(response.split(b"\r\n\r\n", 1)[1].decode("utf-8"))
        self.assertIn(b"400 Bad Request", response)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["message"], "Content-Length 请求头无效。")


if __name__ == "__main__":
    unittest.main()
