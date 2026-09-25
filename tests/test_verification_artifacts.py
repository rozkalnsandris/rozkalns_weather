from rozkalns_weather.artifact_schema_compatibility import artifact_schema_identity
from rozkalns_weather.verification import ErrorPair
from rozkalns_weather.verification_artifacts import (
    VERIFICATION_SUMMARY_CONTRACT,
    VERIFICATION_SUMMARY_SCHEMA_VERSION,
    build_verification_summary_artifact,
)


def test_verification_summary_artifact_is_explicitly_versioned() -> None:
    artifact = build_verification_summary_artifact(
        [ErrorPair("icon_d2", "2026-09", 6, 11.0, 10.0)],
        expected_n=2,
    )
    assert artifact["contract"] == VERIFICATION_SUMMARY_CONTRACT
    assert artifact["schema_version"] == VERIFICATION_SUMMARY_SCHEMA_VERSION
    assert artifact["n"] == 1
    assert artifact["missingness"]["missing_n"] == 1
    assert artifact_schema_identity(artifact) == {
        "name": "verification_summary",
        "version": 1,
        "contract": "verification-summary-v1",
    }
