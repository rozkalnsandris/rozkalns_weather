from pathlib import Path


HANDOFF = Path(__file__).resolve().parents[1] / "docs" / "RPI5_PUBLIC_RUNTIME_HANDOFF.md"


def test_runtime_handoff_keeps_completed_public_acceptance_and_current_now_split():
    text = HANDOFF.read_text(encoding="utf-8")

    assert "Final public acceptance is **COMPLETE** through #176/#177." in text
    assert "10-minute `DWD_CURRENT` feed" in text
    assert "hourly DWD 05480 truth serves verification/history" in text
    assert "Legacy `station_10416` cannot satisfy current-now health." in text


def test_runtime_handoff_routes_weathernext_to_current_private_gate():
    text = HANDOFF.read_text(encoding="utf-8")

    assert "#168 is **completed**" in text
    assert "#122 is the next private WeatherNext gate" in text
    assert "fresh exact owner authorization" in text
    assert "explicit bytes cap" in text
    assert "no production SQLite/schema/corpus/checkpoint write" in text

    stale_prerequisites = (
        "#168 must migrate",
        "before #168 completes",
        "No private query should be executed against the stale first-access location contract",
    )
    for stale in stale_prerequisites:
        assert stale not in text
