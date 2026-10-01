from bson import ObjectId
from django.test import SimpleTestCase

from apps.shared.errors import ValidationError

from . import schema


class ValidateSubmitTests(SimpleTestCase):
    def test_valid_refund_submission(self):
        values = schema.validate_submit(
            {
                "orderId": str(ObjectId()),
                "orderItemId": str(ObjectId()),
                "quantity": 1,
                "reason": "defective",
                "resolutionType": "refund",
            }
        )

        self.assertIsNone(values["exchangeSku"])

    def test_exchange_requires_exchange_sku(self):
        with self.assertRaises(ValidationError) as ctx:
            schema.validate_submit(
                {
                    "orderId": str(ObjectId()),
                    "orderItemId": str(ObjectId()),
                    "quantity": 1,
                    "reason": "defective",
                    "resolutionType": "exchange",
                }
            )

        self.assertIn("exchangeSku", ctx.exception.details["fieldErrors"])

    def test_rejects_malformed_object_ids(self):
        with self.assertRaises(ValidationError) as ctx:
            schema.validate_submit(
                {
                    "orderId": "not-an-object-id",
                    "orderItemId": str(ObjectId()),
                    "quantity": 1,
                    "reason": "defective",
                    "resolutionType": "refund",
                }
            )

        self.assertIn("orderId", ctx.exception.details["fieldErrors"])

    def test_rejects_invalid_reason(self):
        with self.assertRaises(ValidationError):
            schema.validate_submit(
                {
                    "orderId": str(ObjectId()),
                    "orderItemId": str(ObjectId()),
                    "quantity": 1,
                    "reason": "not_a_real_reason",
                    "resolutionType": "refund",
                }
            )


class ValidateRejectTests(SimpleTestCase):
    def test_valid_reject_with_enum_and_optional_note(self):
        values = schema.validate_reject({"reasonCode": "policy_violation", "reasonNote": "customer misused policy"})

        self.assertEqual(values["reasonCode"], "policy_violation")

    def test_reject_without_reason_note_defaults_to_empty(self):
        values = schema.validate_reject({"reasonCode": "other"})

        self.assertEqual(values["reasonNote"], "")

    def test_reject_rejects_arbitrary_reason_code_strings(self):
        with self.assertRaises(ValidationError):
            schema.validate_reject({"reasonCode": "i_felt_like_it"})


class ValidateInspectTests(SimpleTestCase):
    def test_valid_pass_verdict(self):
        values = schema.validate_inspect({"verdict": "pass"})

        self.assertEqual(values["verdict"], "pass")

    def test_rejects_invalid_verdict(self):
        with self.assertRaises(ValidationError):
            schema.validate_inspect({"verdict": "maybe"})
