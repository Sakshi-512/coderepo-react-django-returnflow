from datetime import datetime, timezone

from mongoengine import DateTimeField, Document


def now_utc():
    """Naive UTC, deliberately -- every datetime read back from MongoDB via
    .as_pymongo() throughout this codebase comes back timezone-naive
    (pymongo's default driver behavior; mongoengine.connect() here is not
    configured with tz_aware=True). now_utc() must match that convention,
    because the two real call sites that compare "now" against a persisted
    value (eligibility.evaluate's return-window check, refunds.services's
    nextRetryAt backoff check) would otherwise raise
    `TypeError: can't subtract offset-naive and offset-aware datetimes` --
    confirmed by running the suite against a real MongoDB. mongoengine
    normalizes aware datetimes to naive UTC on save regardless, so nothing
    written via the ODM changes; this only fixes in-memory comparisons.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stamp(document):
    moment = now_utc()

    if document.created_at is None:
        document.created_at = moment

    document.updated_at = moment

    return document


class TimestampedDocument(Document):
    meta = {"abstract": True}

    created_at = DateTimeField(db_field="createdAt")
    updated_at = DateTimeField(db_field="updatedAt")

    def save(self, *args, **kwargs):
        stamp(self)

        return super().save(*args, **kwargs)
