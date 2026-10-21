from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import recorder


class ZoomTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_disabled_without_level(self):
        with patch.object(recorder, "build_opener") as opener:
            recorder.set_zoom()
            opener.assert_not_called()

    @patch.dict(os.environ, {"VIDEO_URL": "https://user:p%40ss@camera:8080/video",
                             "ZOOM_LEVEL": "20"}, clear=True)
    def test_default_endpoint_and_credentials(self):
        self.assertEqual(recorder.zoom_config(),
                         ("https://camera:8080/ptz?zoom=20", "user", "p%40ss"))

    @patch.dict(os.environ, {"ZOOM_LEVEL": "20",
                             "ZOOM_URL": "https://proxy/camera/ptz?token=example&zoom=1"}, clear=True)
    def test_override_preserves_other_parameters(self):
        url, user, password = recorder.zoom_config()
        self.assertEqual(urlsplit(url).path, "/camera/ptz")
        self.assertEqual(parse_qs(urlsplit(url).query), {"token": ["example"], "zoom": ["20"]})
        self.assertIsNone(user)
        self.assertIsNone(password)

    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video"}, clear=True)
    def test_invalid_level_rejected(self):
        for value in ("-1", "1.5", "20&other=1", "abc"):
            with self.subTest(value=value), patch.dict(os.environ, {"ZOOM_LEVEL": value}):
                with self.assertRaises(ValueError):
                    recorder.zoom_config()

    def test_post_and_http_failure(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append((self.command, self.path, self.headers.get("Content-Length")))
                self.send_response(503 if self.path.startswith("/fail") else 200)
                self.end_headers()

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with patch.dict(os.environ, {"VIDEO_URL": base + "/video", "ZOOM_LEVEL": "20"}, clear=True):
                recorder.set_zoom()
                self.assertEqual(requests, [("POST", "/ptz?zoom=20", "0")])
                with patch.dict(os.environ, {"ZOOM_URL": base + "/fail"}):
                    with self.assertRaises(HTTPError):
                        recorder.set_zoom()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
