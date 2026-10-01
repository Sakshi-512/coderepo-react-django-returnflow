from mongoengine import DateTimeField, EmbeddedDocument, EmbeddedDocumentListField, IntField, ObjectIdField, StringField

from apps.shared.documents import TimestampedDocument
from apps.shared.documents import now_utc

from .gateway import PROFILES

OPERATION_STATUSES = ["PENDING", "SUCCEEDED", "FAILED_TERMINAL"]
MAX_ATTEMPTS = 3


class RefundAttempt(EmbeddedDocument):
    attempt = IntField(required=True, min_value=1)
    outcome = StringField(required=True, choices=["SUCCEEDED", "FAILED_RETRYABLE"])
    at = DateTimeField(required=True, default=now_utc)


class RefundOperation(TimestampedDocument):
    meta = {
        "collection": "refundoperations",
        "indexes": [
            {"fields": ["idempotency_key"], "unique": True, "name": "idempotency_key_unique_idx"},
            {"fields": ["return_request_id"], "name": "return_request_idx"},
        ],
    }

    return_request_id = ObjectIdField(db_field="returnRequestId", required=True)
    cycle = IntField(required=True, min_value=1)
    idempotency_key = StringField(db_field="idempotencyKey", required=True, max_length=120)
    simulated_profile = StringField(db_field="simulatedProfile", required=True, choices=PROFILES)
    status = StringField(choices=OPERATION_STATUSES, default="PENDING", required=True)
    max_attempts = IntField(db_field="maxAttempts", default=MAX_ATTEMPTS)
    next_retry_at = DateTimeField(db_field="nextRetryAt", null=True, default=None)
    attempts = EmbeddedDocumentListField(RefundAttempt, default=list)
