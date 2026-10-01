from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from apps.shared.mongo import collection

from .models import ReturnRequest


def find_by_id(return_request_id):
    return ReturnRequest.objects(__raw__={"_id": ObjectId(return_request_id)}).as_pymongo().first()


def find_by_customer(customer_id):
    return list(
        ReturnRequest.objects(__raw__={"customerId": ObjectId(customer_id)}).order_by("-created_at").as_pymongo()
    )


def find_by_status(statuses):
    return list(ReturnRequest.objects(__raw__={"status": {"$in": statuses}}).order_by("created_at").as_pymongo())


def find_by_conditions(conditions, page, page_size):
    query = ReturnRequest.objects(__raw__=conditions).order_by("created_at")
    total = query.count()
    items = list(query.skip((page - 1) * page_size).limit(page_size).as_pymongo())

    return {"items": items, "total": total}


def completed_quantity_for_order_item(order_item_id):
    """Sum of quantity already returned via COMPLETED returns for this order
    line -- the only quantity-accounting check needed, since at most one
    non-terminal return can ever exist per order line (partial unique index).
    """
    pipeline = [
        {"$match": {"orderItemId": ObjectId(order_item_id), "status": "COMPLETED"}},
        {"$group": {"_id": None, "total": {"$sum": "$quantity"}}},
    ]
    result = list(collection(ReturnRequest).aggregate(pipeline))

    return result[0]["total"] if result else 0


def create(values):
    """Raises mongoengine.errors.NotUniqueError if an active (non-terminal)
    return already exists for this order line -- the partial unique index on
    order_item_id is the sole enforcement mechanism for that invariant.
    """
    document = ReturnRequest(**values).save()

    return collection(ReturnRequest).find_one({"_id": document.id})


def transition(return_request_id, allowed_from_statuses, new_status, action, actor_id, actor_role, metadata=None, extra_set=None):
    """The single building block every workflow transition uses: one atomic
    `find_one_and_update` that changes `status` (guarded on the current
    status being one of `allowed_from_statuses`) and appends the matching
    history entry, in the same write. There is no window where the status
    changes without its history entry, because it is the same document
    mutation, not a sequence.

    `previousState` is captured with a two-stage pipeline update referencing
    `$status` in the FIRST stage -- the document's status as it existed
    before this write -- rather than a value read beforehand. Pipeline
    stages execute strictly in sequence (each stage's output feeds the
    next), so stage 1 is guaranteed to see the pre-update status regardless
    of same-stage field-evaluation order, unlike a plain pre-read: a pre-read
    would be racy whenever `allowed_from_statuses` has more than one member,
    since a different transition could move the document between two states
    that are both in that set within the read-then-write window, silently
    recording the wrong previousState even though the write's own guard
    still matched correctly.

    Returns None if the guard didn't match (return not found, or already
    moved out of an allowed source state) -- callers translate that into a
    409 RETURN_INVALID_TRANSITION.
    """
    now = datetime.now(timezone.utc)
    pipeline = [
        {
            "$set": {
                "history": {
                    "$concatArrays": [
                        {"$ifNull": ["$history", []]},
                        [
                            {
                                "action": action,
                                "previousState": "$status",
                                "newState": new_status,
                                "actorId": ObjectId(actor_id) if actor_id else None,
                                "actorRole": actor_role,
                                "metadata": metadata or {},
                                "at": now,
                            }
                        ],
                    ]
                }
            }
        },
        {"$set": {"status": new_status, "updatedAt": now, **(extra_set or {})}},
    ]

    return collection(ReturnRequest).find_one_and_update(
        {"_id": ObjectId(return_request_id), "status": {"$in": allowed_from_statuses}},
        pipeline,
        return_document=ReturnDocument.AFTER,
    )
