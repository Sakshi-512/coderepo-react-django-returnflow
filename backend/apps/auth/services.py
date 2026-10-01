import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from django.conf import settings

from apps.shared.errors import AppError
from apps.shared.validation import is_object_id

from . import repository

TOKEN_ALGORITHM = "HS256"
DURATION_PATTERN = re.compile(r"^(\d+)([smhd])$")
SECONDS_PER_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}
DEFAULT_EXPIRY_SECONDS = 86400
INVALID_TOKEN_MESSAGE = "Your ReturnFlow session is invalid or has expired."


def expiry_seconds(value):
    matched = DURATION_PATTERN.match(value or "")

    if not matched:
        return DEFAULT_EXPIRY_SECONDS

    return int(matched.group(1)) * SECONDS_PER_UNIT[matched.group(2)]


def public_account(account):
    return {"_id": str(account["_id"]), "name": account["name"], "email": account["email"], "role": account["role"]}


def sign(account):
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": str(account["_id"]),
        "role": account["role"],
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=expiry_seconds(settings.JWT_EXPIRES_IN)),
        "aud": settings.JWT_AUDIENCE,
        "iss": settings.JWT_ISSUER,
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=TOKEN_ALGORITHM)


def login(email, password):
    account = repository.find_active_by_email(email.lower())
    valid = account is not None and bcrypt.checkpw(password.encode(), account["passwordHash"].encode())

    if not valid:
        raise AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")

    return {"account": public_account(account), "token": sign(account)}


def decode(token):
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[TOKEN_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except jwt.PyJWTError:
        raise AppError(401, "INVALID_TOKEN", INVALID_TOKEN_MESSAGE)


def authenticate(token):
    payload = decode(token)

    if not is_object_id(payload.get("sub")):
        raise AppError(401, "INVALID_TOKEN", INVALID_TOKEN_MESSAGE)

    account = repository.find_active_by_id(payload["sub"])

    if account is None:
        raise AppError(401, "ACCOUNT_UNAVAILABLE", "This ReturnFlow account is no longer available.")

    return public_account(account), payload


def session(account):
    return {"account": account}
