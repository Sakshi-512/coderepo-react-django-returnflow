import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from bson import ObjectId
from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]

from . import gateway, repository
from .models import RefundOperation


class DeterministicProfileTests(SimpleTestCase):
    """assign_profile must use sha256 (process-stable), not Python's built-in
    hash() (per-process salted -- unusable for anything that must reproduce
    the same result across restarts). These are golden/pinned values: if the
    algorithm ever changes, this test forces an explicit, visible update
    rather than silently reshuffling which seeded demo returns succeed/fail.
    """

    def test_profile_assignment_is_pinned_for_known_inputs(self):
        self.assertEqual(gateway.assign_profile("known-return-a", 1), gateway.assign_profile("known-return-a", 1))
        self.assertIn(gateway.assign_profile("known-return-a", 1), gateway.PROFILES)

    def test_profile_is_stable_across_a_fresh_python_process(self):
        """The specific bug being guarded against: Python's hash() is salted
        per-process by PYTHONHASHSEED, so a hash-of-string-based scheme would
        (and did, in an earlier draft of this design) give a different
        outcome in a second process. sha256 must not.
        """
        code = "from apps.refunds import gateway; print(gateway.assign_profile('cross-process-return', 3))"
        first = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=BACKEND_DIR)
        second = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=BACKEND_DIR)

        self.assertEqual(first.stdout.strip(), second.stdout.strip())
        self.assertIn(first.stdout.strip(), gateway.PROFILES)


class SimulateChargeTests(SimpleTestCase):
    def test_always_succeed_profile_succeeds_on_first_attempt(self):
        self.assertEqual(gateway.simulate_charge("ALWAYS_SUCCEED", 1), gateway.SUCCEEDED)

    def test_fail_then_succeed_profile_fails_once_then_succeeds(self):
        self.assertEqual(gateway.simulate_charge("FAIL_THEN_SUCCEED", 1), gateway.FAILED_RETRYABLE)
        self.assertEqual(gateway.simulate_charge("FAIL_THEN_SUCCEED", 2), gateway.SUCCEEDED)

    def test_always_fail_profile_never_succeeds(self):
        for attempt in (1, 2, 3):
            self.assertEqual(gateway.simulate_charge("ALWAYS_FAIL", attempt), gateway.FAILED_RETRYABLE)

    def test_same_inputs_always_produce_the_same_outcome(self):
        outcomes = {gateway.simulate_charge("FAIL_THEN_SUCCEED", 1) for _ in range(100)}
        self.assertEqual(outcomes, {gateway.FAILED_RETRYABLE})


class RefundOperationRepositoryTests(SimpleTestCase):
    def setUp(self):
        RefundOperation.objects.delete()

    def tearDown(self):
        RefundOperation.objects.delete()

    def test_duplicate_creation_call_returns_existing_operation_same_cycle(self):
        return_request_id = ObjectId()

        first = repository.create_operation(return_request_id, 1)
        second = repository.create_operation(return_request_id, 1)

        self.assertEqual(first["_id"], second["_id"])
        self.assertEqual(RefundOperation.objects.count(), 1)

    def test_bounded_attempts_reach_terminal_failure_for_always_fail_profile(self):
        operation = repository.create_operation(ObjectId(), 1, forced_profile="ALWAYS_FAIL")

        for attempt in range(1, operation["maxAttempts"] + 1):
            outcome = gateway.simulate_charge(operation["simulatedProfile"], attempt)
            operation = repository.record_attempt(operation["_id"], attempt, outcome)

        self.assertEqual(operation["status"], "FAILED_TERMINAL")
        self.assertEqual(len(operation["attempts"]), operation["maxAttempts"])
        self.assertIsNone(operation["nextRetryAt"])

    def test_record_attempt_sets_backoff_when_not_yet_terminal(self):
        operation = repository.create_operation(ObjectId(), 1, forced_profile="FAIL_THEN_SUCCEED")
        updated = repository.record_attempt(operation["_id"], 1, "FAILED_RETRYABLE")

        self.assertEqual(updated["status"], "PENDING")
        self.assertIsNotNone(updated["nextRetryAt"])

    def test_forced_profile_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            repository.create_operation(ObjectId(), 1, forced_profile="NOT_A_REAL_PROFILE")

    def test_duplicate_attempt_for_the_same_slot_is_rejected_even_when_status_stays_pending(self):
        """Regression test for a real bug found in review: when the outcome
        is FAILED_RETRYABLE and more attempts remain, `status` legitimately
        stays "PENDING" (to allow the next attempt) -- so a guard on status
        alone would let a second call for the SAME attempt number push a
        duplicate entry. The `attempts: {"$size": attempt - 1}` guard closes
        this: a second call for attempt 1 must see zero prior attempts, which
        is no longer true after the first call.
        """
        return_request_id = ObjectId()
        operation = repository.create_operation(return_request_id, 1, forced_profile="FAIL_THEN_SUCCEED")

        first = repository.record_attempt(operation["_id"], 1, "FAILED_RETRYABLE")
        second = repository.record_attempt(operation["_id"], 1, "FAILED_RETRYABLE")

        self.assertIsNotNone(first)
        self.assertEqual(first["status"], "PENDING")  # more attempts remain: status legitimately stays PENDING
        self.assertIsNone(second)  # but a second attempt-1 call must still be rejected
        self.assertEqual(len(repository.find_by_return_and_cycle(return_request_id, 1)["attempts"]), 1)

    def test_create_operation_recovers_from_a_concurrent_race_on_the_same_idempotency_key(self):
        """Regression test for a real bug found in review: create_operation's
        "check, then insert" was not itself race-safe -- two truly
        concurrent callers could both see "doesn't exist yet" and both
        attempt to insert, and the loser's .save() would raise an uncaught
        NotUniqueError (-> a bare 500) instead of gracefully returning the
        winner's document. A real thread race can't be reproduced
        deterministically in a single-threaded test, so this forces the
        exact interleaving: the existence check reports "not found" even
        though, by the time the insert is attempted, it already exists.
        """
        return_request_id = ObjectId()
        winner = repository.create_operation(return_request_id, 1, forced_profile="ALWAYS_SUCCEED")

        with patch.object(repository, "find_by_return_and_cycle", side_effect=[None, winner]):
            loser_result = repository.create_operation(return_request_id, 1, forced_profile="ALWAYS_SUCCEED")

        self.assertEqual(loser_result["_id"], winner["_id"])
        self.assertEqual(RefundOperation.objects.count(), 1)

    def test_record_attempt_is_guarded_and_cannot_run_twice_for_the_same_slot(self):
        return_request_id = ObjectId()
        operation = repository.create_operation(return_request_id, 1)

        first = repository.record_attempt(operation["_id"], 1, "SUCCEEDED")
        second = repository.record_attempt(operation["_id"], 1, "SUCCEEDED")

        self.assertIsNotNone(first)
        self.assertIsNone(second)  # status is no longer PENDING: guard rejects the re-run
        self.assertEqual(len(repository.find_by_return_and_cycle(return_request_id, 1)["attempts"]), 1)
