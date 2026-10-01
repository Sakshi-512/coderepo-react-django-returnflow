"""Pure return-eligibility rules -- no I/O, no persistence, no wall-clock
reads. `services.submit_return` resolves order/product/completed-quantity
data first and injects `now` explicitly, so this module is fully
deterministic and testable: the same inputs always produce the same verdict.
"""

from .models import REASONS

RETURN_WINDOW_DAYS = 30


class Verdict:
    def __init__(self, eligible, rule_code=None):
        self.eligible = eligible
        self.rule_code = rule_code


def evaluate(now, order_item, product, completed_quantity, requested_quantity, reason, resolution_type, exchange_product):
    if order_item["fulfillmentStatus"] != "delivered" or order_item.get("deliveredAt") is None:
        return Verdict(False, "ORDER_ITEM_NOT_DELIVERED")

    if (now - order_item["deliveredAt"]).days > RETURN_WINDOW_DAYS:
        return Verdict(False, "RETURN_WINDOW_EXPIRED")

    if not product["returnable"]:
        return Verdict(False, "PRODUCT_NOT_RETURNABLE")

    if reason not in REASONS:
        return Verdict(False, "INVALID_REASON")

    remaining = order_item["quantity"] - completed_quantity

    if requested_quantity < 1 or requested_quantity > remaining:
        return Verdict(False, "QUANTITY_EXCEEDS_REMAINING")

    if resolution_type == "exchange":
        if exchange_product is None:
            return Verdict(False, "EXCHANGE_PRODUCT_NOT_FOUND")

        if exchange_product["variantGroup"] != product["variantGroup"]:
            return Verdict(False, "EXCHANGE_PRODUCT_NOT_IN_VARIANT_GROUP")

    return Verdict(True, None)
