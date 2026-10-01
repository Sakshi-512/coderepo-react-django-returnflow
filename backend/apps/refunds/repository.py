from datetime import datetime, timedelta, timezone

from bson import ObjectId
from mongoengine.errors import NotUniqueError
from pymongo import ReturnDocument

from apps.shared.mongo import collection

from . import gateway
from .models import MAX_ATTEMPTS, RefundOperation

BACKOFF_BASE_SECONDS = 5


def idempotency_key(return_request_id, cycle):
    return f"refund:{return_request_id}:{cycle}"


def find_by_return(return_request_id):
    return list(
        RefundOperation.objects(__raw__={"returnRequestId": ObjectId(return_request_id)})
        .order_by("-cycle")
        .as_pymongo()
    )


def find_by_return_and_cycle(return_request_id, cycle):
    return RefundOperation.objects(
        __raw__={"returnRequestId": ObjectId(return_request_id), "cycle": cycle}
    ).as_pymongo().first()


def create_operation(return_request_id, cycle, forced_profile=None):
    """Idempotent: a duplicate call for the same (return_request_id, cycle)
    returns the existing operation rather than creating a second one, so a
    retried "ensure this cycle's RefundOperation exists" call never risks a
    duplicate charge.

    `forced_profile` exists ONLY for deterministic seed/demo setup: it lets
    the seed script pin an exact scenario (e.g. "this demo return always
    fails") without depending on which hash bucket a return id happens to
    land in. Organic/production code never passes it, so real returns are
    always governed by gateway.assign_profile().
    """
    existing = find_by_return_and_cycle(return_request_id, cycle)

    if existing is not None:
        return existing

    if forced_profile is not None and forced_profile not in gateway.PROFILES:
        raise ValueError(f"Unknown forced_profile: {forced_profile}")

    key = idempotency_key(return_request_id, cycle)
    profile = forced_profile or gateway.assign_profile(str(return_request_id), cycle)

    try:
        document = RefundOperation(
            return_request_id=ObjectId(return_request_id),
            cycle=cycle,
            idempotency_key=key,
            simulated_profile=profile,
            status="PENDING",
        ).save()
    except NotUniqueError:
        # A genuinely concurrent caller won the race on the same
        # idempotency key between our existence check and our insert.
        # That's the intended idempotent outcome, not an error: return
        # whatever they created.
        return find_by_return_and_cycle(return_request_id, cycle)

    return collection(RefundOperation).find_one({"_id": document.id})


def backoff_seconds(attempt):
    return BACKOFF_BASE_SECONDS * (3 ** (attempt - 1))


def record_attempt(operation_id, attempt, outcome):
    """Single-document atomic write: appends the attempt and advances
    status/nextRetryAt together, so there is no partially-recorded attempt.

    The guard requires `attempts` to currently have exactly `attempt - 1`
    entries. Without this, a repeated call for the same attempt number would
    still match a plain `status: "PENDING"` guard whenever the outcome is
    FAILED_RETRYABLE (status legitimately stays PENDING to allow the *next*
    attempt), letting two concurrent/duplicate calls both push an entry for
    the same attempt. The size guard makes attempt recording strictly
    sequential and exactly-once per attempt number, and doubles as the
    concurrency guard: only one of two racing calls can match a given array
    size at a time.
    """
    now = datetime.now(timezone.utc)
    is_terminal_failure = outcome == "FAILED_RETRYABLE" and attempt >= MAX_ATTEMPTS
    next_status = "SUCCEEDED" if outcome == "SUCCEEDED" else ("FAILED_TERMINAL" if is_terminal_failure else "PENDING")
    next_retry_at = None if next_status != "PENDING" else now + timedelta(seconds=backoff_seconds(attempt))

    return collection(RefundOperation).find_one_and_update(
        {"_id": ObjectId(operation_id), "status": "PENDING", "attempts": {"$size": attempt - 1}},
        {
            "$push": {"attempts": {"attempt": attempt, "outcome": outcome, "at": now}},
            "$set": {"status": next_status, "nextRetryAt": next_retry_at, "updatedAt": now},
        },
        return_document=ReturnDocument.AFTER,
    )
