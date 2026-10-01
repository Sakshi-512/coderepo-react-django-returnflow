"""Inventory reservation repository.

Standalone MongoDB, no replica set -> no multi-document transactions. Every
write here is a single-document atomic conditional update. Reserving stock for
an exchange touches two documents (Inventory, InventoryReservation), so the
sequence is ordered to stay safely retryable after a crash at any point:

1. create_reservation()  - idempotent insert of the PENDING intent record.
2. apply_decrement()     - idempotent per reservation_id via
                            pendingReservationIds, so retrying it after an
                            unknown-outcome crash can never double-decrement.
3. mark_reserved() / mark_insufficient() - durably resolve the reservation.
4. prune_pending()       - best-effort cleanup; correctness never depends on
                            this running, only on step 2's guard.

apply_decrement/release/prune_pending intentionally take ONLY a
reservation_id and look up sku/quantity from the InventoryReservation record
itself, rather than trusting a caller-supplied sku/quantity -- the
reservation is the single source of truth for "how much, of what" once it
exists, so a caller passing a mismatched value can never cause an incorrect
inventory adjustment.
"""

from bson import ObjectId
from mongoengine.errors import NotUniqueError
from pymongo import ReturnDocument

from apps.shared.mongo import collection

from .models import Inventory, InventoryReservation


def _as_object_id(value):
    return ObjectId(value) if isinstance(value, str) else value


def find_inventory(sku):
    return Inventory.objects(__raw__={"sku": sku}).as_pymongo().first()


def find_reservation(return_request_id, cycle):
    return InventoryReservation.objects(
        __raw__={"returnRequestId": ObjectId(return_request_id), "cycle": cycle}
    ).as_pymongo().first()


def find_reservation_by_id(reservation_id):
    return collection(InventoryReservation).find_one({"_id": _as_object_id(reservation_id)})


def create_reservation(return_request_id, cycle, sku, quantity):
    """Idempotent: a duplicate call for the same (return_request_id, cycle)
    returns the existing PENDING/resolved reservation instead of a second row.
    """
    existing = find_reservation(return_request_id, cycle)

    if existing is not None:
        return existing

    try:
        document = InventoryReservation(
            return_request_id=ObjectId(return_request_id), cycle=cycle, sku=sku, quantity=quantity, status="PENDING"
        ).save()
    except NotUniqueError:
        # A genuinely concurrent caller won the race on the same
        # {returnRequestId, cycle} between our existence check and our
        # insert. That's the intended idempotent outcome, not an error.
        return find_reservation(return_request_id, cycle)

    return collection(InventoryReservation).find_one({"_id": document.id})


def apply_decrement(reservation_id):
    """Atomically decrement available stock for this reservation, exactly once.

    sku/quantity are read from the reservation record itself (see module
    docstring), not accepted as parameters. The filter's
    `pendingReservationIds: {"$ne": reservation_id}` makes this call safe to
    retry blindly: if a previous attempt already committed (e.g. the process
    crashed before the caller could record that), this second call will not
    match the filter and returns None -- the caller distinguishes "already
    applied" from "insufficient stock" via `was_already_applied`.

    Returns None if the reservation does not exist, stock is insufficient, or
    this reservation_id was already applied.
    """
    reservation_id = _as_object_id(reservation_id)
    reservation = find_reservation_by_id(reservation_id)

    if reservation is None:
        return None

    return collection(Inventory).find_one_and_update(
        {
            "sku": reservation["sku"],
            "availableQuantity": {"$gte": reservation["quantity"]},
            "pendingReservationIds": {"$ne": reservation_id},
        },
        {
            "$inc": {"availableQuantity": -reservation["quantity"], "reservedQuantity": reservation["quantity"]},
            "$push": {"pendingReservationIds": reservation_id},
        },
        return_document=ReturnDocument.AFTER,
    )


def was_already_applied(reservation_id):
    reservation_id = _as_object_id(reservation_id)
    reservation = find_reservation_by_id(reservation_id)

    if reservation is None:
        return False

    return (
        collection(Inventory).find_one({"sku": reservation["sku"], "pendingReservationIds": reservation_id})
        is not None
    )


def mark_reserved(reservation_id):
    """Guarded on status=PENDING so this can only ever fire once per reservation."""
    return collection(InventoryReservation).find_one_and_update(
        {"_id": _as_object_id(reservation_id), "status": "PENDING"},
        {"$set": {"status": "RESERVED"}},
        return_document=ReturnDocument.AFTER,
    )


def mark_insufficient(reservation_id):
    return collection(InventoryReservation).find_one_and_update(
        {"_id": _as_object_id(reservation_id), "status": "PENDING"},
        {"$set": {"status": "INSUFFICIENT"}},
        return_document=ReturnDocument.AFTER,
    )


def release(reservation_id):
    """Return previously reserved stock. Guarded on status=RESERVED so a
    reservation can only ever be released once. The returned quantity/sku
    come from the reservation document that was just guarded-updated, never
    from caller input, so this can never credit the wrong amount or the
    wrong SKU back to Inventory.
    """
    updated_reservation = collection(InventoryReservation).find_one_and_update(
        {"_id": _as_object_id(reservation_id), "status": "RESERVED"},
        {"$set": {"status": "RELEASED"}},
        return_document=ReturnDocument.AFTER,
    )

    if updated_reservation is None:
        return None

    collection(Inventory).find_one_and_update(
        {"sku": updated_reservation["sku"]},
        {
            "$inc": {
                "availableQuantity": updated_reservation["quantity"],
                "reservedQuantity": -updated_reservation["quantity"],
            }
        },
    )

    return updated_reservation


def prune_pending(reservation_id):
    """Best-effort removal of a resolved reservation id from the pending
    ledger. Safe to skip or run repeatedly: the decrement guard in
    apply_decrement() is keyed per reservation_id, so a stale entry belonging
    to *this* reservation only ever blocks a redundant re-decrement (the
    correct outcome), and never affects any other reservation's guard check.
    """
    reservation_id = _as_object_id(reservation_id)
    reservation = find_reservation_by_id(reservation_id)

    if reservation is None:
        return

    collection(Inventory).find_one_and_update(
        {"sku": reservation["sku"]},
        {"$pull": {"pendingReservationIds": reservation_id}},
    )
