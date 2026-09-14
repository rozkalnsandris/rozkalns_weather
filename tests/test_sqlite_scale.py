from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.db import SCHEMA_SQL
from rozkalns_weather.sqlite_scale import (
    BLOCK_SCORE,
    CONTRACT,
    INDEX_PROPOSAL,
    QUERY_CLASSES,
    SCALE_RUNS_PER_PROVIDER,
    benchmark_scale,
    build_synthetic_corpus,
    classify_plan,
    fixture_summary,
    index_proposal,
    main,
    run_benchmark,
)


def test_synthetic_scales_are_monotonic_and_deterministic() -> None:
    summaries = []
    for scale in ("small", "medium", "large"):
        connection = build_synthetic_corpus(scale)
        try:
            summaries.append(fixture_summary(connection, scale))
        finally:
            connection.close()

    assert [item["forecast_runs"] for item in summaries] == [
        SCALE_RUNS_PER_PROVIDER["small"] * 3,
        SCALE_RUNS_PER_PROVIDER["medium"] * 3,
        SCALE_RUNS_PER_PROVIDER["large"] * 3,
    ]
    assert summaries[0]["forecast_values"] < summaries[1]["forecast_values"] < summaries[2]["forecast_values"]
    assert summaries[0]["observations"] < summaries[1]["observations"] < summaries[2]["observations"]

    first = build_synthetic_corpus("small")
    second = build_synthetic_corpus("small")
    try:
        assert fixture_summary(first, "small")["fixture_checksum"] == fixture_summary(second, "small")["fixture_checksum"]
    finally:
        first.close()
        second.close()


def test_large_scale_baseline_warns_but_candidate_indexes_pass() -> None:
    result = benchmark_scale("large")

    assert result["contract"] == CONTRACT
    assert result["state"] == "WARN"
    assert result["block_reasons"] == []
    assert result["warn_reasons"] == ["BASELINE_INDEX_OPPORTUNITIES"]
    assert result["candidate_regressions"] == []
    assert set(result["baseline"]) == set(QUERY_CLASSES)
    assert set(result["candidate"]) == set(QUERY_CLASSES)

    assert result["baseline"]["provider_health"]["state"] == "WARN"
    assert result["baseline"]["common_sample_verification"]["state"] == "WARN"
    assert result["baseline"]["monthly_reporting"]["state"] == "WARN"
    assert result["baseline"]["api_slice"]["state"] == "WARN"

    assert all(item["state"] == "PASS" for item in result["candidate"].values())
    for name in (
        "corpus_report",
        "provider_health",
        "common_sample_verification",
        "monthly_reporting",
        "api_slice",
    ):
        assert result["candidate_improvements"][name]["score_delta"] > 0

    assert result["authority"]["production_data_authority_granted"] is False
    assert result["authority"]["production_schema_or_index_mutation_authority_granted"] is False
    assert result["authority"]["runtime_live_authority_granted"] is False
    assert result["privacy"]["private_coordinates_used"] is False


def test_plan_classifier_blocks_regressed_large_table_scans() -> None:
    classified = classify_plan(
        "provider_health",
        (
            "SCAN forecast_runs",
            "SCAN v",
            "USE TEMP B-TREE FOR ORDER BY",
        ),
    )
    assert classified["plan_score"] >= BLOCK_SCORE
    assert classified["state"] == "BLOCKED"
    assert "PLAN_SCORE_BLOCKED" in classified["reason_codes"]


def test_machine_contract_matches_source_proposal_and_is_not_applied() -> None:
    path = Path(__file__).resolve().parents[1] / "contracts" / "sqlite-scale-index-readiness-v1.json"
    contract = json.loads(path.read_text(encoding="utf-8"))

    assert contract["contract"] == CONTRACT
    assert contract["status"] == "ACTIVE_SOURCE_BENCHMARK"
    assert contract["benchmark"]["synthetic_only"] is True
    assert contract["benchmark"]["plan_scoring"]["wall_clock_is_gate"] is False
    assert contract["index_migration_proposal"] == index_proposal()
    assert contract["index_migration_proposal"]["apply_to_production"] is False

    for item in INDEX_PROPOSAL:
        assert item["name"] not in SCHEMA_SQL
        assert item["sql"].startswith("CREATE INDEX idx_proposed_")
        assert item["rollback_sql"].startswith("DROP INDEX IF EXISTS idx_proposed_")

    assert contract["authority"]["production_schema_or_index_mutation_authority_granted"] is False
    assert contract["authority"]["vacuum_or_analyze_authority_granted"] is False


def test_full_benchmark_covers_all_scales_without_blocker() -> None:
    payload = run_benchmark()

    assert payload["state"] == "WARN"
    assert payload["query_classes"] == list(QUERY_CLASSES)
    assert [item["fixture"]["scale"] for item in payload["scales"]] == ["small", "medium", "large"]
    assert all(item["state"] == "WARN" for item in payload["scales"])
    assert payload["index_proposal"]["status"] == "PROPOSAL_ONLY"
    assert payload["production_mutation_performed"] is False


def test_cli_emits_machine_readable_source_only_evidence(capsys) -> None:
    rc = main(["--scales", "small"])
    output = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output["contract"] == CONTRACT
    assert output["state"] == "WARN"
    assert output["source_only"] is True
    assert output["production_mutation_performed"] is False
    assert output["scales"][0]["privacy"]["production_paths_read"] is False


def test_cli_fails_closed_on_unknown_scale_without_echoing_input(capsys) -> None:
    rc = main(["--scales", "small,not-a-scale"])
    output = json.loads(capsys.readouterr().out)

    assert rc == 3
    assert output["state"] == "BLOCKED"
    assert output["block_reasons"] == ["BENCHMARK_EXECUTION_ERROR"]
    assert output["detail"] == "ValueError"
    assert "not-a-scale" not in json.dumps(output)
