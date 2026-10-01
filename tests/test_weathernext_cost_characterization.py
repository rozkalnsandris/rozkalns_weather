from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from rozkalns_weather.locations import BENCHMARK_LOCATION
from rozkalns_weather.weathernext_cost_characterization import (
    WeatherNextCostCharacterizationError,
    characterize_clustered_query_costs,
)


class FakeJob:
    def __init__(self, estimated_bytes: int, accuracy: str = "UPPER_BOUND") -> None:
        self.total_bytes_processed = estimated_bytes
        self._properties = {
            "statistics": {
                "query": {"totalBytesProcessedAccuracy": accuracy},
            }
        }


class FakeClient:
    def __init__(self, estimates=(2_000_000_000, 20_000_000_000)) -> None:
        self.estimates = list(estimates)
        self.calls = []

    def query(self, sql, job_config=None, **kwargs):
        self.calls.append((sql, job_config, kwargs))
        return FakeJob(self.estimates.pop(0))


def _dry_run_config():
    return SimpleNamespace(
        dry_run=True,
        use_query_cache=False,
        maximum_bytes_billed=None,
    )


def test_characterization_is_uncapped_dry_run_only_and_sanitized() -> None:
    client = FakeClient()
    payload = characterize_clustered_query_costs(
        client=client,
        project="private-project",
        dataset="private_dataset",
        init_time=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
        hours_limit=6,
        job_config_factory=_dry_run_config,
    )

    assert payload["state"] == "clustered_cost_characterized"
    assert payload["location_id"] == BENCHMARK_LOCATION.id == "station_05480"
    assert payload["maximum_bytes_billed_applied"] is False
    assert payload["actual_query_performed"] is False
    assert payload["cost_incurred"] is False
    assert payload["requires_owner_real_query_cost_decision"] is True
    assert [item["estimated_bytes"] for item in payload["dry_run"]] == [
        2_000_000_000,
        20_000_000_000,
    ]
    assert [item["estimate_accuracy"] for item in payload["dry_run"]] == [
        "UPPER_BOUND",
        "UPPER_BOUND",
    ]

    rendered = str(payload)
    assert "private-project" not in rendered
    assert "private_dataset" not in rendered
    assert str(BENCHMARK_LOCATION.lat) not in rendered
    assert str(BENCHMARK_LOCATION.lon) not in rendered

    assert len(client.calls) == 2
    for sql, config, kwargs in client.calls:
        assert config.dry_run is True
        assert config.maximum_bytes_billed is None
        assert kwargs == {"retry": None, "job_retry": None, "timeout": 60}
        assert "SELECT *" not in sql
        assert "t.init_time = TIMESTAMP(" in sql
        assert "ST_COVERS" in sql
        assert "f.hours <= 6" in sql


def test_characterization_rejects_a_capped_job_config() -> None:
    client = FakeClient()

    def capped_config():
        return SimpleNamespace(
            dry_run=True,
            use_query_cache=False,
            maximum_bytes_billed=1_073_741_824,
        )

    with pytest.raises(WeatherNextCostCharacterizationError):
        characterize_clustered_query_costs(
            client=client,
            project="private-project",
            dataset="private_dataset",
            init_time=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
            job_config_factory=capped_config,
        )
    assert client.calls == []


def test_characterization_rejects_non_dry_run_config() -> None:
    client = FakeClient()

    def real_query_config():
        return SimpleNamespace(
            dry_run=False,
            use_query_cache=False,
            maximum_bytes_billed=None,
        )

    with pytest.raises(WeatherNextCostCharacterizationError):
        characterize_clustered_query_costs(
            client=client,
            project="private-project",
            dataset="private_dataset",
            init_time=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
            job_config_factory=real_query_config,
        )
    assert client.calls == []


def test_characterization_rejects_invalid_estimate_without_retry() -> None:
    client = FakeClient(estimates=(-1, 1))
    with pytest.raises(WeatherNextCostCharacterizationError):
        characterize_clustered_query_costs(
            client=client,
            project="private-project",
            dataset="private_dataset",
            init_time=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
            job_config_factory=_dry_run_config,
        )
    assert len(client.calls) == 1
