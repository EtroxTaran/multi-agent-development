import http.client
import unittest

from src.server import HEALTH_BODY, start_server, stop_server


class HealthEndpointTests(unittest.TestCase):
    def test_health_returns_200_and_expected_body(self) -> None:
        running = start_server()
        try:
            conn = http.client.HTTPConnection(running.host, running.port, timeout=2)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")

            self.assertEqual(resp.status, 200)
            self.assertEqual(body, HEALTH_BODY)
        finally:
            stop_server(running)


if __name__ == "__main__":
    unittest.main()
