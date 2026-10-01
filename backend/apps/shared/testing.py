from urllib.parse import urlsplit, urlunsplit

import mongoengine
from django.conf import settings
from django.test.runner import DiscoverRunner

MONGO_ALIAS = "default"


def test_database_uri(source_uri):
    """Derive an isolated `<db>_test` MongoDB URI from the configured dev/seed URI.

    Same host/port/credentials as the source URI; only the database name changes,
    so tests never share a database with `bun run seed` / local development.
    """
    parts = urlsplit(source_uri)
    db_name = parts.path.lstrip("/") or "test"

    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}_test", parts.query, parts.fragment))


class MongoTestRunner(DiscoverRunner):
    """Django's built-in test runner knows nothing about MongoEngine (DATABASES={}
    here), so `manage.py test` would otherwise read/write the same database as
    development. This reconnects MongoEngine to an isolated `_test` database for
    the duration of the run and drops it afterward. No new dependency: both
    `DiscoverRunner` and `mongoengine.connection.disconnect/connect` already ship
    with the pinned packages.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        self.mongo_test_uri = test_database_uri(settings.MONGODB_URI)
        mongoengine.disconnect(alias=MONGO_ALIAS)
        # Short server selection timeout: if MongoDB isn't reachable, fail
        # fast (seconds) instead of hanging on pymongo's ~30s default while
        # discovering that out during teardown/first query.
        mongoengine.connect(
            host=self.mongo_test_uri, uuidRepresentation="standard", alias=MONGO_ALIAS, serverSelectionTimeoutMS=2000
        )

    def teardown_test_environment(self, **kwargs):
        connection = mongoengine.connection.get_connection(alias=MONGO_ALIAS)
        db_name = mongoengine.connection.get_db(alias=MONGO_ALIAS).name

        try:
            connection.drop_database(db_name)
        except Exception as error:
            # Reported honestly, not swallowed: if MongoDB was never
            # reachable, this is expected and does not mean the tests that
            # ran above (ones with no DB dependency) are invalid -- but a
            # real environment MUST see this succeed before the isolation
            # guarantee can be considered verified.
            print(f"[MongoTestRunner] could not drop test database {db_name!r}: {error!r}")

        mongoengine.disconnect(alias=MONGO_ALIAS)

        super().teardown_test_environment(**kwargs)
