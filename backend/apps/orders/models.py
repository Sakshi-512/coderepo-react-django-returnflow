from bson import ObjectId
from mongoengine import (
    DateTimeField,
    DecimalField,
    EmbeddedDocument,
    EmbeddedDocumentListField,
    IntField,
    ObjectIdField,
    StringField,
)

from apps.shared.documents import TimestampedDocument

FULFILLMENT_STATUSES = ["pending", "shipped", "delivered", "cancelled"]
MAX_SKU_LENGTH = 40


class OrderItem(EmbeddedDocument):
    order_item_id = ObjectIdField(db_field="orderItemId", required=True, default=ObjectId)
    sku = StringField(required=True, max_length=MAX_SKU_LENGTH)
    quantity = IntField(required=True, min_value=1)
    unit_price = DecimalField(db_field="unitPrice", required=True, min_value=0, precision=2)
    fulfillment_status = StringField(db_field="fulfillmentStatus", choices=FULFILLMENT_STATUSES, default="delivered")
    delivered_at = DateTimeField(db_field="deliveredAt", null=True, default=None)


class Order(TimestampedDocument):
    meta = {
        "collection": "orders",
        "indexes": [
            {"fields": ["customer_id", "created_at"], "name": "customer_created_idx"},
            # Explicit db_field path ("orderItemId", not the Python attribute
            # name "order_item_id"): mongoengine's attribute-name-to-db_field
            # translation for index specs is only precedented in this
            # codebase for top-level fields (see the sample repo's own
            # owner_id_idx); a dotted path into an embedded document's field
            # is unverified, so this spells out the literal Mongo field path
            # to remove the ambiguity rather than rely on it.
            {"fields": ["items.orderItemId"], "name": "order_item_id_idx"},
        ],
    }

    customer_id = ObjectIdField(db_field="customerId", required=True)
    items = EmbeddedDocumentListField(OrderItem, default=list)
