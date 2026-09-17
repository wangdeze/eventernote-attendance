import json
import tempfile
import unittest
from pathlib import Path

from scripts.fetch_attendance import (
    ActorCandidate,
    EventRecord,
    EventernoteClient,
    main,
    match_events,
    parse_actor_search_results,
    parse_event_list,
)


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


if __name__ == "__main__":
    unittest.main()
