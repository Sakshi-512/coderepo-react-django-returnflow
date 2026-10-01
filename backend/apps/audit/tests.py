from datetime import datetime, timezone

from bson import ObjectId
from django.test import SimpleTestCase

from . import repository
from .models import AuditEvent


class AuditProjectionTests(SimpleTestCase):
    """AuditEvent is a derived projection, never authoritative (see the
    module docstring in repository.py and models.py). These tests prove the
    only property that matters for that claim: projecting the same source
    event any number of times produces exactly one row.
    """

    def setUp(self):
        AuditEvent.objects.delete()

    def tearDown(self):
        AuditEvent.objects.delete()

    def test_recording_the_same_source_event_twice_creates_one_row(self):
        entity_id = ObjectId()
        actor_id = ObjectId()
        at = datetime.now(timezone.utc).replace(microsecond=0)

        repository.record("ReturnRequest", entity_id, "RETURN_APPROVED", "REQUESTED", "APPROVED", actor_id, "agent", {}, at)
        repository.record("ReturnRequest", entity_id, "RETURN_APPROVED", "REQUESTED", "APPROVED", actor_id, "agent", {}, at)

        rows = repository.find_for_entity("ReturnRequest", entity_id)
        self.assertEqual(len(rows), 1)

    def test_reproject_from_history_is_idempotent_and_order_independent(self):
        entity_id = ObjectId()
        actor_id = ObjectId()
        history = [
            {
                "action": "RETURN_REQUESTED",
                "previousState": None,
                "newState": "REQUESTED",
                "actorId": actor_id,
                "actorRole": "customer",
                "metadata": {},
                "at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            },
            {
                "action": "RETURN_APPROVED",
                "previousState": "REQUESTED",
                "newState": "APPROVED",
                "actorId": actor_id,
                "actorRole": "agent",
                "metadata": {},
                "at": datetime(2026, 1, 2, tzinfo=timezone.utc),
            },
        ]

        repository.reproject_from_history("ReturnRequest", entity_id, history)
        repository.reproject_from_history("ReturnRequest", entity_id, history)  # simulate a repeated/rerun projection

        rows = repository.find_for_entity("ReturnRequest", entity_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["action"] for row in rows}, {"RETURN_REQUESTED", "RETURN_APPROVED"})
