from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_REVISION = "274d58f2d9d3cb86feded2751b8f9009a4501f6b"


class WorkCycleV23CanaryTests(unittest.TestCase):
    def load_json(self, relative: str):
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_bootstrap_manifest_is_stable_routing_only(self):
        manifest = self.load_json(".github/agent-bootstrap.json")
        self.assertEqual(manifest["schema"], "rozkalns.agent-bootstrap.v1")
        self.assertEqual(manifest["repository"], "rozkalnsandris/rozkalns_weather")
        self.assertEqual(manifest["shared_policy"]["work_cycle"], "docs/WORK_CYCLE_V23_ADOPTION.md")
        self.assertEqual(manifest["shared_policy"]["github_api_access"], ".github/github-api-access-v1.json")
        self.assertEqual(manifest["continuation"], {"kind": "issue", "locator": "9"})
        self.assertEqual(
            manifest["automation"],
            {"fast_lane": True, "auto_run_full": True, "queue_mode": "inactive"},
        )
        self.assertEqual(manifest["deployment_profile"], "simple-deploy")

        for relative in (
            manifest["rules"]["primary"],
            manifest["shared_policy"]["work_cycle"],
            manifest["shared_policy"]["github_api_access"],
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

        forbidden = {
            "current_main_sha", "main_sha", "current_head_sha", "head_sha",
            "active_pr_number", "pr_number", "ci_status", "review_state",
            "mergeability", "runtime_revision", "deployed_revision",
            "merge_authorization", "live_authorization", "authorization_consumed",
            "secret", "secrets", "credential", "credentials", "token", "password", "api_key",
        }

        def walk(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    self.assertNotIn(str(key).casefold(), forbidden)
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(manifest)

    def test_start_auto_continuation_and_compact_terminal_contract(self):
        doc = (ROOT / "docs/WORK_CYCLE_V23_ADOPTION.md").read_text(encoding="utf-8")
        routing = self.load_json(".github/start-mode-routing.json")
        self.assertIn(SHARED_REVISION, doc)
        self.assertIn("exactly one canonical lane", doc)
        self.assertIn("automatically executes all immediately safe same-scope technical work", doc)
        self.assertIn("stops only at a genuine owner gate", doc)
        self.assertIn("at most four decisive `EVIDENCE` facts", doc)
        self.assertIn("exactly one final actionable command", doc)
        self.assertIn("`ACTION REQUIRED` appears only for a real owner decision", doc)
        self.assertEqual(routing["bare_continuation_result"], "FAST-LANE v2.2")
        self.assertFalse(routing["explicit_modes"]["AUTO-RUN-FULL"]["may_be_inferred_from_context"])

    def test_write_preflight_adopts_shared_extension_without_local_framework(self):
        api = self.load_json(".github/github-api-access-v1.json")
        preflight = api["write_preflight"]
        self.assertEqual(preflight["contract"], "WRITE_PREFLIGHT_COMPACT_V1")
        self.assertEqual(preflight["shared_revision"], SHARED_REVISION)
        self.assertEqual(preflight["exact_existing_intent"], "RECONCILE_OR_NOOP")
        self.assertEqual(preflight["conflicting_intent"], "STOP")
        self.assertEqual(preflight["stale_writer"], "STOP")
        self.assertFalse(preflight["duplicate_recovery_write_allowed"])
        self.assertFalse(preflight["local_framework_implementation"])

        cases = self.load_json("tests/fixtures/work_cycle_v23_write_preflight_cases.json")
        allowed = {"RECONCILE_OR_NOOP", "STOP"}
        self.assertGreaterEqual(len(cases), 6)
        for case in cases:
            self.assertIn(case["expected"], allowed)
            self.assertFalse(case["dispatch_duplicate_write"])
            if "exact" in case["observed"] and "conflicting" not in case["observed"]:
                self.assertEqual(case["expected"], "RECONCILE_OR_NOOP")
            if any(word in case["observed"] for word in ("different", "conflicting", "stale")):
                self.assertEqual(case["expected"], "STOP")

    def test_normalized_full_state_is_new_activation_only_and_fail_closed(self):
        full = self.load_json(".github/auto-run-full-v2.json")
        normalized = full["normalized_state"]
        self.assertEqual(normalized["shared_revision"], SHARED_REVISION)
        self.assertEqual(normalized["activation_mode"], "NEW_EXPLICIT_RUNS_ONLY")
        self.assertEqual(normalized["legacy_controller_issue"], 9)
        self.assertTrue(normalized["legacy_active_or_historical_state_read_only"])
        self.assertFalse(normalized["rewrite_legacy_state_in_place"])
        self.assertTrue(normalized["legacy_idle_transition_requires_fresh_explicit_full_activation"])
        self.assertTrue(normalized["historical_receipts_preserved"])
        self.assertTrue(normalized["target_issue_owns_mutable_run_state"])
        self.assertTrue(normalized["controller_owns_only_lock_and_active_run_pointer"])
        self.assertTrue(normalized["receipts_are_evidence_only"])
        self.assertEqual(normalized["stale_writer_disposition"], "STOP")
        self.assertEqual(normalized["transition_collision_disposition"], "STOP")
        self.assertTrue(normalized["exact_replay_is_idempotent"])
        self.assertFalse(normalized["queue_vnext_96_activated"])

    def test_local_merge_live_and_deploy_boundaries_are_unchanged(self):
        full = self.load_json(".github/auto-run-full-v2.json")
        doc = (ROOT / "docs/WORK_CYCLE_V23_ADOPTION.md").read_text(encoding="utf-8")
        self.assertTrue(full["command"]["requires_explicit_current_command"])
        self.assertTrue(
            full["merge"]["auto_run_full_command_is_explicit_owner_merge_authority_for_the_frozen_issue"]
        )
        self.assertFalse(full["live"]["merge_authorizes_live"])
        self.assertTrue(full["live"]["private_rpi5_deploy_requires_separate_exact_authority"])
        self.assertIn("FAST source work may proceed through PR/CI/Ready, but merge requires a separate exact owner command", doc)
        self.assertIn("does not perform a SIMPLE-DEPLOY cutover", doc)
        self.assertIn("Queue vNext", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
