import io
import json
import unittest
from unittest import mock
from wsgiref.util import setup_testing_defaults

from v2.backend.wsgi import MAX_REQUEST_BODY_BYTES, application


class WsgiTests(unittest.TestCase):
    def request(self, body=b"{}", **overrides):
        environ = {}
        setup_testing_defaults(environ)
        environ.update({
            "PATH_INFO": "/api/analyze",
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        })
        environ.update(overrides)
        response = {}

        def start_response(status, headers):
            response["status"] = int(status.split()[0])
            response["headers"] = dict(headers)

        data = b"".join(application(environ, start_response))
        self.assertEqual(int(response["headers"]["Content-Length"]), len(data))
        return response["status"], response["headers"], json.loads(data)

    def test_analysis_uses_existing_api(self):
        payload = {"user_id": "test", "actor_name": "artist", "year": "2025"}
        with mock.patch("v2.backend.wsgi.build_analysis_response", return_value=(200, {"status": "success"})) as analyze:
            status, _, result = self.request(json.dumps(payload).encode())
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "success")
        analyze.assert_called_once_with(payload)

    def test_rejects_bad_requests_before_analysis(self):
        cases = [
            (b"{}", {"CONTENT_LENGTH": ""}, 411),
            (b"{}", {"CONTENT_LENGTH": "-1"}, 400),
            (b"{}", {"CONTENT_LENGTH": "invalid"}, 400),
            (b"{}", {"CONTENT_LENGTH": str(MAX_REQUEST_BODY_BYTES + 1)}, 413),
            (b"{}", {"CONTENT_LENGTH": "3"}, 400),
            (b"{", {}, 400),
            (b"\xff", {}, 400),
            (b"{}", {"CONTENT_TYPE": "text/plain"}, 415),
        ]
        with mock.patch("v2.backend.wsgi.build_analysis_response") as analyze:
            for body, overrides, expected in cases:
                with self.subTest(overrides=overrides, body=body):
                    status, _, result = self.request(body, **overrides)
                    self.assertEqual(status, expected)
                    self.assertEqual(result["status"], "error")
            analyze.assert_not_called()

    def test_accepts_body_at_size_limit_and_json_charset(self):
        body = b"{}" + b" " * (MAX_REQUEST_BODY_BYTES - 2)
        with mock.patch("v2.backend.wsgi.build_analysis_response", return_value=(200, {"status": "success"})):
            status, _, _ = self.request(body, CONTENT_TYPE="application/json; charset=utf-8")
        self.assertEqual(status, 200)

    def test_validation_errors_use_existing_response_shape(self):
        status, _, result = self.request()
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "error")

    def test_health_unknown_path_and_method(self):
        self.assertEqual(self.request(PATH_INFO="/health", REQUEST_METHOD="GET")[0], 200)
        self.assertEqual(self.request(PATH_INFO="/missing")[0], 404)
        status, headers, _ = self.request(REQUEST_METHOD="GET")
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "POST")
