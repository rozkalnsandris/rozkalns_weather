from __future__ import annotations

from datetime import datetime, timezone
import json
import sys

from .private_runtime_activation import evaluate_private_runtime_activation


def _invalid(message: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "state": "INVALID",
        "error": message,
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "project_dataset_identity_exposed": False,
            "real_weather_values_exposed": False,
            "private_paths_or_logs_exposed": False,
        },
        "authority": {
            "live_authority_granted": False,
            "production_data_authority_granted": False,
            "credential_mutation_authority_granted": False,
            "runtime_mutation_performed": False,
        },
    }


def main() -> None:
    try:
        evidence = json.load(sys.stdin)
        if not isinstance(evidence, dict):
            raise ValueError("private runtime activation evidence must be a JSON object")
        payload = evaluate_private_runtime_activation(
            evidence,
            now=datetime.now(timezone.utc),
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps(_invalid(str(exc)), sort_keys=True, indent=2))
        raise SystemExit(2)

    print(json.dumps(payload, sort_keys=True, indent=2))
    if payload["state"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
