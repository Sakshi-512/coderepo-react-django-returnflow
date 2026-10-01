from bson import ObjectId
from mongoengine.errors import NotUniqueError

from apps.audit import services as audit_service
from apps.catalog import repository as catalog_repository
from apps.inventory import services as inventory_service
from apps.orders import repository as order_repository
from apps.refunds import services as refund_service
from apps.shared.documents import now_utc
from apps.shared.errors import AppError
from apps.shared.validation import is_object_id

from . import eligibility, repository

RETURN_NOT_FOUND_MESSAGE = "The requested return does not exist."


def ensure_identifier(return_id):
    if not is_object_id(return_id):
        raise AppError(404, "RETURN_NOT_FOUND", RETURN_NOT_FOUND_MESSAGE)


def ensure_viewable(return_id, viewer):
    ensure_identifier(return_id)
    existing = repository.find_by_id(return_id)

    if existing is None:
        raise AppError(404, "RETURN_NOT_FOUND", RETURN_NOT_FOUND_MESSAGE)

    if viewer["role"] == "customer" and str(existing["customerId"]) != str(viewer["_id"]):
        raise AppError(404, "RETURN_NOT_FOUND", RETURN_NOT_FOUND_MESSAGE)

    return existing


def get_by_id(return_id, viewer):
    return ensure_viewable(return_id, viewer)


def list_returns(query, viewer):
    conditions = {}

    if viewer["role"] == "customer":
        conditions["customerId"] = ObjectId(viewer["_id"])
    elif query.get("customerEmail"):
        from apps.auth import repository as auth_repository

        account = auth_repository.find_active_by_email(query["customerEmail"].lower())
        conditions["customerId"] = ObjectId(account["_id"]) if account else ObjectId()

    if query.get("status"):
        conditions["status"] = {"$in": query["status"]}

    if query.get("reason"):
        conditions["reason"] = query["reason"]

    if query.get("resolutionType"):
        conditions["resolutionType"] = query["resolutionType"]

    if query.get("orderId") and is_object_id(query["orderId"]):
        conditions["orderId"] = ObjectId(query["orderId"])

    return repository.find_by_conditions(conditions, query["page"], query["pageSize"])


def _find_order_item(order, order_item_id):
    return next((item for item in order["items"] if str(item["orderItemId"]) == str(order_item_id)), None)


def submit_return(values, customer):
    order = order_repository.find_by_id(values["orderId"])

    if order is None or str(order["customerId"]) != str(customer["_id"]):
        raise AppError(404, "ORDER_NOT_FOUND", "The requested order does not exist.")

    order_item = _find_order_item(order, values["orderItemId"])

    if order_item is None:
        raise AppError(404, "ORDER_ITEM_NOT_FOUND", "The requested order item does not exist.")

    product = catalog_repository.find_by_sku(order_item["sku"])

    if product is None:
        raise AppError(422, "PRODUCT_NOT_FOUND", "This item is no longer in the catalog.")

    exchange_product = None

    if values["resolutionType"] == "exchange":
        exchange_product = catalog_repository.find_by_sku(values["exchangeSku"])

    completed_quantity = repository.completed_quantity_for_order_item(values["orderItemId"])
    now = now_utc()
    verdict = eligibility.evaluate(
        now,
        order_item,
        product,
        completed_quantity,
        values["quantity"],
        values["reason"],
        values["resolutionType"],
        exchange_product,
    )

    eligible = verdict.eligible
    status = "REQUESTED" if eligible else "REJECTED"
    # NOTE: this history list is passed through the mongoengine ODM
    # constructor (repository.create -> ReturnRequest(**values)), which
    # requires Python attribute names (previous_state, actor_id, ...), NOT
    # the db_field names (previousState, actorId, ...) that repository.py's
    # raw-pymongo transition() uses for every later push. Both end up stored
    # identically on disk; only the construction-time key names differ.
    history = [
        {
            "action": "RETURN_REQUESTED",
            "previous_state": None,
            "new_state": "REQUESTED" if eligible else None,
            "actor_id": ObjectId(customer["_id"]),
            "actor_role": "customer",
            "metadata": {},
            "at": now,
        }
    ]

    if not eligible:
        history.append(
            {
                "action": "RETURN_REJECTED",
                "previous_state": "REQUESTED",
                "new_state": "REJECTED",
                "actor_id": None,
                "actor_role": "system",
                "metadata": {"stage": "eligibility", "ruleCode": verdict.rule_code},
                "at": now,
            }
        )

    document_values = {
        "customer_id": ObjectId(customer["_id"]),
        "order_id": ObjectId(values["orderId"]),
        "order_item_id": ObjectId(values["orderItemId"]),
        "sku": order_item["sku"],
        "quantity": values["quantity"],
        "reason": values["reason"],
        "resolution_type": values["resolutionType"],
        "exchange_sku": values.get("exchangeSku"),
        "status": status,
        "history": history,
    }

    try:
        created = repository.create(document_values)
    except NotUniqueError:
        raise AppError(409, "DUPLICATE_ACTIVE_RETURN", "An active return already exists for this order item.")

    for entry in created["history"]:
        audit_service.project_entry("ReturnRequest", created["_id"], entry)

    return created


def _finish(updated, return_id):
    if updated is None:
        current = repository.find_by_id(return_id)

        if current is None:
            raise AppError(404, "RETURN_NOT_FOUND", RETURN_NOT_FOUND_MESSAGE)

        raise AppError(409, "RETURN_INVALID_TRANSITION", "This return has already moved on.", {"currentState": current["status"]})

    audit_service.project_entry("ReturnRequest", updated["_id"], updated["history"][-1])

    return updated


def cancel(return_id, customer):
    ensure_viewable(return_id, customer)  # role=="customer": also enforces ownership, else 404

    updated = repository.transition(return_id, ["REQUESTED"], "CANCELLED", "RETURN_CANCELLED", customer["_id"], "customer")

    return _finish(updated, return_id)


def approve(return_id, actor):
    ensure_identifier(return_id)
    updated = repository.transition(
        return_id, ["REQUESTED"], "APPROVED", "RETURN_APPROVED", actor["_id"], actor["role"], extra_set={"approvedAt": now_utc()}
    )

    return _finish(updated, return_id)


def reject(return_id, actor, reason_code, reason_note):
    ensure_identifier(return_id)
    updated = repository.transition(
        return_id,
        ["REQUESTED"],
        "REJECTED",
        "RETURN_REJECTED",
        actor["_id"],
        actor["role"],
        metadata={"stage": "review", "reasonCode": reason_code, "reasonNote": reason_note},
    )

    return _finish(updated, return_id)


def receive(return_id, actor):
    ensure_identifier(return_id)
    updated = repository.transition(
        return_id, ["APPROVED"], "ITEM_RECEIVED", "ITEM_RECEIVED", actor["_id"], actor["role"], extra_set={"receivedAt": now_utc()}
    )

    return _finish(updated, return_id)


def inspect(return_id, actor, verdict, notes, forced_refund_profile=None):
    """`forced_refund_profile` exists only so the deterministic seed script
    can drive a pinned refund demo scenario through this same real service
    function -- see refunds.services.initiate. The real POST .../inspect
    view never passes it, so production behavior is unaffected.
    """
    ensure_identifier(return_id)
    now = now_utc()
    inspection = {"verdict": verdict, "notes": notes, "inspectedBy": ObjectId(actor["_id"]), "inspectedAt": now}

    if verdict == "pass":
        updated = repository.transition(
            return_id,
            ["ITEM_RECEIVED"],
            "INSPECTED",
            "ITEM_INSPECTED",
            actor["_id"],
            actor["role"],
            metadata={"verdict": "pass"},
            extra_set={"inspection": inspection},
        )
        updated = _finish(updated, return_id)

        return _initiate_resolution(updated, forced_refund_profile=forced_refund_profile)

    updated = repository.transition(
        return_id,
        ["ITEM_RECEIVED"],
        "REJECTED",
        "RETURN_REJECTED",
        actor["_id"],
        actor["role"],
        metadata={"stage": "inspection", "verdict": "fail"},
        extra_set={"inspection": inspection},
    )

    return _finish(updated, return_id)


def _initiate_resolution(return_request, forced_refund_profile=None):
    """Runs inline, in the same request as the passing inspection, so the
    common case resolves in one round trip. This is not a background job:
    it is a synchronous call within the current request, and the same
    resolution service function remains independently callable later
    (via POST .../refund/attempt or .../exchange/retry-reservation) for
    recovery if this call is interrupted -- see the crash matrices in the
    Phase 2 architecture.
    """
    if return_request["resolutionType"] == "refund":
        updated = repository.transition(
            return_request["_id"], ["INSPECTED"], "REFUND_PROCESSING", "REFUND_INITIATED", None, "system", extra_set={"cycle": 1}
        )
        updated = _finish(updated, return_request["_id"])
        _try_advance_inline(
            lambda rr: refund_service.initiate_and_advance(rr, forced_profile=forced_refund_profile), updated
        )
    else:
        updated = repository.transition(
            return_request["_id"], ["INSPECTED"], "EXCHANGE_RESERVING", "EXCHANGE_INITIATED", None, "system", extra_set={"cycle": 1}
        )
        updated = _finish(updated, return_request["_id"])
        _try_advance_inline(inventory_service.initiate_and_advance, updated)

    return repository.find_by_id(return_request["_id"])


def _try_advance_inline(advance_fn, return_request):
    """The ITEM_INSPECTED -> REFUND_PROCESSING/EXCHANGE_RESERVING transition
    has ALREADY committed by the time this runs. If the immediate cascade
    attempt fails for any reason, that must not make this inspect() call
    look like it failed -- the actual state change the caller asked for did
    succeed. The return is left exactly as if a real process crash had
    happened at this point: persisted, correct, and recoverable by the next
    explicit POST .../refund/attempt or .../exchange/retry-reservation call,
    per the Phase 2 crash matrix. Never silently retried in a loop here --
    that would be reintroducing a background job by another name.
    """
    try:
        advance_fn(return_request)
    except Exception as error:
        print(f"[returns] inline resolution cascade failed for {return_request['_id']}: {error!r}")
