from mongoengine import BooleanField, DecimalField, StringField

from apps.shared.documents import TimestampedDocument

MAX_NAME_LENGTH = 160
MAX_SKU_LENGTH = 40


class Product(TimestampedDocument):
    meta = {
        "collection": "products",
        "indexes": [{"fields": ["sku"], "unique": True, "name": "sku_unique_idx"}],
    }

    sku = StringField(required=True, max_length=MAX_SKU_LENGTH)
    name = StringField(required=True, max_length=MAX_NAME_LENGTH)
    price = DecimalField(required=True, min_value=0, precision=2)
    variant_group = StringField(db_field="variantGroup", required=True, max_length=MAX_SKU_LENGTH)
    returnable = BooleanField(default=True)
