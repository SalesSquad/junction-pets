import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("reconcile_evidence", Path(__file__).with_name("reconcile_evidence.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
J = "a" * 40
C = "b" * 40

def junction(factory=False):
    steps = [{"name": x, "status": "pass"} for x in sorted(mod.REQUIRED_JUNCTION)]
    if factory:
        steps += [{"name": x, "status": "pass"} for x in (
            "factory_broker_unit_tests", "factory_broker_build", "factory_native_benign_canary")]
    return {"schema": "rml1.developer-integration/v1",
            "junction_source_sha": J, "factory_source_sha": C if factory else None,
            "qualified": False, "runtime_authorized": False, "generated_r_executed": False,
            "overall": "pass" if factory else "incomplete", "platform": "linux",
            "steps": steps, "simulation": {
                "scenarios": 100000, "checksum": "add27e55e4d142b6", "runtime_authorized": False}}

def chibi():
    return {"schema": "chibi.seeded-factory-simulation/v1", "passed": True,
            "lane": "market", "head_before": C, "head_after": C,
            "live_egress": False, "external_credentials": "excluded",
            "postgres_cleanup": "not_required",
            "campaign_start": 0, "campaign_count": 10000,
            "cargo_lock_sha256": "d" * 64,
            "suites": [{"scenario": "agent_market", "failed": 0, "passed": 10,
                        "exit_code": 0, "campaign": {
                            "schema": "chibi.synthetic-campaign/v1", "start": 0,
                            "count": 10000, "liveEgress": False,
                            "events": 60000, "traceSha256": "e" * 64}}]}

class ReconcileTests(unittest.TestCase):
    def test_missing_chibi_and_factory_never_green(self):
        result = mod.reconcile(junction(), J)
        self.assertEqual(result["coverage"], "incomplete")
        self.assertFalse(result["runtime_authorized"])
        self.assertEqual(result["chibi"]["status"], "not_run")

    def test_cross_host_chibi_not_a_substitute_for_factory(self):
        result = mod.reconcile(junction(), J, chibi(), C)
        self.assertEqual(result["coverage"], "incomplete")
        self.assertEqual(result["chibi"]["status"], "pass")

    def test_all_source_check_receipts_preserve_non_authorization(self):
        result = mod.reconcile(junction(True), J, chibi(), C)
        self.assertEqual(result["coverage"], "pass")
        self.assertFalse(result["authenticated_host_evidence"])
        self.assertFalse(result["qualified"])
        self.assertFalse(result["runtime_authorized"])

    def test_wrong_chibi_sha_rejected(self):
        with self.assertRaisesRegex(mod.Refused, "chibi_source_mismatch"):
            mod.reconcile(junction(True), J, chibi(), "c"*40)

    def test_missing_market_packet_rejected(self):
        receipt = chibi()
        del receipt["suites"][0]["campaign"]
        with self.assertRaisesRegex(mod.Refused, "chibi_market_packet_invalid"):
            mod.reconcile(junction(True), J, receipt, C)

    def test_fake_factory_complete_rejected(self):
        receipt = junction()
        receipt["overall"] = "pass"
        with self.assertRaisesRegex(mod.Refused, "junction_false_complete"):
            mod.reconcile(receipt, J, chibi(), C)

    def test_wrong_junction_seed_or_status_rejected(self):
        receipt = junction()
        receipt["simulation"]["scenarios"] = 4096
        with self.assertRaisesRegex(mod.Refused, "junction_seed_coverage"):
            mod.reconcile(receipt, J)
        receipt = junction()
        receipt["steps"][0]["status"] = "not_run"
        with self.assertRaisesRegex(mod.Refused, "junction_required_steps_not_passed"):
            mod.reconcile(receipt, J)

    def test_source_sha_and_unsupported_authorization_rejected(self):
        with self.assertRaises(mod.Refused):
            mod.reconcile(junction(), "bad")
        receipt = junction()
        receipt["runtime_authorized"] = True
        with self.assertRaisesRegex(mod.Refused, "junction_authority_claim"):
            mod.reconcile(receipt, J)

    def test_duplicate_steps_rejected(self):
        receipt = junction()
        receipt["steps"].append(receipt["steps"][0])
        with self.assertRaisesRegex(mod.Refused, "duplicate_steps"):
            mod.reconcile(receipt, J)

    def test_chibi_extra_events_required(self):
        receipt = chibi()
        receipt["suites"][0]["campaign"]["events"] = 100
        with self.assertRaisesRegex(mod.Refused, "chibi_events_missing"):
            mod.reconcile(junction(True), J, receipt, C)

if __name__ == "__main__":
    unittest.main()
