"""Exchange reservation orchestration. Every branch re-derives what's already
true from persisted state before deciding what (if anything) still needs to
happen -- advance() is safe to call from any point, including immediately
after a crash anywhere in a prior call. See the Phase 2 architecture's
exchange crash matrix for the checkpoint-by-checkpoint reasoning this
mirrors.
"""

from apps.audit import services as audit_service
from apps.returns import repository as return_repository
from apps.shared.documents import now_utc
from apps.shared.errors import AppError

from . import repository


def initiate(return_request):
    """Creates the cycle's InventoryReservation (does not attempt the
    decrement).
    """
    return repository.create_reservation(
        return_request["_id"], return_request["cycle"], return_request["exchangeSku"], return_request["quantity"]
    )


def initiate_and_advance(return_request):
    initiate(return_request)

    return advance(return_request)


def reservation(return_request):
    return repository.find_reservation(return_request["_id"], return_request["cycle"])


def advance(return_request):
    reservation_doc = repository.find_reservation(return_request["_id"], return_request["cycle"])

    if reservation_doc is None:
        # Crash point: ReturnRequest already moved to EXCHANGE_RESERVING but
        # the reservation for this cycle was never created.
        reservation_doc = repository.create_reservation(
            return_request["_id"], return_request["cycle"], return_request["exchangeSku"], return_request["quantity"]
        )

    if reservation_doc["status"] == "PENDING":
        reservation_doc = _resolve_pending(reservation_doc)

    if reservation_doc["status"] == "RESERVED":
        _advance_return(return_request, "COMPLETED", "EXCHANGE_CONFIRMED", {"completedAt": now_utc()})
        repository.prune_pending(reservation_doc["_id"])
    elif reservation_doc["status"] == "INSUFFICIENT":
        _advance_return(return_request, "EXCHANGE_AWAITING_INVENTORY", "EXCHANGE_INSUFFICIENT_INVENTORY", None)

    return reservation_doc


def _resolve_pending(reservation_doc):
    """Always (re-)attempt the decrement -- it is idempotent and safe to
    call even if it already succeeded (the guard simply won't match again).
    The result is interpreted AFTER the attempt, not before, so a
    concurrent racer applying the decrement between our check and our call
    can never be misread as "insufficient stock".
    """
    decrement_result = repository.apply_decrement(reservation_doc["_id"])

    if decrement_result is not None or repository.was_already_applied(reservation_doc["_id"]):
        resolved = repository.mark_reserved(reservation_doc["_id"])
    else:
        resolved = repository.mark_insufficient(reservation_doc["_id"])

    # mark_reserved/mark_insufficient are guarded on status=PENDING: if a
    # concurrent call already resolved this reservation, ours returns None
    # here and we fall back to reading the (correct, already-resolved) state.
    return resolved or repository.find_reservation_by_id(reservation_doc["_id"])


def _advance_return(return_request, new_status, action, extra_set):
    updated = return_repository.transition(
        return_request["_id"], ["EXCHANGE_RESERVING"], new_status, action, None, "system", extra_set=extra_set
    )

    if updated is not None:
        audit_service.project_entry("ReturnRequest", updated["_id"], updated["history"][-1])


def retry(return_request, actor):
    """Agent/Manager only: opens a brand-new reservation cycle, which can
    never collide with the exhausted one (unique {returnRequestId, cycle}).
    """
    next_cycle = return_request["cycle"] + 1
    updated = return_repository.transition(
        return_request["_id"],
        ["EXCHANGE_AWAITING_INVENTORY"],
        "EXCHANGE_RESERVING",
        "EXCHANGE_RESERVATION_RETRIED",
        actor["_id"],
        actor["role"],
        extra_set={"cycle": next_cycle},
    )

    if updated is None:
        current = return_repository.find_by_id(return_request["_id"])
        raise AppError(
            409,
            "RETURN_INVALID_TRANSITION",
            "This return is not awaiting an inventory retry.",
            {"currentState": current["status"] if current else None},
        )

    audit_service.project_entry("ReturnRequest", updated["_id"], updated["history"][-1])
    initiate_and_advance(updated)

    return return_repository.find_by_id(updated["_id"])
