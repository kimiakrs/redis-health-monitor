import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

import app


class NotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "event": "redis_unavailable",
            "host": "redis",
            "port": 6379,
            "failed_checks": 3,
        }

    @patch.object(app, "urlopen")
    def test_disabled_webhook_sends_nothing(self, mock_urlopen):
        with patch.object(app, "WEBHOOK_URL", ""):
            app.send_notification(self.payload)

        mock_urlopen.assert_not_called()

    @patch.object(app, "urlopen")
    def test_successful_delivery(self, mock_urlopen):
        response = MagicMock()
        response.status = 204
        mock_urlopen.return_value.__enter__.return_value = response

        with patch.object(
            app, "WEBHOOK_URL", "http://receiver:8080/events"
        ):
            with self.assertLogs(level="INFO") as logs:
                app.send_notification(self.payload)

        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args.args[0]

        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            self.payload,
        )
        self.assertEqual(
            mock_urlopen.call_args.kwargs["timeout"],
            app.WEBHOOK_TIMEOUT,
        )
        self.assertTrue(
            any("Webhook delivered" in line for line in logs.output)
        )

    def test_delivery_errors_are_logged(self):
        errors = [
            URLError("Receiver unavailable"),
            TimeoutError("Receiver timed out"),
            HTTPError(
                "http://receiver:8080/events",
                500,
                "Internal Server Error",
                None,
                None,
            ),
        ]

        for error in errors:
            with self.subTest(error=type(error).__name__):
                with patch.object(
                    app, "WEBHOOK_URL", "http://receiver:8080/events"
                ):
                    with patch.object(
                        app, "urlopen", side_effect=error
                    ) as mock_urlopen:
                        with self.assertLogs(level="WARNING") as logs:
                            app.send_notification(self.payload)

                mock_urlopen.assert_called_once()
                self.assertTrue(
                    any(
                        "Webhook delivery failed" in line
                        for line in logs.output
                    )
                )


if __name__ == "__main__":
    unittest.main()
