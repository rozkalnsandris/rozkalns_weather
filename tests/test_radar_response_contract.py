from __future__ import annotations

from datetime import datetime, timezone
import json

from rozkalns_weather.radar_warnings import fetch_radar_point


NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def test_radar_response_exposes_timeline_metadata_but_not_grid_or_geometry() -> None:
    def fake_fetcher(url: str, params: dict[str, object]) -> dict[str, object]:
        assert url == "https://api.brightsky.dev/radar"
        assert params == {"lat": 50.0, "lon": 8.0}
        return {
            "radar": [
                {
                    "timestamp": "2026-09-28T11:55:00+00:00",
                    "source": "RADOLAN::RV::observed-fixture",
                    "precipitation_5": "synthetic-private-grid-material",
                    "provider_extra": "must-not-leak",
                },
                {
                    "timestamp": "2026-09-28T12:30:00+00:00",
                    "source": "RADOLAN::RV::nowcast-fixture",
                    "precipitation_5": [[1, 2], [3, 4]],
                },
            ],
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[7.1, 50.1], [8.9, 50.1], [8.9, 51.9], [7.1, 51.9], [7.1, 50.1]]],
            },
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

    assert result["frames"] == [
        {
            "timestamp": "2026-09-28T11:55:00+00:00",
            "kind": "radar_observed",
            "source": "RADOLAN::RV::observed-fixture",
        },
        {
            "timestamp": "2026-09-28T12:30:00+00:00",
            "kind": "radar_nowcast",
            "source": "RADOLAN::RV::nowcast-fixture",
        },
    ]

    contract = result["map_contract"]
    assert contract["center_location_id"] == "home"
    assert contract["coordinates_exposed"] is False
    assert contract["geometry_exposed"] is False
    assert contract["raw_payload_exposed"] is False
    assert contract["rendering_contract"] == {
        "state": "metadata_only",
        "raster_rendering_available": False,
        "reason_code": "RADAR_RASTER_CONTRACT_PENDING",
        "required_fields": [
            "encoding",
            "dimensions",
            "projection",
            "precipitation_unit",
            "nodata",
        ],
    }

    rendered = json.dumps(result, sort_keys=True)
    assert "precipitation_5" not in rendered
    assert "synthetic-private-grid-material" not in rendered
    assert "provider_extra" not in rendered
    assert "geometry" not in result
    assert "bbox" not in rendered
    assert "latlon_position" not in rendered
    assert "7.1" not in rendered
    assert "8.9" not in rendered


def test_empty_radar_response_keeps_metadata_only_rendering_contract() -> None:
    def fake_fetcher(_url: str, _params: dict[str, object]) -> dict[str, object]:
        return {"radar": [], "geometry": {"coordinates": [[7.0, 50.0]]}}

    result = fetch_radar_point(
        lat=50.0,
        lon=8.0,
        center_location_id="station_05480",
        fetcher=fake_fetcher,
        now=NOW,
    )

    assert result["state"] == "no_radar_frames"
    assert result["frames"] == []
    assert result["map_contract"]["rendering_contract"]["raster_rendering_available"] is False
    assert "geometry" not in result
