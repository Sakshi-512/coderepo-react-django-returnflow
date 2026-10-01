import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATE_KEY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OFFSET_SUFFIX_PATTERN = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def is_time_zone(value):
    if not isinstance(value, str):
        return False

    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False

    return True


def to_utc(value):
    if value.tzinfo is None:
        return value

    return value.astimezone(timezone.utc).replace(tzinfo=None)


def parse_instant(value):
    if isinstance(value, datetime):
        return to_utc(value)

    if not isinstance(value, str):
        return None

    text = value.strip()

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None and not OFFSET_SUFFIX_PATTERN.search(text):
        return parsed.astimezone().astimezone(timezone.utc).replace(tzinfo=None)

    return to_utc(parsed)
