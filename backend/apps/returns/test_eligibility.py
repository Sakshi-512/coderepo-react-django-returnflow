from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from . import eligibility

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)


def order_item(**overrides):
    return {
        "fulfillmentStatus": "delivered",
        "deliveredAt": NOW - timedelta(days=10),
        "quantity": 3,
        **overrides,
    }


def product(**overrides):
    return {"returnable": True, "variantGroup": "jacket", **overrides}


class EligibilityTests(SimpleTestCase):
    """Pure, no I/O, no live MongoDB required -- these genuinely execute."""

    def test_eligible_within_window(self):
        verdict = eligibility.evaluate(NOW, order_item(), product(), 0, 1, "defective", "refund", None)

        self.assertTrue(verdict.eligible)
        self.assertIsNone(verdict.rule_code)

    def test_ineligible_when_window_expired(self):
        item = order_item(deliveredAt=NOW - timedelta(days=eligibility.RETURN_WINDOW_DAYS + 1))
        verdict = eligibility.evaluate(NOW, item, product(), 0, 1, "defective", "refund", None)

        self.assertFalse(verdict.eligible)
        self.assertEqual(verdict.rule_code, "RETURN_WINDOW_EXPIRED")

    def test_exactly_at_window_boundary_is_eligible(self):
        item = order_item(deliveredAt=NOW - timedelta(days=eligibility.RETURN_WINDOW_DAYS))
        verdict = eligibility.evaluate(NOW, item, product(), 0, 1, "defective", "refund", None)

        self.assertTrue(verdict.eligible)

    def test_ineligible_when_not_delivered(self):
        item = order_item(fulfillmentStatus="pending")
        verdict = eligibility.evaluate(NOW, item, product(), 0, 1, "defective", "refund", None)

        self.assertEqual(verdict.rule_code, "ORDER_ITEM_NOT_DELIVERED")

    def test_ineligible_when_product_not_returnable(self):
        verdict = eligibility.evaluate(NOW, order_item(), product(returnable=False), 0, 1, "defective", "refund", None)

        self.assertEqual(verdict.rule_code, "PRODUCT_NOT_RETURNABLE")

    def test_ineligible_when_reason_invalid(self):
        verdict = eligibility.evaluate(NOW, order_item(), product(), 0, 1, "not_a_real_reason", "refund", None)

        self.assertEqual(verdict.rule_code, "INVALID_REASON")

    def test_ineligible_when_quantity_exceeds_purchased(self):
        verdict = eligibility.evaluate(NOW, order_item(quantity=3), product(), 0, 4, "defective", "refund", None)

        self.assertEqual(verdict.rule_code, "QUANTITY_EXCEEDS_REMAINING")

    def test_ineligible_when_quantity_exceeds_remaining_after_prior_completed_returns(self):
        # purchased 3, 2 already returned via a COMPLETED return -> only 1 remains
        verdict = eligibility.evaluate(NOW, order_item(quantity=3), product(), 2, 2, "defective", "refund", None)

        self.assertEqual(verdict.rule_code, "QUANTITY_EXCEEDS_REMAINING")

    def test_eligible_for_remaining_quantity_after_prior_completed_return(self):
        verdict = eligibility.evaluate(NOW, order_item(quantity=3), product(), 2, 1, "defective", "refund", None)

        self.assertTrue(verdict.eligible)

    def test_exchange_requires_a_resolved_replacement_product(self):
        verdict = eligibility.evaluate(NOW, order_item(), product(), 0, 1, "defective", "exchange", None)

        self.assertEqual(verdict.rule_code, "EXCHANGE_PRODUCT_NOT_FOUND")

    def test_exchange_requires_matching_variant_group(self):
        replacement = product(variantGroup="boots")
        verdict = eligibility.evaluate(NOW, order_item(), product(variantGroup="jacket"), 0, 1, "defective", "exchange", replacement)

        self.assertEqual(verdict.rule_code, "EXCHANGE_PRODUCT_NOT_IN_VARIANT_GROUP")

    def test_exchange_eligible_with_matching_variant_group(self):
        replacement = product(variantGroup="jacket")
        verdict = eligibility.evaluate(NOW, order_item(), product(variantGroup="jacket"), 0, 1, "defective", "exchange", replacement)

        self.assertTrue(verdict.eligible)
