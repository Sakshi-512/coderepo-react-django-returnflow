from mongoengine import BooleanField, StringField

from apps.shared.documents import TimestampedDocument

ROLES = ["customer", "agent", "warehouse", "manager"]


class WorkspaceAccount(TimestampedDocument):
    meta = {
        "collection": "workspaceaccounts",
        "indexes": [{"fields": ["email"], "unique": True, "name": "email_unique_idx"}],
    }

    name = StringField(required=True, max_length=120)
    email = StringField(required=True, max_length=254)
    password_hash = StringField(db_field="passwordHash", required=True)
    role = StringField(required=True, choices=ROLES)
    active = BooleanField(default=True)
