import os
import socket
import time
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

CHECK_INTERVAL = 2
FAILURE_THRESHOLD = 3




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


def main() -> None:
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

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
