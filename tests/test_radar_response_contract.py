from __future__ import annotations

from datetime import datetime, timezone
import json

from rozkalns_weather.radar_warnings import (
    PNG_SIGNATURE,
    dwd_radar_map_url,
    fetch_dwd_radar_map_png,
    fetch_radar_point,
    normalize_dwd_wms_time,
)


NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def test_radar_response_exposes_timeline_without_coordinates_or_raw_grid() -> None:
    def fake_fetcher(url: str, params: dict[str, object]) -> dict[str, object]:
        assert url == "https://api.brightsky.dev/radar"
        assert params == {
            "lat": 50.0,
            "lon": 8.0,
            "distance": 20_000,
            "format": "plain",
            "date": "2026-09-28T11:00:00Z",
            "last_date": "2026-09-28T14:00:00Z",
            "tz": "UTC",
        }
        return {
            "radar": [
                {
                    "timestamp": "2026-09-28T11:55:00+00:00",
                    "source": "RADOLAN::RV::observed-fixture",
                    "precipitation_5": [[0, 1], [2, 3]],
                },
                {
                    "timestamp": "2026-09-28T12:30:00+00:00",
                    "source": "RADOLAN::RV::nowcast-fixture",
                    "precipitation_5": [[0, 25], [0, 0]],
                },
            ],
            "geometry": {"coordinates": [[[7.1, 50.1], [8.9, 51.9]]]},
            "bbox": [1, 2, 3, 4],
            "latlon_position": {"x": 99.5, "y": 100.5},
        }

    result = fetch_radar_point(
        lat=50.0,
        lon=8.0,
        center_location_id="home",
        fetcher=fake_fetcher,
        now=NOW,
    )

    assert [frame["kind"] for frame in result["frames"]] == [
        "radar_observed",
        "radar_nowcast",
    ]
    assert all("raster" not in frame for frame in result["frames"])
    assert result["map_contract"]["coordinates_exposed"] is False

    rendered = json.dumps(result, sort_keys=True)
    assert "precipitation_5" not in rendered
    assert '"geometry":' not in rendered
    assert '"bbox":' not in rendered
    assert '"latlon_position":' not in rendered
    assert "7.1" not in rendered
    assert "8.9" not in rendered


def test_empty_radar_response_keeps_simple_timeline_contract() -> None:
    def fake_fetcher(_url: str, _params: dict[str, object]) -> dict[str, object]:
        return {"radar": []}

    result = fetch_radar_point(
        lat=50.0,
        lon=8.0,
        center_location_id="station_05480",
        fetcher=fake_fetcher,
        now=NOW,
    )

    assert result["state"] == "no_radar_frames"
    assert result["frames"] == []


def test_dwd_radar_map_uses_fixed_layers_and_normalized_utc_time() -> None:
    assert normalize_dwd_wms_time("2026-09-28T12:30:00+00:00") == "2026-09-28T12:30:00.000Z"
    url = dwd_radar_map_url(
        at="2026-09-28T12:30:00+00:00",
        west=7.4,
        south=51.4,
        east=7.8,
        north=51.7,
    )
    assert "layers=dwd%3Abluemarble%2Cdwd%3ANiederschlagsradar" in url
    assert "styles=%2C" in url
    assert "crs=EPSG%3A3857" in url
    assert "width=640" in url
    assert "height=640" in url
    assert "transparent=FALSE" in url
    assert "time=2026-09-28T12%3A30%3A00.000Z" in url


def test_dwd_radar_map_rejects_oversized_view_and_non_png() -> None:
    try:
        dwd_radar_map_url(
            at="2026-09-28T12:30:00Z",
            west=5.0,
            south=50.0,
            east=8.0,
            north=51.0,
        )
    except ValueError as exc:
        assert "too large" in str(exc)
    else:
        raise AssertionError("oversized radar view must be rejected")

    def fake_bytes(_url: str) -> bytes:
        return b"not-a-png"

    try:
        fetch_dwd_radar_map_png(
            at="2026-09-28T12:30:00Z",
            west=7.4,
            south=51.4,
            east=7.8,
            north=51.7,
            fetcher=fake_bytes,
        )
    except ValueError as exc:
        assert "PNG" in str(exc)
    else:
        raise AssertionError("non-PNG radar response must be rejected")

    assert PNG_SIGNATURE.startswith(b"\x89PNG")
