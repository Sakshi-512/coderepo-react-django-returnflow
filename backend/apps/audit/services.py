"""Thin, best-effort projection wrapper. AuditEvent is never authoritative
(see repository.py) -- a projection failure here must never turn a
successful workflow write into a failed response, so every exception is
caught and logged, never raised.
"""

from . import repository


def project_entry(entity_type, entity_id, entry):
    try:
        repository.record(
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
    except Exception as error:
        print(f"[audit] projection failed for {entity_type} {entity_id}: {error!r}")
