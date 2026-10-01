from apps.shared.validation import Errors, read_number, read_object_id, read_option, read_string

from .models import INSPECTION_VERDICTS, REASONS, REJECT_REASONS, RESOLUTION_TYPES

MAX_NOTE_LENGTH = 1000
MAX_QUANTITY = 100
MAX_SKU_LENGTH = 40
MAX_PAGE_SIZE = 50
EXCHANGE_SKU_REQUIRED_MESSAGE = "Choose a replacement item for an exchange."


def validate_submit(body):
    errors = Errors()
    values = {
        "orderId": read_object_id(errors, body, "orderId"),
        "orderItemId": read_object_id(errors, body, "orderItemId"),
        "quantity": read_number(errors, body, "quantity", minimum=1, maximum=MAX_QUANTITY),
        "reason": read_option(errors, body, "reason", REASONS),
        "resolutionType": read_option(errors, body, "resolutionType", RESOLUTION_TYPES),
    }

    exchange_sku = None

    if body.get("resolutionType") == "exchange":
        exchange_sku = read_string(errors, body, "exchangeSku", trim=True, minimum=1, maximum=MAX_SKU_LENGTH)

        if not errors.field_errors.get("exchangeSku") and not exchange_sku:
            errors.add("exchangeSku", EXCHANGE_SKU_REQUIRED_MESSAGE)

    values["exchangeSku"] = exchange_sku

    errors.raise_if_any()

    return values


def validate_reject(body):
    errors = Errors()
    values = {
        "reasonCode": read_option(errors, body, "reasonCode", REJECT_REASONS),
        "reasonNote": read_string(errors, body, "reasonNote", default="", trim=True, maximum=MAX_NOTE_LENGTH),
    }

    errors.raise_if_any()

    return values


def validate_inspect(body):
    errors = Errors()
    values = {
        "verdict": read_option(errors, body, "verdict", INSPECTION_VERDICTS),
        "notes": read_string(errors, body, "notes", default="", trim=True, maximum=MAX_NOTE_LENGTH),
    }

    errors.raise_if_any()

    return values


def validate_list(query):
    errors = Errors()
    status = str(query.get("status") or "")
    values = {
        "status": [item for item in status.split(",") if item] or None,
        "reason": query.get("reason") or None,
        "resolutionType": query.get("resolutionType") or None,
        "orderId": query.get("orderId") or None,
        "customerEmail": query.get("customerEmail") or None,
        "page": read_number(errors, query, "page", default=1, minimum=1),
        "pageSize": read_number(errors, query, "pageSize", default=20, minimum=1, maximum=MAX_PAGE_SIZE),
    }

    errors.raise_if_any()

    return values
