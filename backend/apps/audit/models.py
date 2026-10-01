from mongoengine import DateTimeField, DictField, ObjectIdField, StringField

from apps.shared.documents import TimestampedDocument

MAX_ENTITY_TYPE_LENGTH = 40
MAX_ACTION_LENGTH = 60
MAX_ROLE_LENGTH = 20
MAX_STATE_LENGTH = 40


class AuditEvent(TimestampedDocument):
    """A derived, rebuildable READ projection -- never the source of truth.
    Authoritative workflow history lives on ReturnRequest.history[] (and
    RefundOperation.attempts[] / InventoryReservation status). This
    collection exists only for cross-entity views (activity feed, insights)
    that would be awkward to build by scanning every aggregate's own history.
    A missing/stale row here can never make a business metric wrong, because
    insights aggregate from the authoritative documents, not from this one.
    """

    meta = {
        "collection": "auditevents",
        "indexes": [{"fields": ["entity_type", "entity_id", "created_at"], "name": "entity_timeline_idx"}],
    }

    entity_type = StringField(db_field="entityType", required=True, max_length=MAX_ENTITY_TYPE_LENGTH)
    entity_id = ObjectIdField(db_field="entityId", required=True)
    action = StringField(required=True, max_length=MAX_ACTION_LENGTH)
    previous_state = StringField(db_field="previousState", null=True, max_length=MAX_STATE_LENGTH)
    new_state = StringField(db_field="newState", null=True, max_length=MAX_STATE_LENGTH)
    actor_id = ObjectIdField(db_field="actorId", null=True)
    actor_role = StringField(db_field="actorRole", max_length=MAX_ROLE_LENGTH)
    metadata = DictField(default=dict)
    at = DateTimeField(required=True)
