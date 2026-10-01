from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase
from mongoengine.connection import get_db
from rest_framework.test import APIClient

from .testing import test_database_uri


class TestDatabaseUriTests(SimpleTestCase):
    def test_appends_test_suffix_to_db_name_only(self):
        self.assertEqual(
            test_database_uri("mongodb://localhost:27017/returnflow_db"),
            "mongodb://localhost:27017/returnflow_db_test",
        )

    def test_preserves_host_and_query_string(self):
        self.assertEqual(
            test_database_uri("mongodb://user:pass@localhost:27017/returnflow_db?retryWrites=true"),
            "mongodb://user:pass@localhost:27017/returnflow_db_test?retryWrites=true",
        )


class RunningUnderTestRunnerTests(SimpleTestCase):
    """Proves the custom MongoTestRunner actually reconnected to an isolated
    database before this test (or any test) runs -- see
    apps/shared/testing.py::MongoTestRunner.
    """

    def test_active_connection_is_the_isolated_test_database(self):
        active_db_name = get_db().name
        configured_dev_db_name = settings.MONGODB_URI.rsplit("/", 1)[-1]

        self.assertTrue(active_db_name.endswith("_test"))
        self.assertNotEqual(active_db_name, configured_dev_db_name)


class ApiWiringTests(SimpleTestCase):
    """Exercises the URL/view/error-handling plumbing end to end through
    Django's test client. Deliberately limited to paths that do not require
    a live MongoDB connection, so these genuinely run in this environment.
    """

    def setUp(self):
        self.client = APIClient()

    def test_health_degrades_gracefully_without_crashing_when_mongo_is_unreachable(self):
        """Deliberately mocks the MongoDB ping rather than relying on the
        ambient environment's real connectivity: whether a live MongoDB
        happens to be reachable while this suite runs must not change the
        outcome of a test that specifically claims to exercise the
        unreachable-database branch. The production health endpoint
        (apps/shared/views.py) is untouched -- only its dependency is
        stubbed for the duration of this one request.
        """
        with patch("apps.shared.views.get_db", side_effect=Exception("simulated MongoDB outage")):
            response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["data"]["status"], "degraded")
        self.assertEqual(response.data["data"]["database"], "disconnected")

    def test_login_with_missing_fields_returns_validation_error_shape(self):
        response = self.client.post("/api/v1/auth/login", {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("email", response.data["error"]["details"]["fieldErrors"])
        self.assertIn("password", response.data["error"]["details"]["fieldErrors"])

    def test_unauthenticated_session_request_is_rejected(self):
        response = self.client.get("/api/v1/auth/session")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "AUTH_REQUIRED")

    def test_unknown_route_outside_api_prefix_returns_not_found_error_shape(self):
        response = self.client.get("/totally-unknown-path")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")

    def test_unknown_api_route_requires_auth_before_reporting_not_found(self):
        """Matches the sample repo's own convention: unmatched /api/v1/*
        routes are auth-gated before falling through to route_not_found, so
        an unauthenticated caller sees 401, not a 404 that would otherwise
        leak route existence."""
        response = self.client.get("/api/v1/does-not-exist")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "AUTH_REQUIRED")
