import json
import unittest
from urllib.error import HTTPError, URLError
#unit test for the notification sending functionality of the app module. It uses unittest and unittest.mock to test different scenarios of sending notifications via a webhook.
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
# First test case checks that when the webhook URL is disabled (set to an empty string), the send_notification function does not attempt to make any HTTP requests. It uses patch.object to mock the urlopen function and asserts that it was not called.
 # patch.object is used to mock the urlopen function in the app module, allowing the tests to simulate different responses and errors without making actual HTTP requests.
    @patch.object(app, "urlopen")
    def test_disabled_webhook_sends_nothing(self, mock_urlopen):
        with patch.object(app, "WEBHOOK_URL", ""):
            app.send_notification(self.payload)

        mock_urlopen.assert_not_called()

# what is urlopen? urlopen is a function from the urllib module in Python that is used to open URLs. It can be used to send HTTP requests and receive responses from web servers. In this context, it is being mocked to test the behavior of the send_notification function without making actual HTTP requests.
    @patch.object(app, "urlopen")
    def test_successful_delivery(self, mock_urlopen):
        # Mock the response to simulate a successful delivery with a 204 No Content status code.
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
        # assertEqual is used to check that the HTTP request method is POST, the payload sent in the request matches the expected payload, 
        # and the timeout value used in the request matches the configured webhook timeout. It also checks that a log message indicating successful delivery is present in the logs.
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            #jason.loads is used to parse the JSON data sent in the request and compare it with the expected payload.
            #payload is the data that is being sent in the notification, which is a dictionary containing information about the event, host, port, and failed checks.
            json.loads(request.data.decode("utf-8")),
            # self.payload is the expected payload that should be sent in the notification. It is defined in the setUp method of the test case and contains the same information as the payload being sent in the request.
            self.payload,
        )
        self.assertEqual(
            mock_urlopen.call_args.kwargs["timeou t"],
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
                        #assertLogs is used to check that a log message indicating a webhook delivery failure is present in the logs when an error occurs during the notification sending process. It captures the log output at the WARNING level and asserts that the expected log message is present.
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
