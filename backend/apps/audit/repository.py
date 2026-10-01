"""Append-only by construction: this module exposes only `record` (idempotent
upsert-insert) and `find_for_entity` (read). There is no update or delete
function anywhere in this module, so the only way this collection changes is
by inserting a new, distinct natural-keyed row.
"""

from bson import ObjectId

from apps.shared.mongo import collection

from .models import AuditEvent


def record(entity_type, entity_id, action, previous_state, new_state, actor_id, actor_role, metadata, at):
    """Upsert on the natural key {entityType, entityId, action, previousState,
    newState, at} -- `at` is the SOURCE event's own timestamp (e.g. the
    ReturnRequest.history[] entry's `at`), not "time of projection", so
    projecting the same source event any number of times, from any process,
    in any order, produces exactly one row.
    """
    key = {
        "entityType": entity_type,
        "entityId": ObjectId(entity_id),
        "action": action,
        "previousState": previous_state,
        "newState": new_state,
        "at": at,
    }

    return collection(AuditEvent).update_one(
        key,
        {
            "$setOnInsert": {
                **key,
                "actorId": ObjectId(actor_id) if actor_id else None,
                "actorRole": actor_role,
                "metadata": metadata or {},
            }
        },
        upsert=True,
    )


def find_for_entity(entity_type, entity_id):
    return list(
        AuditEvent.objects(__raw__={"entityType": entity_type, "entityId": ObjectId(entity_id)})
        .order_by("-created_at")
        .as_pymongo()
    )


def reproject_from_history(entity_type, entity_id, history_entries):
    """Rebuild this entity's AuditEvent rows from its authoritative history.
    Safe to run any number of times (each entry upserts on its natural key) --
    this is how a missing/failed `record()` call is ever recovered from, and
    it never needs a destructive truncate-and-rebuild.
    """
    for entry in history_entries:
        record(
            entity_type,
            entity_id,
            entry["action"],
            entry.get("previousState"),
            entry.get("newState"),
            entry.get("actorId"),
            entry.get("actorRole"),
            entry.get("metadata"),
            entry["at"],
        )
