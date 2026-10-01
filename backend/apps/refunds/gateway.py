"""Deterministic, dependency-free simulation of a payment gateway.

No real payment provider exists. `assign_profile` is pure and derived from
sha256 (stable across processes and machines -- unlike Python's built-in
`hash()`, which is salted per-process and must never be used for anything
that needs to reproduce the same result later or elsewhere). The profile is
computed once, when a RefundOperation cycle is created, and persisted; every
later attempt reads the stored profile rather than re-deriving anything, so
`simulate_charge` is a pure, deterministic lookup table.
"""

import hashlib

PROFILES = ["ALWAYS_SUCCEED", "FAIL_THEN_SUCCEED", "ALWAYS_FAIL"]
SUCCEEDED = "SUCCEEDED"
FAILED_RETRYABLE = "FAILED_RETRYABLE"


def assign_profile(return_request_id, cycle):
    digest = hashlib.sha256(f"{return_request_id}:{cycle}".encode("utf-8")).digest()
    bucket = digest[0] % 100

    if bucket < 85:
        return "ALWAYS_SUCCEED"

    if bucket < 97:
        return "FAIL_THEN_SUCCEED"

    return "ALWAYS_FAIL"


def simulate_charge(profile, attempt):
    """Returns SUCCEEDED or FAILED_RETRYABLE for the given profile/attempt.
    Pure function: identical inputs always produce the identical outcome.
    """
    if profile == "ALWAYS_SUCCEED":
        return SUCCEEDED

    if profile == "FAIL_THEN_SUCCEED":
        return SUCCEEDED if attempt >= 2 else FAILED_RETRYABLE

    if profile == "ALWAYS_FAIL":
        return FAILED_RETRYABLE

    raise ValueError(f"Unknown simulated gateway profile: {profile}")
