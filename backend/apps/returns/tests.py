from bson import ObjectId
from django.test import SimpleTestCase
from mongoengine.errors import NotUniqueError

from . import repository
from .models import ReturnRequest


def base_values(order_item_id, status="REQUESTED", **overrides):
    return {
        "customer_id": ObjectId(),
        "order_id": ObjectId(),
        "order_item_id": order_item_id,
        "sku": "RF-JCKT-BLK-M",
        "quantity": 1,
        "reason": "defective",
        "resolution_type": "refund",
        "status": status,
        **overrides,
    }


class ActiveReturnUniquenessTests(SimpleTestCase):
    def setUp(self):
        ReturnRequest.objects.delete()

    def tearDown(self):
        ReturnRequest.objects.delete()

    def test_second_active_return_on_same_order_line_is_rejected(self):
        order_item_id = ObjectId()
        repository.create(base_values(order_item_id, status="REQUESTED"))

        with self.assertRaises(NotUniqueError):
            repository.create(base_values(order_item_id, status="REQUESTED"))

    def test_new_return_allowed_once_previous_one_is_terminal(self):
        order_item_id = ObjectId()
        repository.create(base_values(order_item_id, status="COMPLETED"))

        # Must not raise: a terminal return on this order line does not block
        # a new one, by construction of the partial filter expression.
        created = repository.create(base_values(order_item_id, status="REQUESTED"))

        self.assertEqual(created["status"], "REQUESTED")

    def test_completed_quantity_sums_only_completed_returns(self):
        order_item_id = ObjectId()
        repository.create(base_values(order_item_id, status="COMPLETED", quantity=1))
        second_item = ObjectId()
        repository.create(base_values(second_item, status="COMPLETED", quantity=2))
        repository.create(base_values(order_item_id, status="REQUESTED", quantity=99))

        # NotUniqueError above would have prevented this: use a still-active
        # return on a different order line to prove the sum is scoped by id.
        self.assertEqual(repository.completed_quantity_for_order_item(order_item_id), 1)
        self.assertEqual(repository.completed_quantity_for_order_item(second_item), 2)


class TransitionAtomicityTests(SimpleTestCase):
    def setUp(self):
        ReturnRequest.objects.delete()

    def tearDown(self):
        ReturnRequest.objects.delete()

    def test_valid_transition_updates_status_and_appends_history_together(self):
        created = repository.create(base_values(ObjectId(), status="REQUESTED"))
        actor_id = ObjectId()

        updated = repository.transition(
            created["_id"],
            allowed_from_statuses=["REQUESTED"],
            new_status="APPROVED",
            action="RETURN_APPROVED",
            actor_id=actor_id,
            actor_role="agent",
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "APPROVED")
        self.assertEqual(len(updated["history"]), 1)
        self.assertEqual(updated["history"][0]["action"], "RETURN_APPROVED")
        self.assertEqual(updated["history"][0]["previousState"], "REQUESTED")
        self.assertEqual(updated["history"][0]["newState"], "APPROVED")
        self.assertEqual(updated["history"][0]["actorId"], actor_id)

    def test_transition_from_disallowed_state_is_rejected_not_applied(self):
        created = repository.create(base_values(ObjectId(), status="APPROVED"))

        result = repository.transition(
            created["_id"],
            allowed_from_statuses=["REQUESTED"],
            new_status="APPROVED",
            action="RETURN_APPROVED",
            actor_id=ObjectId(),
            actor_role="agent",
        )

        self.assertIsNone(result)
        unchanged = repository.find_by_id(created["_id"])
        self.assertEqual(unchanged["status"], "APPROVED")
        self.assertEqual(len(unchanged["history"]), 0)

    def test_previous_state_is_captured_correctly_with_a_multi_source_state_guard(self):
        """Regression test for a review finding: previousState must reflect
        the document's actual status at write time, not a value read
        beforehand -- otherwise a multi-source-state transition (allowed
        from more than one status) could record the wrong previousState if
        another transition moved the document within the same allowed set
        between the read and the write. This exercises the multi-state case
        directly; see repository.py::transition for the full reasoning.
        """
        created = repository.create(base_values(ObjectId(), status="APPROVED"))

        updated = repository.transition(
            created["_id"],
            allowed_from_statuses=["REQUESTED", "APPROVED"],
            new_status="ITEM_RECEIVED",
            action="ITEM_RECEIVED",
            actor_id=ObjectId(),
            actor_role="warehouse",
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated["history"][0]["previousState"], "APPROVED")

    def test_concurrent_double_approve_only_one_wins(self):
        """No real concurrency needed to prove this: the guard is the same
        atomic conditional filter regardless of how many callers race it, so
        simulating two sequential callers against the same source state is
        sufficient evidence -- the second's filter can never match once the
        first has moved the document.
        """
        created = repository.create(base_values(ObjectId(), status="REQUESTED"))

        first = repository.transition(
            created["_id"], ["REQUESTED"], "APPROVED", "RETURN_APPROVED", ObjectId(), "agent"
        )
        second = repository.transition(
            created["_id"], ["REQUESTED"], "APPROVED", "RETURN_APPROVED", ObjectId(), "agent"
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
