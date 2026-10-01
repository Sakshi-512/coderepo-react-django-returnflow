"""Refund workflow orchestration. No background worker exists anywhere in
this system -- every attempt is advanced by an explicit call to advance()
(wired to POST .../refund/attempt), never a scheduled job. `nextRetryAt` is
computed and checked entirely server-side.
"""

from apps.audit import services as audit_service
from apps.returns import repository as return_repository
from apps.shared.documents import now_utc
from apps.shared.errors import AppError

from . import gateway, repository


def initiate(return_request, forced_profile=None):
    """Creates the cycle's RefundOperation (does not execute an attempt).

    `forced_profile` exists only so the deterministic seed script can pin an
    exact demo scenario through this same real code path -- see
    refunds.repository.create_operation. The real POST .../inspect view
    never passes it, so production behavior is unaffected.
    """
    return repository.create_operation(return_request["_id"], return_request["cycle"], forced_profile=forced_profile)


def initiate_and_advance(return_request, forced_profile=None):
    initiate(return_request, forced_profile=forced_profile)

    return advance(return_request)


def history(return_request):
    return repository.find_by_return(return_request["_id"])


def advance(return_request):
    """The single entry point for both the normal "next attempt" path and
    crash recovery -- see the Phase 2 architecture's refund crash matrix.
    Safe to call any number of times, from any state, including immediately
    after a crash at any point in a prior call.
    """
    operation = repository.find_by_return_and_cycle(return_request["_id"], return_request["cycle"])

    if operation is None:
        # Crash point: ReturnRequest already moved to REFUND_PROCESSING but
        # the operation for this cycle was never created.
        operation = repository.create_operation(return_request["_id"], return_request["cycle"])

    if operation["status"] != "PENDING":
        # Crash point: an attempt was already recorded (this operation is
        # already terminal) but the ReturnRequest was never advanced.
        return _propagate(return_request, operation)

    now = now_utc()

    if operation.get("nextRetryAt") and now < operation["nextRetryAt"]:
        raise AppError(
            409, "RETRY_NOT_YET_ELIGIBLE", "This refund cannot be retried yet.", {"nextRetryAt": operation["nextRetryAt"]}
        )

    attempt = len(operation["attempts"]) + 1
    outcome = gateway.simulate_charge(operation["simulatedProfile"], attempt)
    updated_operation = repository.record_attempt(operation["_id"], attempt, outcome)

    if updated_operation is None:
        # Guard didn't match: a concurrent call already recorded this exact
        # attempt slot. Re-read and propagate whatever is now true rather
        # than treat this as an error.
        updated_operation = repository.find_by_return_and_cycle(return_request["_id"], return_request["cycle"])

    return _propagate(return_request, updated_operation)


def _propagate(return_request, operation):
    if operation["status"] == "SUCCEEDED":
        _advance_return(return_request, "COMPLETED", "RETURN_COMPLETED", {"completedAt": now_utc()})
    elif operation["status"] == "FAILED_TERMINAL":
        _advance_return(return_request, "REFUND_FAILED", "REFUND_FAILED", None)

    return operation


def _advance_return(return_request, new_status, action, extra_set):
    updated = return_repository.transition(
        return_request["_id"], ["REFUND_PROCESSING"], new_status, action, None, "system", extra_set=extra_set
    )

    if updated is not None:
        audit_service.project_entry("ReturnRequest", updated["_id"], updated["history"][-1])


def retry(return_request, actor):
    """Manager-only: opens a brand-new cycle, which can never collide with
    the exhausted one (new idempotency key, new unique-indexed document).
    """
    next_cycle = return_request["cycle"] + 1
    updated = return_repository.transition(
        return_request["_id"],
        ["REFUND_FAILED"],
        "REFUND_PROCESSING",
        "REFUND_RETRY_INITIATED",
        actor["_id"],
        actor["role"],
        extra_set={"cycle": next_cycle},
    )

    if updated is None:
        current = return_repository.find_by_id(return_request["_id"])
        raise AppError(
            409,
            "RETURN_INVALID_TRANSITION",
            "This return is not awaiting a refund retry.",
            {"currentState": current["status"] if current else None},
        )

    audit_service.project_entry("ReturnRequest", updated["_id"], updated["history"][-1])
    initiate_and_advance(updated)

    return return_repository.find_by_id(updated["_id"])
