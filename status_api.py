"""Status API for Redis Health Monitor."""

from datetime import datetime, timezone

# Lock is used to ensure that only one thread can access a shared resource
# at a time, preventing race conditions and ensuring thread safety.
# In this context, it synchronizes access to the status data when multiple
# threads may be updating or reading it concurrently.
from threading import Lock

import time

import math

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Creating an instance of the MonitoringState class to manage the monitoring state of the Redis service.
class MonitoringState:
    # __init__ is a special method in Python classes that is called
    # when an instance of the class is created.
    # stale_after is a parameter that specifies the duration (in seconds) after which the monitoring state is considered stale if no new checks have been recorded. It defaults to 30 seconds.
    def __init__(self, host: str, port: int, stale_after: float = 30,) -> None:
        if not math.isfinite(stale_after) or stale_after <= 0:
            raise ValueError("stale_after must be a positive number")
        self._stale_after = stale_after
        self._last_checked_monotonic: float | None = None
        # What is _lock? _lock is an instance variable that holds a Lock object.
        # The underscore indicates that it is intended for internal use.
        # It synchronizes access to shared resources in a multi-threaded
        # environment, ensuring that only one thread holding this lock
        # can access the protected resource at a time.

        self._lock = Lock()

        # | None is a type hint indicating that the variable can either
        # be of type float or None.
        self._outage_started_at: float | None = None

        self._data = {
            "service": "redis",
            "host": host,
            "port": port,
            "status": "unknown",
            "last_checked_at": None,
            "last_success_at": None,
            "consecutive_failures": 0,
            "alert_active": False,
        }

    def record_check(
        self,
        *,
        success: bool,
        failures: int,
        alert_active: bool,
        outage_started_at: float | None,
    ) -> None:
        # This instance method updates the monitoring state based on
        # the result of a health check. It takes four keyword-only arguments:
        # success: whether the check was successful.
        # failures: the number of consecutive failures.
        # alert_active: whether the failure threshold has been reached.
        # outage_started_at: the monotonic time of the first failed check,
        # or None when no outage is active.
        with self._lock:
            self._last_checked_monotonic = time.monotonic()
            # Why the underscore when accessing self._data?
            # The underscore prefix indicates that it is intended for
            # internal use. Python still allows access from outside the class.
            # Within instance methods, we access and modify this dictionary
            # to update the monitoring state.
            checked_at = datetime.now(timezone.utc).isoformat()
            self._data["last_checked_at"] = checked_at

            if success:
                self._data["status"] = "up"
                self._data["last_success_at"] = checked_at
                self._data["consecutive_failures"] = 0
                self._outage_started_at = None
            else:
                self._data["status"] = "down"
                self._data["consecutive_failures"] = failures

                # The monitoring loop supplies the original outage start time.
                # It uses time.monotonic(), matching the duration calculation.
                self._outage_started_at = outage_started_at

            self._data["alert_active"] = alert_active

    def snapshot(self) -> dict:
        """Return an independent, consistent copy of the current state."""
        with self._lock:
            result = self._data.copy()
            result["current_outage_seconds"] = None

            if self._outage_started_at is not None:
                result["current_outage_seconds"] = round(
                    time.monotonic() - self._outage_started_at,
                    1,
                )
            if self._last_checked_monotonic is not None:
                if (
                    time.monotonic() - self._last_checked_monotonic
                    > self._stale_after
                ):
                    result["status"] = "stale"
            return result

        
def create_status_server(
    state: MonitoringState,
    host: str = "0.0.0.0",
    port: int = 8081,
) -> ThreadingHTTPServer:
    """Create the HTTP server using the monitor's shared state."""

    class StatusHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/status":
                payload = state.snapshot()
            elif self.path == "/healthz":
                payload = {"status": "ok"}
            else:
                self.send_error(404, "Unknown endpoint")
                return

            body = json.dumps(payload).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), StatusHandler)
