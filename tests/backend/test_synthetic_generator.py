import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))
sys.path.insert(0, str(Path(__file__).parents[2] / "backend"))

from scripts.generate_synthetic_analytics import (  # noqa: E402
    Counts,
    CatalogueParser,
    dataset_key,
    event_request_id,
    planned_counts,
    synthetic_email,
    _event_date,
    SourceEvent,
)


def test_same_seed_has_same_namespace_and_keys():
    assert dataset_key(42) == dataset_key(42)
    assert dataset_key(42) != dataset_key(43)
    assert (
        synthetic_email(dataset_key(42), 1)
        == "synthetic-" + dataset_key(42) + "-user000001@example.test"
    )
    assert event_request_id(dataset_key(42), 7).endswith("-000007")


def test_planned_counts_are_explicit_and_configurable():
    counts = Counts(
        users=2, events=3, interactions=4, favorites=5, reminders=6, reviews=7
    )
    assert planned_counts(counts) == {
        "users": 2,
        "events": 3,
        "event_analytics": 4,
        "favorites": 5,
        "reminders": 6,
        "ratings": 7,
        "comments": 7,
    }


def test_catalogue_parser_reads_titles_dates_and_links_without_people():
    parser = CatalogueParser("https://nu.edu.kz/events")
    parser.feed(
        '<h2>July</h2><a href="/event/2"><img src="/images/workshop.jpg"></a><h3><a href="/event/2">A public workshop</a></h3><div>05.08.2026</div>'
    )
    assert parser.items[0].title == "A public workshop"
    assert parser.items[0].event_date == date(2026, 8, 5)
    assert parser.items[0].url == "https://nu.edu.kz/event/2"
    assert parser.items[0].image_url == "https://nu.edu.kz/images/workshop.jpg"
    assert "person" not in parser.items[0].title.lower()


def test_catalogue_parser_reads_filter_cards():
    parser = CatalogueParser("https://nu.edu.kz/events")
    parser.feed(
        '<article class="nu-event-card"><a href="/event/3">'
        '<img class="wp-post-image" src="/images/event.jpg"></a>'
        '<div class="nu-event-title"><a href="/event/3">Real Event</a></div>'
        "<span>Fri, Oct 16, 2026</span></article>"
    )

    assert parser.items[0].title == "Real Event"
    assert parser.items[0].event_date == date(2026, 10, 16)
    assert parser.items[0].image_url == "https://nu.edu.kz/images/event.jpg"


def test_past_catalogue_dates_are_rebased_deterministically():
    event = SourceEvent("Past Event", date(2025, 1, 1), "https://nu.edu.kz/event")

    assert _event_date(2, [event], None, date(2026, 7, 21)) == date(2026, 8, 3)
