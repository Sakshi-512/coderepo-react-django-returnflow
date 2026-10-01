from datetime import datetime, timezone

from bson import ObjectId
from rest_framework.renderers import JSONRenderer
from rest_framework.utils.encoders import JSONEncoder

MILLISECONDS_PER_MICROSECOND = 1000


def to_iso_string(value):
    moment = value.astimezone(timezone.utc) if value.tzinfo else value
    milliseconds = moment.microsecond // MILLISECONDS_PER_MICROSECOND

    return f"{moment.strftime('%Y-%m-%dT%H:%M:%S')}.{milliseconds:03d}Z"


class ApiEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)

        if isinstance(obj, datetime):
            return to_iso_string(obj)

        return super().default(obj)


class ApiRenderer(JSONRenderer):
    encoder_class = ApiEncoder
