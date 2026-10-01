from bson import ObjectId
from django.test import SimpleTestCase

from apps.returns import repository as return_repository
from apps.returns.models import ReturnRequest

from . import repository, services
from .models import RefundOperation


def make_return(status="REFUND_PROCESSING", cycle=1):
    return return_repository.create(
        {
            "customer_id": ObjectId(),
            "order_id": ObjectId(),
            "order_item_id": ObjectId(),
            "sku": "RF-TEST",
            "quantity": 1,
            "reason": "defective",
            "resolution_type": "refund",
            "status": status,
            "cycle": cycle,
            "history": [],
        }
    )


class RefundAdvanceCrashRecoveryTests(SimpleTestCase):
    """Each test reproduces one row of the refund crash matrix from the
    Phase 2 architecture by simulating the state a crash would leave behind,
    then calling advance() exactly as POST .../refund/attempt would.
    """

    def setUp(self):
        ReturnRequest.objects.delete()
        RefundOperation.objects.delete()

    def tearDown(self):
        ReturnRequest.objects.delete()
        RefundOperation.objects.delete()

    def test_creates_missing_operation_when_return_already_in_refund_processing(self):
        """Crash point: ReturnRequest -> REFUND_PROCESSING committed, but the
        RefundOperation for this cycle was never created."""
        return_doc = make_return()

        self.assertIsNone(repository.find_by_return_and_cycle(return_doc["_id"], 1))

        services.advance(return_doc)

        self.assertIsNotNone(repository.find_by_return_and_cycle(return_doc["_id"], 1))

    def test_does_not_recharge_an_already_terminal_operation(self):
        """Crash point: an attempt was already recorded (operation is
        terminal) but ReturnRequest was never advanced past REFUND_PROCESSING."""
        return_doc = make_return()
        operation = repository.create_operation(return_doc["_id"], 1, forced_profile="ALWAYS_SUCCEED")
        repository.record_attempt(operation["_id"], 1, "SUCCEEDED")

        services.advance(return_doc)

        updated_return = return_repository.find_by_id(return_doc["_id"])
        self.assertEqual(updated_return["status"], "COMPLETED")
        # Exactly one attempt exists -- advance() must not have charged again.
        self.assertEqual(len(repository.find_by_return_and_cycle(return_doc["_id"], 1)["attempts"]), 1)

    def test_propagates_terminal_failure_to_return_request(self):
        # Attempts 1-2 are driven directly at the repository layer (bypassing
        # the real backoff wait, which is exercised separately below) so this
        # test focuses purely on "3 attempts recorded -> ReturnRequest
        # advances to REFUND_FAILED", the actual crash-matrix row under test.
        return_doc = make_return()
        operation = repository.create_operation(return_doc["_id"], 1, forced_profile="ALWAYS_FAIL")
        repository.record_attempt(operation["_id"], 1, "FAILED_RETRYABLE")
        repository.record_attempt(operation["_id"], 2, "FAILED_RETRYABLE")
        repository.record_attempt(operation["_id"], 3, "FAILED_RETRYABLE")

        services.advance(return_doc)

        updated_return = return_repository.find_by_id(return_doc["_id"])
        self.assertEqual(updated_return["status"], "REFUND_FAILED")

    def test_respects_backoff_before_eligible(self):
        from apps.shared.errors import AppError

        return_doc = make_return()
        operation = repository.create_operation(return_doc["_id"], 1, forced_profile="FAIL_THEN_SUCCEED")
        repository.record_attempt(operation["_id"], 1, "FAILED_RETRYABLE")

        with self.assertRaises(AppError) as ctx:
            services.advance(return_doc)

        self.assertEqual(ctx.exception.code, "RETRY_NOT_YET_ELIGIBLE")


class RefundRetryTests(SimpleTestCase):
    def setUp(self):
        ReturnRequest.objects.delete()
        RefundOperation.objects.delete()

    def tearDown(self):
        ReturnRequest.objects.delete()
        RefundOperation.objects.delete()

    def test_retry_opens_a_new_cycle_that_cannot_collide_with_the_exhausted_one(self):
        return_doc = make_return(status="REFUND_FAILED", cycle=1)
        repository.create_operation(return_doc["_id"], 1, forced_profile="ALWAYS_FAIL")
        for attempt in (1, 2, 3):
            operation = repository.find_by_return_and_cycle(return_doc["_id"], 1)
            repository.record_attempt(operation["_id"], attempt, "FAILED_RETRYABLE")

        actor = {"_id": str(ObjectId()), "role": "manager"}
        services.retry(return_doc, actor)

        cycle_1 = repository.find_by_return_and_cycle(return_doc["_id"], 1)
        cycle_2 = repository.find_by_return_and_cycle(return_doc["_id"], 2)
        self.assertEqual(cycle_1["status"], "FAILED_TERMINAL")
        self.assertIsNotNone(cycle_2)
        self.assertNotEqual(cycle_1["idempotencyKey"], cycle_2["idempotencyKey"])

    def test_retry_rejected_when_not_in_refund_failed(self):
        from apps.shared.errors import AppError

        return_doc = make_return(status="REFUND_PROCESSING", cycle=1)
        actor = {"_id": str(ObjectId()), "role": "manager"}

        with self.assertRaises(AppError) as ctx:
            services.retry(return_doc, actor)

        self.assertEqual(ctx.exception.code, "RETURN_INVALID_TRANSITION")
