from __future__ import annotations

from datetime import datetime, timezone
import json

from rozkalns_weather.radar_warnings import (
    PNG_SIGNATURE,
    dwd_radar_map_url,
    fetch_dwd_radar_map_png,
    fetch_radar_point,
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
    assert result["map_contract"]["image_endpoint"] == "/api/radar/map"
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
    assert result["map_contract"]["image_endpoint"] == "/api/radar/map"


def test_dwd_radar_map_is_one_fixed_composite_wms_image() -> None:
    url = dwd_radar_map_url(
        lat=50.0,
        lon=8.0,
        at="2026-09-28T12:30:00Z",
    )
    assert url.startswith("https://maps.dwd.de/geoserver/dwd/wms?")
    assert "layers=dwd%3Abluemarble%2Cdwd%3ANiederschlagsradar%2Cdwd%3AWarngebiete_Kreise" in url
    assert "styles=%2C%2C" in url
    assert "crs=EPSG%3A3857" in url
    assert "time=2026-09-28T12%3A30%3A00Z" in url
    assert "lat=" not in url
    assert "lon=" not in url


def test_dwd_radar_map_proxy_accepts_only_png() -> None:
    seen: list[str] = []

    def fake_fetcher(url: str) -> bytes:
        seen.append(url)
        return PNG_SIGNATURE + b"fixture"

    payload = fetch_dwd_radar_map_png(
        lat=50.0,
        lon=8.0,
        at="2026-09-28T12:30:00Z",
        fetcher=fake_fetcher,
    )
    assert payload == PNG_SIGNATURE + b"fixture"
    assert len(seen) == 1

    def bad_fetcher(_url: str) -> bytes:
        return b"<ServiceException>bad request</ServiceException>"

    try:
        fetch_dwd_radar_map_png(
            lat=50.0,
            lon=8.0,
            at="2026-09-28T12:30:00Z",
            fetcher=bad_fetcher,
        )
    except ValueError as exc:
        assert "not PNG" in str(exc)
    else:
        raise AssertionError("non-PNG WMS response must fail closed")
