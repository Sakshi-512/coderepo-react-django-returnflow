from mongoengine import DateTimeField, DictField, EmbeddedDocument, EmbeddedDocumentField, EmbeddedDocumentListField, IntField, ObjectIdField, StringField

from apps.shared.documents import TimestampedDocument

MAX_SKU_LENGTH = 40
MAX_ROLE_LENGTH = 20
MAX_ACTION_LENGTH = 60
MAX_STATE_LENGTH = 40

RESOLUTION_TYPES = ["refund", "exchange"]
REASONS = ["defective", "wrong_item", "not_as_described", "no_longer_needed", "changed_mind"]
INSPECTION_VERDICTS = ["pass", "fail"]
REJECT_REASONS = ["policy_violation", "return_window_expired", "item_not_eligible", "duplicate_request", "other"]

STATUSES = [
    "REQUESTED",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
    "ITEM_RECEIVED",
    "INSPECTED",
    "REFUND_PROCESSING",
    "REFUND_FAILED",
    "EXCHANGE_RESERVING",
    "EXCHANGE_AWAITING_INVENTORY",
    "COMPLETED",
]

# The domain invariant this list encodes: at most one non-terminal
# ReturnRequest may exist per order line (see the partial unique index
# below). REFUND_FAILED is deliberately NOT terminal here -- the return is
# paused pending a Manager's explicit retry, not finished, so a second
# return cannot be opened against the same order line while it sits there.
TERMINAL_STATUSES = ["COMPLETED", "REJECTED", "CANCELLED"]
NON_TERMINAL_STATUSES = [status for status in STATUSES if status not in TERMINAL_STATUSES]


class Inspection(EmbeddedDocument):
    verdict = StringField(required=True, choices=INSPECTION_VERDICTS)
    notes = StringField(default="", max_length=1000)
    inspected_by = ObjectIdField(db_field="inspectedBy", required=True)
    inspected_at = DateTimeField(db_field="inspectedAt", required=True)


class HistoryEntry(EmbeddedDocument):
    action = StringField(required=True, max_length=MAX_ACTION_LENGTH)
    previous_state = StringField(db_field="previousState", null=True, max_length=MAX_STATE_LENGTH)
    new_state = StringField(db_field="newState", null=True, max_length=MAX_STATE_LENGTH)
    actor_id = ObjectIdField(db_field="actorId", null=True)
    actor_role = StringField(db_field="actorRole", max_length=MAX_ROLE_LENGTH)
    metadata = DictField(default=dict)
    at = DateTimeField(required=True)


class ReturnRequest(TimestampedDocument):
    meta = {
        "collection": "returnrequests",
        "indexes": [
            {"fields": ["status", "created_at"], "name": "status_created_idx"},
            {"fields": ["customer_id", "created_at"], "name": "customer_created_idx"},
            {"fields": ["order_id"], "name": "order_idx"},
            {
                "fields": ["order_item_id"],
                "unique": True,
                "partialFilterExpression": {"status": {"$in": NON_TERMINAL_STATUSES}},
                "name": "active_return_per_order_item_idx",
            },
        ],
    }

    customer_id = ObjectIdField(db_field="customerId", required=True)
    order_id = ObjectIdField(db_field="orderId", required=True)
    order_item_id = ObjectIdField(db_field="orderItemId", required=True)
    sku = StringField(required=True, max_length=MAX_SKU_LENGTH)
    quantity = IntField(required=True, min_value=1)
    reason = StringField(required=True, choices=REASONS)
    resolution_type = StringField(db_field="resolutionType", required=True, choices=RESOLUTION_TYPES)
    exchange_sku = StringField(db_field="exchangeSku", null=True, default=None, max_length=MAX_SKU_LENGTH)
    status = StringField(required=True, choices=STATUSES, default="REQUESTED")
    cycle = IntField(default=1, min_value=1)
    inspection = EmbeddedDocumentField(Inspection, null=True, default=None)
    # Authoritative workflow history -- every transition appends here in the
    # SAME atomic write that changes `status`, so state and history can never
    # diverge. AuditEvent (apps/audit) is a derived, rebuildable projection of
    # this array; it is never the source of truth.
    history = EmbeddedDocumentListField(HistoryEntry, default=list)
    approved_at = DateTimeField(db_field="approvedAt", null=True, default=None)
    received_at = DateTimeField(db_field="receivedAt", null=True, default=None)
    completed_at = DateTimeField(db_field="completedAt", null=True, default=None)
