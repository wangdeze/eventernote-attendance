import unittest

from scripts.fetch_attendance import ActorCandidate, EventRecord, match_events, parse_actor_search_results, parse_event_list


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


if __name__ == "__main__":
    unittest.main()
