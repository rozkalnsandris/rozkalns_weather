import copy
import json
from pathlib import Path

import pytest

from rozkalns_weather.locations import BENCHMARK_LOCATION
from rozkalns_weather.weathernext_final_live_plan import (
    BLOCKED, RPI5_SOURCE_SHA, bind_source_receipt, build_final_live_plan, validate_final_live_plan,
)


def test_checked_in_plan_matches_closed_schema_and_does_not_authorize_live():
    plan = json.loads(Path("deploy/weathernext-final-live-plan.json").read_text())
    result = validate_final_live_plan(plan)
    assert result["next_state"] == BLOCKED
    assert result["live_authorized"] is False
    assert plan["target"]["location_id"] == BENCHMARK_LOCATION.id == "station_05480"
    classes = {item["class"]: item for item in plan["ordered_stages"]}
    assert classes["weathernext_private_runtime_materialization"]["source_readiness"] == "SOURCE_READY"
    assert classes["private_execution_bridge"]["source_readiness"] == "EXTERNAL_SOURCE_CAPABILITY_MISSING"


@pytest.mark.parametrize("path,value", [
    (("target", "host_alias"), "other-host"),
    (("target", "home_scope_enabled"), True),
    (("canary", "HOURS"), 7),
    (("canary", "MAX_BYTES_BILLED_PER_QUERY"), 1073741825),
    (("canary", "first_access_sqlite_write"), True),
    (("failure_policy", "automatic_retry"), True),
    (("authority", "plan_grants_live_authority"), True),
    (("target", "project_id"), "private-fixture"),
    (("target", "credential_path"), "/private-fixture"),
    (("target", "email"), "fixture@example.invalid"),
    (("target", "raw_values"), [1, 2]),
])
def test_scope_expansion_or_private_field_rejected_without_echo(path, value):
    plan = copy.deepcopy(build_final_live_plan())
    plan[path[0]][path[1]] = value
    with pytest.raises(ValueError, match="public-safe") as exc:
        validate_final_live_plan(plan)
    assert "private-fixture" not in str(exc.value)


def test_source_binding_rejects_drift_or_failed_ci_and_never_claims_runtime():
    args = dict(weather_sha="a" * 40, observed_weather_main="a" * 40,
                rpi5_sha=RPI5_SOURCE_SHA, weather_ci_pass=True, rpi5_ci_pass=True)
    assert bind_source_receipt(**args)["runtime_verified"] is False
    for change in ({"observed_weather_main": "b" * 40}, {"rpi5_sha": "b" * 40},
                   {"weather_ci_pass": False}, {"rpi5_ci_pass": False}):
        with pytest.raises(ValueError):
            bind_source_receipt(**(args | change))
