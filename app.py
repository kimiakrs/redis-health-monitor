from datetime import datetime, timezone
import os
import socket
import time
import logging
import json
import signal
from threading import Thread
from status_api import MonitoringState, create_status_server
# http.client is used to make HTTP requests to the Redis server for health checks.
from http.client import HTTPConnection, HTTPException
# urllib.error is used to handle errors that may occur during HTTP requests to the Redis server for health checks.
from urllib.error import URLError, HTTPError
# .request is used to make HTTP requests to the Redis server for health checks.
from urllib.request import Request, urlopen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
API_PORT = int(os.environ.get("API_PORT", "8081"))
STATUS_STALE_AFTER = float(os.environ.get("STATUS_STALE_AFTER", "30"))

CHECK_INTERVAL = 2
FAILURE_THRESHOLD = 3
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
WEBHOOK_TIMEOUT = 3 #Seconds
monitoring_state = MonitoringState(
    REDIS_HOST,
    REDIS_PORT,
    stale_after=STATUS_STALE_AFTER,
)






def ping_redis() -> None:
    """Raise an error if Redis does not respond with PONG."""
    with socket.create_connection(
        (REDIS_HOST, REDIS_PORT),
        timeout=2,
    ) as connection:
        connection.sendall(b"*1\r\n$4\r\nPING\r\n")

        with connection.makefile("rb") as response:
            reply = response.readline(256)

    if reply != b"+PONG\r\n":
        raise ConnectionError(f"Unexpected Redis response: {reply!r}")

def send_notification(payload: dict) -> None:
    """Attempt webhook delivery and log errors without interrupting monitoring."""
    if not WEBHOOK_URL:
        return

    try:
        request = Request(
            WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(request, timeout=WEBHOOK_TIMEOUT) as response:
            status = response.status

        if 200 <= status < 300:
            logging.info(
                "Webhook delivered; event=%s; status=%s",
                payload.get("event"),
                status,
            )
        else:
            logging.warning(
                "Webhook delivery failed; event=%s; status=%s",
                payload.get("event"),
                status,
            )

    except HTTPError as error:
        logging.warning(
            "Webhook delivery failed; event=%s; status=%s",
            payload.get("event"),
            error.code,
        )
        error.close()

    except (OSError, HTTPException, ValueError) as error:
        logging.warning(
            "Webhook delivery failed; event=%s; error_type=%s",
            payload.get("event"),
            type(error).__name__,
        )


def monitor_loop() -> None:
    failures = 0
    outage_reported = False
    first_success = True
    outage_started_at = None

    logging.info(
        "Monitoring Redis at %s:%s every %s seconds; failure threshold=%s",
        REDIS_HOST,
        REDIS_PORT,
        CHECK_INTERVAL,
        FAILURE_THRESHOLD,
    )

    while True:
        try:
            ping_redis()
            monitoring_state.record_check(
                    success=True,
                    failures=0,
                    alert_active=False,
                    outage_started_at=None,
                    )

            if outage_started_at is not None:
                # monotonic() is used to measure elapsed time, so we can calculate the outage duration even if the system clock changes.
                outage_duration = time.monotonic() - outage_started_at

                if outage_reported:
                    logging.info(
                        "RECOVERED: Redis is reachable again; "
                        "observed_outage_seconds=%.1f; failed_checks=%s",
                        outage_duration,
                        failures,
                    )
                    send_notification({
                        "event": "redis_recovered",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "host": REDIS_HOST,
                        "port": REDIS_PORT,
                        "observed_outage_seconds": round(outage_duration, 1),
                        "failed_checks": failures,
                    })

                else:
                    logging.info(
                        "Redis is reachable after a brief interruption; "
                        "observed_outage_seconds=%.1f; failed_checks=%s",
                        outage_duration,
                        failures,
                    )

            if first_success:
                logging.info("OK: Redis is reachable")
                first_success = False

            failures = 0
            outage_reported = False
            outage_started_at = None

        except OSError as error:
            if outage_started_at is None:
                outage_started_at = time.monotonic()

            failures += 1
            monitoring_state.record_check(
                    success=False,
                    failures=failures,
                    alert_active=failures >= FAILURE_THRESHOLD,
                    outage_started_at=outage_started_at,
                    )

            logging.warning(
                "Check failed (%s); error_type=%s; error=%s",
                failures,
                type(error).__name__,
                error,
            )

            if failures >= FAILURE_THRESHOLD and not outage_reported:
                logging.error(
                    "ALERT: Redis failed %s consecutive checks; "
                    "target=%s:%s; error_type=%s; error=%s",
                    failures,
                    REDIS_HOST,
                    REDIS_PORT,
                    type(error).__name__,
                    error,
                )
                outage_reported = True
                send_notification({
                    "event": "redis_unavailable",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "host": REDIS_HOST,
                    "port": REDIS_PORT,
                    "failed_checks": failures,
                })

        time.sleep(CHECK_INTERVAL)


def handle_termination(signum, frame) -> None:
    """Exit through the cleanup block when Docker requests shutdown."""
    raise SystemExit(0)


def main() -> None:
    # Binding happens here, so a port conflict fails before monitoring starts.
    server = create_status_server(monitoring_state, port=API_PORT)
    # ThreadingHTTPServer.serve_forever() is used to run the HTTP server in a separate thread, allowing the monitoring loop to continue running concurrently. 
    # The server thread is set as a daemon so that it will automatically exit when the main program exits.
    server_thread = Thread(
        target=server.serve_forever,
        name="status-api",
        daemon=True,
    )
    # Signal handling is set up to catch the SIGTERM signal, which is sent by Docker when the container is being stopped. The handle_termination function raises a SystemExit exception, which allows the program to exit gracefully and perform any necessary cleanup.
    signal.signal(signal.SIGTERM, handle_termination)

    try:
        server_thread.start()
        logging.info("Status API listening on port %s", API_PORT)
        monitor_loop()
    except KeyboardInterrupt:
        logging.info("Stopping Redis monitor")
    finally:
        if server_thread.is_alive():
            server.shutdown()
            server_thread.join()

        server.server_close()

if __name__ == "__main__":
    main()
