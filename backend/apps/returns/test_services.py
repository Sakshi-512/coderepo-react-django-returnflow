from datetime import timedelta
from unittest.mock import patch

from bson import ObjectId
from django.test import SimpleTestCase

from apps.auth.models import WorkspaceAccount
from apps.catalog.models import Product
from apps.inventory.models import Inventory, InventoryReservation
from apps.orders.models import Order, OrderItem
from apps.refunds.models import RefundOperation
from apps.shared.documents import now_utc
from apps.shared.errors import AppError

from . import services
from .models import ReturnRequest


def make_customer():
    return WorkspaceAccount(name="Cust", email=f"{ObjectId()}@returnflow.example", password_hash="x", role="customer").save()


def make_order(customer_id, sku="RF-TEST-A", quantity=2, delivered_days_ago=5):
    item = OrderItem(sku=sku, quantity=quantity, unit_price=10, delivered_at=now_utc() - timedelta(days=delivered_days_ago))
    return Order(customer_id=customer_id, items=[item]).save()


def make_product(sku="RF-TEST-A", returnable=True, variant_group="group-a"):
    return Product(sku=sku, name="Test product", price=10, variant_group=variant_group, returnable=returnable).save()


class SubmitReturnTests(SimpleTestCase):
    def setUp(self):
        WorkspaceAccount.objects.delete()
        Order.objects.delete()
        Product.objects.delete()
        ReturnRequest.objects.delete()

    def tearDown(self):
        WorkspaceAccount.objects.delete()
        Order.objects.delete()
        Product.objects.delete()
        ReturnRequest.objects.delete()

    def test_eligible_submission_creates_requested_return(self):
        customer = make_customer()
        order = make_order(customer.id)
        make_product()
        account = {"_id": str(customer.id), "role": "customer"}
        values = {
            "orderId": str(order.id),
            "orderItemId": str(order.items[0].order_item_id),
            "quantity": 1,
            "reason": "defective",
            "resolutionType": "refund",
            "exchangeSku": None,
        }

        created = services.submit_return(values, account)

        self.assertEqual(created["status"], "REQUESTED")
        self.assertEqual(len(created["history"]), 1)

    def test_ineligible_submission_is_auto_rejected_not_a_400(self):
        customer = make_customer()
        order = make_order(customer.id, delivered_days_ago=45)  # past the 30-day window
        make_product()
        account = {"_id": str(customer.id), "role": "customer"}
        values = {
            "orderId": str(order.id),
            "orderItemId": str(order.items[0].order_item_id),
            "quantity": 1,
            "reason": "defective",
            "resolutionType": "refund",
            "exchangeSku": None,
        }

        created = services.submit_return(values, account)

        self.assertEqual(created["status"], "REJECTED")
        self.assertEqual(created["history"][-1]["metadata"]["ruleCode"], "RETURN_WINDOW_EXPIRED")

    def test_second_submission_for_same_order_line_is_rejected_while_first_is_active(self):
        customer = make_customer()
        order = make_order(customer.id, quantity=5)
        make_product()
        account = {"_id": str(customer.id), "role": "customer"}
        values = {
            "orderId": str(order.id),
            "orderItemId": str(order.items[0].order_item_id),
            "quantity": 1,
            "reason": "defective",
            "resolutionType": "refund",
            "exchangeSku": None,
        }

        services.submit_return(values, account)

        with self.assertRaises(AppError) as ctx:
            services.submit_return(values, account)

        self.assertEqual(ctx.exception.code, "DUPLICATE_ACTIVE_RETURN")

    def test_cannot_submit_against_another_customers_order(self):
        owner = make_customer()
        other = make_customer()
        order = make_order(owner.id)
        make_product()
        account = {"_id": str(other.id), "role": "customer"}
        values = {
            "orderId": str(order.id),
            "orderItemId": str(order.items[0].order_item_id),
            "quantity": 1,
            "reason": "defective",
            "resolutionType": "refund",
            "exchangeSku": None,
        }

        with self.assertRaises(AppError) as ctx:
            services.submit_return(values, account)

        self.assertEqual(ctx.exception.code, "ORDER_NOT_FOUND")


class OwnershipTests(SimpleTestCase):
    def setUp(self):
        WorkspaceAccount.objects.delete()
        ReturnRequest.objects.delete()

    def tearDown(self):
        WorkspaceAccount.objects.delete()
        ReturnRequest.objects.delete()

    def _create_return_for(self, customer_id):
        from . import repository

        return repository.create(
            {
                "customer_id": customer_id,
                "order_id": ObjectId(),
                "order_item_id": ObjectId(),
                "sku": "RF-TEST-A",
                "quantity": 1,
                "reason": "defective",
                "resolution_type": "refund",
                "status": "REQUESTED",
                "history": [],
            }
        )

    def test_owner_can_view_their_own_return(self):
        customer = make_customer()
        created = self._create_return_for(customer.id)

        found = services.get_by_id(str(created["_id"]), {"_id": str(customer.id), "role": "customer"})

        self.assertEqual(found["_id"], created["_id"])

    def test_other_customer_gets_not_found_not_forbidden(self):
        owner = make_customer()
        other = make_customer()
        created = self._create_return_for(owner.id)

        with self.assertRaises(AppError) as ctx:
            services.get_by_id(str(created["_id"]), {"_id": str(other.id), "role": "customer"})

        self.assertEqual(ctx.exception.status_code, 404)

    def test_staff_can_view_any_customers_return(self):
        owner = make_customer()
        created = self._create_return_for(owner.id)
        staff = {"_id": str(ObjectId()), "role": "agent"}

        found = services.get_by_id(str(created["_id"]), staff)

        self.assertEqual(found["_id"], created["_id"])

    def test_cancel_rejected_for_non_owner(self):
        owner = make_customer()
        other = make_customer()
        created = self._create_return_for(owner.id)

        with self.assertRaises(AppError) as ctx:
            services.cancel(str(created["_id"]), {"_id": str(other.id), "role": "customer"})

        self.assertEqual(ctx.exception.status_code, 404)


class InspectCascadeTests(SimpleTestCase):
    """Proves the inspect-pass cascade actually initiates the correct
    downstream workflow (refund vs exchange) inline, in the same call.
    """

    def setUp(self):
        ReturnRequest.objects.delete()
        RefundOperation.objects.delete()
        InventoryReservation.objects.delete()
        Inventory.objects.delete()

    def tearDown(self):
        ReturnRequest.objects.delete()
        RefundOperation.objects.delete()
        InventoryReservation.objects.delete()
        Inventory.objects.delete()

    def _received_return(self, resolution_type="refund", exchange_sku=None):
        from . import repository

        return repository.create(
            {
                "customer_id": ObjectId(),
                "order_id": ObjectId(),
                "order_item_id": ObjectId(),
                "sku": "RF-TEST-A",
                "quantity": 1,
                "reason": "defective",
                "resolution_type": resolution_type,
                "exchange_sku": exchange_sku,
                "status": "ITEM_RECEIVED",
                "history": [],
            }
        )

    def test_inspect_pass_for_refund_creates_and_advances_a_refund_operation(self):
        return_doc = self._received_return(resolution_type="refund")
        actor = {"_id": str(ObjectId()), "role": "warehouse"}

        updated = services.inspect(str(return_doc["_id"]), actor, "pass", "")

        self.assertIn(updated["status"], ("REFUND_PROCESSING", "COMPLETED", "REFUND_FAILED"))
        from apps.refunds import repository as refund_repository

        self.assertIsNotNone(refund_repository.find_by_return_and_cycle(return_doc["_id"], 1))

    def test_inspect_pass_for_exchange_creates_and_advances_a_reservation(self):
        Inventory(sku="RF-TEST-REPLACEMENT", available_quantity=1, reserved_quantity=0).save()
        return_doc = self._received_return(resolution_type="exchange", exchange_sku="RF-TEST-REPLACEMENT")
        actor = {"_id": str(ObjectId()), "role": "warehouse"}

        updated = services.inspect(str(return_doc["_id"]), actor, "pass", "")

        self.assertIn(updated["status"], ("EXCHANGE_RESERVING", "COMPLETED", "EXCHANGE_AWAITING_INVENTORY"))
        from apps.inventory import repository as inventory_repository

        self.assertIsNotNone(inventory_repository.find_reservation(return_doc["_id"], 1))

    def test_inspect_fail_rejects_without_touching_refund_or_inventory(self):
        return_doc = self._received_return(resolution_type="refund")
        actor = {"_id": str(ObjectId()), "role": "warehouse"}

        updated = services.inspect(str(return_doc["_id"]), actor, "fail", "damaged beyond claimed reason")

        self.assertEqual(updated["status"], "REJECTED")
        self.assertEqual(updated["inspection"]["verdict"], "fail")

    def test_inspect_pass_succeeds_even_if_the_inline_cascade_fails(self):
        """Regression test for a real gap found in review: the ITEM_INSPECTED
        transition commits before the inline refund/exchange cascade runs.
        If the cascade raises for any reason, inspect() must still report
        success (the actual state change the caller asked for DID happen)
        rather than surface an error for an action that actually worked --
        the return is left exactly as a real crash at this point would leave
        it: persisted in REFUND_PROCESSING, recoverable via a later explicit
        POST .../refund/attempt.
        """
        return_doc = self._received_return(resolution_type="refund")
        actor = {"_id": str(ObjectId()), "role": "warehouse"}

        with patch("apps.refunds.services.initiate_and_advance", side_effect=RuntimeError("simulated crash")):
            updated = services.inspect(str(return_doc["_id"]), actor, "pass", "")

        self.assertEqual(updated["status"], "REFUND_PROCESSING")

        from apps.refunds import repository as refund_repository

        # The cascade never got to create the operation -- exactly the
        # "crash after transition, before operation created" row of the
        # refund crash matrix, which POST .../refund/attempt already
        # recovers from (see apps/refunds/test_services.py).
        self.assertIsNone(refund_repository.find_by_return_and_cycle(return_doc["_id"], 1))
