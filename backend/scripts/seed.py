"""Deterministic ReturnFlow seed.

Accounts, catalog, inventory, and orders are inserted directly (they are
plain reference/historical data with no workflow invariants of their own).
Every ReturnRequest demo scenario, by contrast, is produced by calling the
REAL service functions (apps.returns.services, apps.refunds.*,
apps.inventory.*) in the same sequence a real user's actions would --
never by constructing a ReturnRequest document directly in a specific
status. That is the only way seeded data can be guaranteed to satisfy the
same guarded invariants (partial unique index, atomic transitions, bounded
refund attempts, idempotent reservations) that the running application
itself enforces.

Determinism:
- Refund success/failure scenarios use the approved `forced_profile`
  mechanism (threaded through the real inspect() -> refund initiation path)
  instead of searching for a return id whose hash happens to land in the
  desired bucket. Organic returns created by real users are NOT seeded here
  and are unaffected -- they still resolve through gateway.assign_profile().
- Exchange success/insufficient-inventory scenarios are deterministic
  because they are controlled by the actual seeded Inventory quantities
  (RF-BOOT-TAN-10 is seeded at 0), not by chance.
- All timestamps are relative to "now" at seed time (mirroring the sample
  calendar repo's own TODAY_KEY convention), with wide margins from the
  30-day return window boundary so classification is stable across any
  realistic gap between seed runs.
"""

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "returnflow_backend.settings")

import django

django.setup()

import bcrypt

from apps.auth.models import WorkspaceAccount
from apps.catalog.models import Product
from apps.inventory.models import Inventory, InventoryReservation
from apps.orders.models import Order, OrderItem
from apps.refunds import gateway as refund_gateway
from apps.refunds import repository as refund_repository
from apps.refunds import services as refund_service
from apps.returns import services as return_service
from apps.returns.eligibility import RETURN_WINDOW_DAYS
from apps.returns.models import ReturnRequest
from apps.shared.documents import stamp
from scripts.seed_data import ACCOUNT_ROWS, DEMO_PASSWORD, INVENTORY_ROWS, ORDER_ROWS, PASSWORD_ROUNDS, PRODUCT_ROWS

SEPARATOR = "=" * 40


def clear_collections():
    print("Clearing existing collections...")

    for model in (ReturnRequest, InventoryReservation, Order, Inventory, Product, WorkspaceAccount):
        model.objects.delete()

    # RefundOperation shares no explicit relation with the models above at
    # the ODM-import level in this script; imported and cleared explicitly.
    from apps.refunds.models import RefundOperation

    RefundOperation.objects.delete()

    # AuditEvent is a derived projection with no bearing on the seed
    # baseline's correctness, but is cleared too so a reseed starts from a
    # genuinely empty projection rather than a mix of old and new rows.
    from apps.audit.models import AuditEvent

    AuditEvent.objects.delete()


def insert_accounts():
    print("\nSeeding accounts...")

    password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt(PASSWORD_ROUNDS)).decode()
    accounts = [stamp(WorkspaceAccount(password_hash=password_hash, **row)) for row in ACCOUNT_ROWS]
    WorkspaceAccount.objects.insert(accounts)

    print(f"  Created {len(accounts)} accounts")

    return {account.email: account for account in accounts}


def insert_products():
    print("\nSeeding catalog...")

    # Explicit field-by-field mapping, not **row unpacking: PRODUCT_ROWS uses
    # db_field-style keys ("variantGroup") for readability, but the
    # mongoengine ODM constructor requires Python attribute names
    # ("variant_group") -- confirmed as a real bug via live-MongoDB
    # verification (blind **row unpacking raised FieldDoesNotExist).
    products = [
        stamp(
            Product(
                sku=row["sku"],
                name=row["name"],
                price=Decimal(row["price"]),
                variant_group=row["variantGroup"],
                returnable=row["returnable"],
            )
        )
        for row in PRODUCT_ROWS
    ]
    Product.objects.insert(products)

    print(f"  Created {len(products)} products")


def insert_inventory():
    print("\nSeeding inventory...")

    rows = [stamp(Inventory(sku=row["sku"], available_quantity=row["availableQuantity"])) for row in INVENTORY_ROWS]
    Inventory.objects.insert(rows)

    print(f"  Created {len(rows)} inventory rows")


def insert_orders(accounts_by_email):
    """Returns scenarios: a dict mapping each scenarioKey to
    {"order": Order, "orderItemId": ObjectId, "sku": str, "customer": WorkspaceAccount}.
    """
    print("\nSeeding orders...")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    orders = []
    scenarios = {}

    for row in ORDER_ROWS:
        customer = accounts_by_email[row["customerEmail"]]
        items = []

        for item_row in row["items"]:
            item = OrderItem(
                sku=item_row["sku"],
                quantity=item_row["quantity"],
                unit_price=Decimal(next(p["price"] for p in PRODUCT_ROWS if p["sku"] == item_row["sku"])),
                fulfillment_status="delivered",
                delivered_at=now - timedelta(days=item_row["deliveredDaysAgo"]),
            )
            items.append((item_row["scenarioKey"], item))

        order = stamp(Order(customer_id=customer.id, items=[item for _, item in items]))
        orders.append(order)

        for scenario_key, item in items:
            scenarios[scenario_key] = {"order": order, "orderItemId": item.order_item_id, "sku": item.sku, "customer": customer}

    Order.objects.insert(orders)

    print(f"  Created {len(orders)} orders covering {len(scenarios)} demo order lines")

    return scenarios


def submit(scenario, customer, reason="defective", resolution_type="refund", exchange_sku=None, quantity=None):
    customer_account = {"_id": str(customer.id), "role": "customer"}
    body = {
        "orderId": str(scenario["order"].id),
        "orderItemId": str(scenario["orderItemId"]),
        "quantity": quantity or 1,
        "reason": reason,
        "resolutionType": resolution_type,
        "exchangeSku": exchange_sku,
    }

    return return_service.submit_return(body, customer_account)


def assert_status(return_id, expected_status, label):
    """The seed must never silently produce a wrong baseline: if any
    scenario doesn't land in the state it's supposed to demonstrate (e.g.
    because the inline resolution cascade's own error handling swallowed a
    real problem -- see returns.services._try_advance_inline), fail loudly
    here rather than leave a mislabeled demo row behind.
    """
    actual = return_service.repository.find_by_id(return_id)["status"]

    if actual != expected_status:
        raise AssertionError(f"Scenario {label!r} expected status {expected_status!r} but got {actual!r}")


def run_return_scenarios(scenarios, accounts_by_email):
    print("\nRunning return workflow scenarios through the real service layer...")

    agent = {"_id": str(accounts_by_email["priya.nair@returnflow.example"].id), "role": "agent"}
    warehouse = {"_id": str(accounts_by_email["sam.ortiz@returnflow.example"].id), "role": "warehouse"}

    # 1. Eligible return, pending operations review (REQUESTED).
    scenario = scenarios["requested_pending_review"]
    created = submit(scenario, scenario["customer"])
    assert_status(str(created["_id"]), "REQUESTED", "requested_pending_review")

    # 2. Ineligible submission -- delivered outside the return window,
    # auto-REJECTED by the real eligibility check, not a fabricated status.
    scenario = scenarios["ineligible_rejected"]
    created = submit(scenario, scenario["customer"])
    assert_status(str(created["_id"]), "REJECTED", "ineligible_rejected")

    # 3. A second REQUESTED return, ready for the review demo.
    scenario = scenarios["requested_second"]
    created = submit(scenario, scenario["customer"])
    assert_status(str(created["_id"]), "REQUESTED", "requested_second")

    # 4. Approved, awaiting the item to arrive.
    scenario = scenarios["approved_awaiting_item"]
    created = submit(scenario, scenario["customer"])
    return_service.approve(str(created["_id"]), agent)
    assert_status(str(created["_id"]), "APPROVED", "approved_awaiting_item")

    # 5. Item received, pending inspection.
    scenario = scenarios["item_received_pending_inspection"]
    created = submit(scenario, scenario["customer"])
    return_service.approve(str(created["_id"]), agent)
    return_service.receive(str(created["_id"]), warehouse)
    assert_status(str(created["_id"]), "ITEM_RECEIVED", "item_received_pending_inspection")

    # 6. Refund succeeded -> COMPLETED. forced_refund_profile is the
    # approved deterministic mechanism -- see module docstring.
    scenario = scenarios["refund_succeeded"]
    created = submit(scenario, scenario["customer"])
    return_service.approve(str(created["_id"]), agent)
    return_service.receive(str(created["_id"]), warehouse)
    return_service.inspect(str(created["_id"]), warehouse, "pass", "", forced_refund_profile="ALWAYS_SUCCEED")
    assert_status(str(created["_id"]), "COMPLETED", "refund_succeeded")

    # 7. Refund retried/exhausted -> REFUND_FAILED. Attempt 1 runs inline via
    # inspect()'s real cascade; attempts 2-3 are driven directly through the
    # same guarded repository.record_attempt() primitive the app itself
    # uses, only to skip the real-time backoff wait (a UX pacing concern,
    # not a data invariant) -- see the module docstring's determinism note.
    scenario = scenarios["refund_failed"]
    created = submit(scenario, scenario["customer"])
    return_service.approve(str(created["_id"]), agent)
    return_service.receive(str(created["_id"]), warehouse)
    return_service.inspect(str(created["_id"]), warehouse, "pass", "", forced_refund_profile="ALWAYS_FAIL")
    operation = refund_repository.find_by_return_and_cycle(str(created["_id"]), 1)
    for attempt in (2, 3):
        outcome = refund_gateway.simulate_charge(operation["simulatedProfile"], attempt)
        operation = refund_repository.record_attempt(operation["_id"], attempt, outcome)
    refresh = return_service.get_by_id(str(created["_id"]), agent)
    refund_service.advance(refresh)
    assert_status(str(created["_id"]), "REFUND_FAILED", "refund_failed")

    # 8. Exchange succeeded -> COMPLETED (replacement SKU has stock).
    scenario = scenarios["exchange_completed"]
    created = submit(scenario, scenario["customer"], resolution_type="exchange", exchange_sku="RF-JCKT-BLK-L")
    return_service.approve(str(created["_id"]), agent)
    return_service.receive(str(created["_id"]), warehouse)
    return_service.inspect(str(created["_id"]), warehouse, "pass", "")
    assert_status(str(created["_id"]), "COMPLETED", "exchange_completed")

    # 9. Exchange parked awaiting inventory (replacement SKU seeded at 0).
    scenario = scenarios["exchange_awaiting_inventory"]
    created = submit(scenario, scenario["customer"], resolution_type="exchange", exchange_sku="RF-BOOT-TAN-10")
    return_service.approve(str(created["_id"]), agent)
    return_service.receive(str(created["_id"]), warehouse)
    return_service.inspect(str(created["_id"]), warehouse, "pass", "")
    assert_status(str(created["_id"]), "EXCHANGE_AWAITING_INVENTORY", "exchange_awaiting_inventory")

    # 10. Rejected at inspection (item did not pass warehouse inspection).
    scenario = scenarios["rejected_at_inspection"]
    created = submit(scenario, scenario["customer"])
    return_service.approve(str(created["_id"]), agent)
    return_service.receive(str(created["_id"]), warehouse)
    return_service.inspect(str(created["_id"]), warehouse, "fail", "Item shows damage inconsistent with the reported reason.")
    assert_status(str(created["_id"]), "REJECTED", "rejected_at_inspection")

    print("  10 demo scenarios created and verified against their expected baseline status")


def seed():
    print(SEPARATOR)
    print("ReturnFlow Database Seeding")
    print(f"{SEPARATOR}\n")

    print("Connecting to MongoDB...")
    print("Connected to MongoDB")
    print(f"Return window: {RETURN_WINDOW_DAYS} days")

    clear_collections()

    accounts_by_email = insert_accounts()
    insert_products()
    insert_inventory()
    scenarios = insert_orders(accounts_by_email)
    run_return_scenarios(scenarios, accounts_by_email)

    print(f"\n{SEPARATOR}")
    print("Seeding completed successfully!")
    print(SEPARATOR)
    print("\nCollection counts:")
    print(f"  Accounts:       {WorkspaceAccount.objects.count()}")
    print(f"  Products:       {Product.objects.count()}")
    print(f"  Inventory:      {Inventory.objects.count()}")
    print(f"  Orders:         {Order.objects.count()}")
    print(f"  Return requests:{ReturnRequest.objects.count()}")
    print("\nDemo accounts (all roles share one password):")

    for row in ACCOUNT_ROWS:
        print(f"  {row['role']:<10} {row['email']} | {DEMO_PASSWORD}")

    print(f"\n{SEPARATOR}\n")


def main():
    try:
        seed()
    except Exception as error:
        print(f"\nSeeding failed: {error}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("Disconnected from MongoDB")


if __name__ == "__main__":
    main()
