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


def test_radar_response_exposes_validated_local_raster_without_coordinates() -> None:
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
                    "precipitation_5": [[0, 1, 2], [3, 4, 5], [0, 10, 0]],
                    "provider_extra": "must-not-leak",
                },
                {
                    "timestamp": "2026-09-28T12:30:00+00:00",
                    "source": "RADOLAN::RV::nowcast-fixture",
                    "precipitation_5": [[0, 0, 0], [0, 25, 0], [0, 0, 0]],
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

    assert [frame["kind"] for frame in result["frames"]] == [
        "radar_observed",
        "radar_nowcast",
    ]
    assert result["frames"][0]["raster"] == {
        "width": 3,
        "height": 3,
        "values": [[0, 1, 2], [3, 4, 5], [0, 10, 0]],
    }

    contract = result["map_contract"]
    assert contract["center_location_id"] == "home"
    assert contract["coordinates_exposed"] is False
    assert contract["geometry_exposed"] is False
    assert contract["raw_payload_exposed"] is False
    assert contract["rendering_contract"] == {
        "state": "raster_ready",
        "raster_rendering_available": True,
        "encoding": "plain_integer_grid",
        "dimensions": {"width": 3, "height": 3},
        "projection": {
            "id": "DWD_RADOLAN_DE1200",
            "kind": "polar_stereographic",
            "pixel_size_m": 1000,
            "web_mercator_overlay_safe": False,
        },
        "precipitation_unit": {
            "field": "precipitation_5",
            "unit": "mm_per_5_min",
            "scale": 0.01,
        },
        "nodata": {
            "sentinel": None,
            "zero_may_include_uncovered_grid_edge": True,
        },
        "crop_radius_m": 20_000,
        "center_marker": "privacy_safe_crop_center",
        "raster_frame_count": 2,
        "timeline_frame_count": 2,
    }

    rendered = json.dumps(result, sort_keys=True)
    assert "precipitation_5" in rendered
    assert "provider_extra" not in rendered
    assert "geometry" not in result
    assert "bbox" not in rendered
    assert "latlon_position" not in rendered
    assert "7.1" not in rendered
    assert "8.9" not in rendered


def test_inconsistent_raster_dimensions_fail_closed_to_timeline_only() -> None:
    def fake_fetcher(_url: str, _params: dict[str, object]) -> dict[str, object]:
        return {
            "radar": [
                {
                    "timestamp": "2026-09-28T11:55:00Z",
                    "source": "observed",
                    "precipitation_5": [[0, 1], [2, 3]],
                },
                {
                    "timestamp": "2026-09-28T12:30:00Z",
                    "source": "nowcast",
                    "precipitation_5": [[0, 1, 2], [3, 4, 5]],
                },
            ]
        }

    result = fetch_radar_point(
        lat=50.0,
        lon=8.0,
        center_location_id="station_05480",
        fetcher=fake_fetcher,
        now=NOW,
    )

    assert all("raster" not in frame for frame in result["frames"])
    rendering = result["map_contract"]["rendering_contract"]
    assert rendering == {
        "state": "unavailable",
        "raster_rendering_available": False,
        "reason_code": "RADAR_RASTER_VALIDATION_FAILED",
    }


def test_empty_radar_response_keeps_fail_closed_rendering_contract() -> None:
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
    assert result["map_contract"]["rendering_contract"] == {
        "state": "unavailable",
        "raster_rendering_available": False,
        "reason_code": "RADAR_NO_RENDERABLE_FRAMES",
    }
    assert "geometry" not in result



def test_dwd_radar_map_uses_fixed_projection_safe_wms_layers() -> None:
    radar_url = dwd_radar_map_url(
        lat=50.0,
        lon=8.0,
        layer="radar",
        at="2026-09-28T12:30:00Z",
    )
    assert radar_url.startswith("https://maps.dwd.de/geoserver/dwd/wms?")
    assert "layers=dwd%3ANiederschlagsradar" in radar_url
    assert "crs=EPSG%3A3857" in radar_url
    assert "time=2026-09-28T12%3A30%3A00Z" in radar_url
    assert "lat=" not in radar_url
    assert "lon=" not in radar_url

    base_url = dwd_radar_map_url(lat=50.0, lon=8.0, layer="base")
    assert "layers=dwd%3Abluemarble" in base_url
    assert "transparent=FALSE" in base_url

    boundaries_url = dwd_radar_map_url(lat=50.0, lon=8.0, layer="boundaries")
    assert "layers=dwd%3AWarngebiete_Kreise" in boundaries_url
    assert "transparent=TRUE" in boundaries_url


def test_dwd_radar_map_proxy_accepts_only_png() -> None:
    seen: list[str] = []

    def fake_fetcher(url: str) -> bytes:
        seen.append(url)
        return PNG_SIGNATURE + b"fixture"

    payload = fetch_dwd_radar_map_png(
        lat=50.0,
        lon=8.0,
        layer="radar",
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
            layer="base",
            fetcher=bad_fetcher,
        )
    except ValueError as exc:
        assert "not PNG" in str(exc)
    else:
        raise AssertionError("non-PNG WMS response must fail closed")
