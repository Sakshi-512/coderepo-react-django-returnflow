from unittest.mock import patch

from bson import ObjectId
from django.test import SimpleTestCase

from . import repository
from .models import Inventory, InventoryReservation


def make_reservation(sku="TEST-SKU", quantity=1, status="PENDING"):
    return repository.create_reservation(ObjectId(), 1, sku, quantity) if status == "PENDING" else (
        InventoryReservation(return_request_id=ObjectId(), cycle=1, sku=sku, quantity=quantity, status=status)
        .save()
        .to_mongo()
    )


class InventoryLedgerTests(SimpleTestCase):
    """Proves the pendingReservationIds idempotency ledger (see the module
    docstring in repository.py): the decrement guard is keyed per
    reservation_id, so retrying it after an unknown-outcome crash never
    double-decrements, and a stale entry for one reservation never blocks or
    falsely-satisfies a different reservation's own guard check. Also proves
    apply_decrement/release derive sku/quantity from the reservation record
    itself, never from caller-supplied values.
    """

    def setUp(self):
        Inventory.objects.delete()
        InventoryReservation.objects.delete()
        Inventory(sku="TEST-SKU", available_quantity=1, reserved_quantity=0).save()

    def tearDown(self):
        Inventory.objects.delete()
        InventoryReservation.objects.delete()

    def test_decrement_succeeds_once_and_records_pending_id(self):
        reservation = make_reservation(quantity=1)

        result = repository.apply_decrement(reservation["_id"])

        self.assertIsNotNone(result)
        self.assertEqual(result["availableQuantity"], 0)
        self.assertEqual(result["reservedQuantity"], 1)
        self.assertIn(reservation["_id"], result["pendingReservationIds"])

    def test_decrement_ignores_a_nonexistent_reservation(self):
        self.assertIsNone(repository.apply_decrement(ObjectId()))

    def test_retry_after_unknown_outcome_does_not_double_decrement(self):
        """Simulates the crash window: the first call's write committed, but
        the caller doesn't know that and retries the exact same call.
        """
        reservation = make_reservation(quantity=1)
        repository.apply_decrement(reservation["_id"])

        retried = repository.apply_decrement(reservation["_id"])

        self.assertIsNone(retried)  # guard did not match: already applied, not re-applied
        self.assertTrue(repository.was_already_applied(reservation["_id"]))
        stock = repository.find_inventory("TEST-SKU")
        self.assertEqual(stock["availableQuantity"], 0)  # not -1: no double decrement

    def test_second_distinct_reservation_for_the_last_unit_gets_insufficient(self):
        """The concurrency scenario from the architecture review: two
        reservations contend for the single remaining unit. Sequential calls
        are sufficient evidence because MongoDB serializes writes to one
        document regardless of caller count -- the second's `$gte` filter
        cannot match once the first has already decremented to 0.
        """
        first_reservation = make_reservation(quantity=1)
        second_reservation = make_reservation(quantity=1)

        first_result = repository.apply_decrement(first_reservation["_id"])
        second_result = repository.apply_decrement(second_reservation["_id"])

        self.assertIsNotNone(first_result)
        self.assertIsNone(second_result)
        self.assertFalse(repository.was_already_applied(second_reservation["_id"]))

    def test_stale_pending_id_for_one_reservation_never_blocks_another(self):
        first_reservation = make_reservation(quantity=1)
        repository.apply_decrement(first_reservation["_id"])
        Inventory.objects(sku="TEST-SKU").update(set__available_quantity=5)  # restock for the next check

        other_reservation = make_reservation(quantity=1)
        result = repository.apply_decrement(other_reservation["_id"])

        self.assertIsNotNone(result)
        self.assertIn(first_reservation["_id"], result["pendingReservationIds"])
        self.assertIn(other_reservation["_id"], result["pendingReservationIds"])

    def test_prune_removes_only_the_named_reservation(self):
        keep = make_reservation(quantity=1)
        repository.apply_decrement(keep["_id"])
        Inventory.objects(sku="TEST-SKU").update(set__available_quantity=5)
        remove = make_reservation(quantity=1)
        repository.apply_decrement(remove["_id"])

        repository.prune_pending(remove["_id"])

        stock = repository.find_inventory("TEST-SKU")
        self.assertIn(keep["_id"], stock["pendingReservationIds"])
        self.assertNotIn(remove["_id"], stock["pendingReservationIds"])

    def test_release_returns_stock_and_is_guarded_to_fire_once(self):
        reservation = make_reservation(quantity=1, status="RESERVED")
        Inventory.objects(sku="TEST-SKU").update(set__available_quantity=0, set__reserved_quantity=1)

        first_release = repository.release(reservation["_id"])
        second_release = repository.release(reservation["_id"])

        self.assertIsNotNone(first_release)
        self.assertIsNone(second_release)  # already RELEASED: guard prevents a second refund of stock
        stock = repository.find_inventory("TEST-SKU")
        self.assertEqual(stock["availableQuantity"], 1)
        self.assertEqual(stock["reservedQuantity"], 0)

    def test_release_credits_the_reservations_own_quantity_not_arbitrary_input(self):
        """Regression test for the fix that removed caller-supplied
        sku/quantity from release(): the amount credited back must always
        come from the reservation document, so a caller cannot (by bug or
        otherwise) return the wrong amount of stock.
        """
        reservation = make_reservation(quantity=3, status="RESERVED")
        Inventory.objects(sku="TEST-SKU").update(set__available_quantity=0, set__reserved_quantity=3)

        repository.release(reservation["_id"])

        stock = repository.find_inventory("TEST-SKU")
        self.assertEqual(stock["availableQuantity"], 3)
        self.assertEqual(stock["reservedQuantity"], 0)


class ReservationCreationIdempotencyTests(SimpleTestCase):
    def setUp(self):
        InventoryReservation.objects.delete()

    def tearDown(self):
        InventoryReservation.objects.delete()

    def test_create_reservation_recovers_from_a_concurrent_race_on_the_same_cycle(self):
        """Regression test for a real bug found in review: create_reservation's
        "check, then insert" was not itself race-safe -- see the identical
        fix/test in apps/refunds/tests.py for the full reasoning. Forces the
        exact interleaving a true concurrent race would produce.
        """
        return_request_id = ObjectId()
        winner = repository.create_reservation(return_request_id, 1, "TEST-SKU", 1)

        with patch.object(repository, "find_reservation", side_effect=[None, winner]):
            loser_result = repository.create_reservation(return_request_id, 1, "TEST-SKU", 1)

        self.assertEqual(loser_result["_id"], winner["_id"])
        self.assertEqual(InventoryReservation.objects.count(), 1)

    def test_duplicate_creation_call_returns_existing_reservation(self):
        return_request_id = ObjectId()

        first = repository.create_reservation(return_request_id, 1, "TEST-SKU", 1)
        second = repository.create_reservation(return_request_id, 1, "TEST-SKU", 1)

        self.assertEqual(first["_id"], second["_id"])
        self.assertEqual(InventoryReservation.objects.count(), 1)
