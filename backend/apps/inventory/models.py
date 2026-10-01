from mongoengine import IntField, ListField, ObjectIdField, StringField

from apps.shared.documents import TimestampedDocument

MAX_SKU_LENGTH = 40
RESERVATION_STATUSES = ["PENDING", "RESERVED", "INSUFFICIENT", "RELEASED"]


class Inventory(TimestampedDocument):
    meta = {
        "collection": "inventory",
        "indexes": [{"fields": ["sku"], "unique": True, "name": "sku_unique_idx"}],
    }

    sku = StringField(required=True, max_length=MAX_SKU_LENGTH)
    available_quantity = IntField(db_field="availableQuantity", required=True, min_value=0)
    reserved_quantity = IntField(db_field="reservedQuantity", required=True, min_value=0, default=0)
    # Bounded idempotency ledger: holds only reservation ids currently mid-flight
    # between a decrement attempt and that reservation's status being durably
    # resolved (RESERVED/INSUFFICIENT). Entries are pruned once resolved, so this
    # never grows with the SKU's all-time reservation volume. See
    # apps/inventory/repository.py for the invariant this protects.
    pending_reservation_ids = ListField(ObjectIdField(), db_field="pendingReservationIds", default=list)


class InventoryReservation(TimestampedDocument):
    meta = {
        "collection": "inventoryreservations",
        "indexes": [
            {"fields": ["return_request_id", "cycle"], "unique": True, "name": "return_cycle_unique_idx"},
        ],
    }

    return_request_id = ObjectIdField(db_field="returnRequestId", required=True)
    cycle = IntField(required=True, min_value=1)
    sku = StringField(required=True, max_length=MAX_SKU_LENGTH)
    quantity = IntField(required=True, min_value=1)
    status = StringField(choices=RESERVATION_STATUSES, default="PENDING", required=True)
