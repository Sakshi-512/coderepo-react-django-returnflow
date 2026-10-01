from bson import ObjectId
from django.test import SimpleTestCase

from apps.returns import repository as return_repository
from apps.returns.models import ReturnRequest
from apps.shared.errors import AppError

from . import repository, services
from .models import Inventory, InventoryReservation


def make_return(status="EXCHANGE_RESERVING", cycle=1, exchange_sku="RF-TEST-REPLACEMENT", quantity=1):
    return return_repository.create(
        {
            "customer_id": ObjectId(),
            "order_id": ObjectId(),
            "order_item_id": ObjectId(),
            "sku": "RF-TEST-ORIGINAL",
            "quantity": quantity,
            "reason": "defective",
            "resolution_type": "exchange",
            "exchange_sku": exchange_sku,
            "status": status,
            "cycle": cycle,
            "history": [],
        }
    )


class ExchangeAdvanceCrashRecoveryTests(SimpleTestCase):
    """Each test reproduces one row of the exchange crash matrix from the
    Phase 2 architecture (reservation creation / inventory decrement /
    reservation resolution / ReturnRequest advancement / pending-id pruning)
    by simulating the state a crash would leave behind, then calling
    advance() exactly as POST .../exchange/retry-reservation would.
    """

    def setUp(self):
        ReturnRequest.objects.delete()
        InventoryReservation.objects.delete()
        Inventory.objects.delete()
        Inventory(sku="RF-TEST-REPLACEMENT", available_quantity=1, reserved_quantity=0).save()

    def tearDown(self):
        ReturnRequest.objects.delete()
        InventoryReservation.objects.delete()
        Inventory.objects.delete()

    def test_creates_missing_reservation_when_return_already_reserving(self):
        """Crash point: ReturnRequest -> EXCHANGE_RESERVING committed, but
        the InventoryReservation for this cycle was never created."""
        return_doc = make_return()

        self.assertIsNone(repository.find_reservation(return_doc["_id"], 1))

        services.advance(return_doc)

        self.assertIsNotNone(repository.find_reservation(return_doc["_id"], 1))

    def test_successful_decrement_confirms_exchange_and_completes_return(self):
        return_doc = make_return()

        services.advance(return_doc)

        stock = repository.find_inventory("RF-TEST-REPLACEMENT")
        updated_return = return_repository.find_by_id(return_doc["_id"])
        self.assertEqual(stock["availableQuantity"], 0)
        self.assertEqual(updated_return["status"], "COMPLETED")

    def test_pending_id_is_pruned_after_confirmation(self):
        return_doc = make_return()

        services.advance(return_doc)

        stock = repository.find_inventory("RF-TEST-REPLACEMENT")
        self.assertEqual(stock["pendingReservationIds"], [])

    def test_insufficient_stock_parks_return_awaiting_inventory(self):
        Inventory.objects(sku="RF-TEST-REPLACEMENT").update(set__available_quantity=0)
        return_doc = make_return()

        services.advance(return_doc)

        updated_return = return_repository.find_by_id(return_doc["_id"])
        self.assertEqual(updated_return["status"], "EXCHANGE_AWAITING_INVENTORY")

    def test_recovers_when_decrement_already_applied_but_resolution_was_never_recorded(self):
        """Crash point: the decrement committed (stock moved, id recorded in
        pendingReservationIds) but the process crashed before resolving the
        reservation to RESERVED. advance() must not re-decrement and must
        still reach RESERVED/COMPLETED."""
        return_doc = make_return()
        reservation = repository.create_reservation(return_doc["_id"], 1, "RF-TEST-REPLACEMENT", 1)
        repository.apply_decrement(reservation["_id"])  # simulate the crash: decrement done, resolution not recorded

        services.advance(return_doc)

        stock = repository.find_inventory("RF-TEST-REPLACEMENT")
        updated_return = return_repository.find_by_id(return_doc["_id"])
        self.assertEqual(stock["availableQuantity"], 0)  # not -1: no double decrement
        self.assertEqual(updated_return["status"], "COMPLETED")

    def test_recovers_when_reservation_already_resolved_but_return_not_advanced(self):
        """Crash point: reservation reached RESERVED but ReturnRequest was
        never advanced past EXCHANGE_RESERVING."""
        return_doc = make_return()
        reservation = repository.create_reservation(return_doc["_id"], 1, "RF-TEST-REPLACEMENT", 1)
        repository.apply_decrement(reservation["_id"])
        repository.mark_reserved(reservation["_id"])

        services.advance(return_doc)

        updated_return = return_repository.find_by_id(return_doc["_id"])
        self.assertEqual(updated_return["status"], "COMPLETED")

    def test_concurrent_last_unit_contention_only_one_reservation_confirms(self):
        first_return = make_return()
        second_return = make_return()

        services.advance(first_return)
        services.advance(second_return)

        first_reservation = repository.find_reservation(first_return["_id"], 1)
        second_reservation = repository.find_reservation(second_return["_id"], 1)
        self.assertEqual(first_reservation["status"], "RESERVED")
        self.assertEqual(second_reservation["status"], "INSUFFICIENT")


class ExchangeRetryTests(SimpleTestCase):
    def setUp(self):
        ReturnRequest.objects.delete()
        InventoryReservation.objects.delete()
        Inventory.objects.delete()
        Inventory(sku="RF-TEST-REPLACEMENT", available_quantity=0, reserved_quantity=0).save()

    def tearDown(self):
        ReturnRequest.objects.delete()
        InventoryReservation.objects.delete()
        Inventory.objects.delete()

    def test_retry_opens_a_new_cycle_that_cannot_collide_with_the_exhausted_one(self):
        return_doc = make_return(status="EXCHANGE_AWAITING_INVENTORY", cycle=1)
        cycle_1_reservation = repository.create_reservation(return_doc["_id"], 1, "RF-TEST-REPLACEMENT", 1)
        # Actually drive cycle 1 to INSUFFICIENT (stock is 0 per setUp) before
        # asserting on it below -- a bug found via live-MongoDB verification:
        # this test previously asserted cycle 1 was INSUFFICIENT without ever
        # making that true, so it only "passed" as long as MongoDB was
        # unreachable and the whole test errored out before the assertion.
        repository.apply_decrement(cycle_1_reservation["_id"])
        repository.mark_insufficient(cycle_1_reservation["_id"])

        Inventory.objects(sku="RF-TEST-REPLACEMENT").update(set__available_quantity=1)  # restocked
        actor = {"_id": str(ObjectId()), "role": "agent"}
        services.retry(return_doc, actor)

        cycle_1 = repository.find_reservation(return_doc["_id"], 1)
        cycle_2 = repository.find_reservation(return_doc["_id"], 2)
        self.assertEqual(cycle_1["status"], "INSUFFICIENT")
        self.assertIsNotNone(cycle_2)
        self.assertEqual(cycle_2["status"], "RESERVED")

    def test_retry_rejected_when_not_awaiting_inventory(self):
        return_doc = make_return(status="EXCHANGE_RESERVING", cycle=1)
        actor = {"_id": str(ObjectId()), "role": "agent"}

        with self.assertRaises(AppError) as ctx:
            services.retry(return_doc, actor)

        self.assertEqual(ctx.exception.code, "RETURN_INVALID_TRANSITION")
