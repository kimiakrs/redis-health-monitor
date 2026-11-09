import os
import socket
import time
import logging

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

CHECK_INTERVAL = float(os.environ.get("CHECK_INTERVAL", "2"))
FAILURE_THRESHOLD = int(os.environ.get("FAILURE_THRESHOLD", "3"))

if CHECK_INTERVAL <= 0:
    raise ValueError("CHECK_INTERVAL must be greater than zero")
if FAILURE_THRESHOLD < 1:
    raise ValueError("FAILURE_THRESHOLD must be at least one")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
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


def main() -> None:
    failures = 0
    outage_reported = False
    first_success = True

    print(f"Monitoring Redis at {REDIS_HOST}:{REDIS_PORT}", flush=True)

    while True:
        try:
            ping_redis()

            if outage_reported:
                logging.info("RECOVERED: Redis is reachable again")
            elif first_success:
                logging.info("OK: Redis is reachable")

            failures = 0
            outage_reported = False
            first_success = False

        except OSError as error:
            failures += 1
            logging.warning("Check failed (%s): (%s)", failures, error)

            if failures >= FAILURE_THRESHOLD and not outage_reported:
                logging.error(
                    "ALERT: Redis failed %s consecutive checks",
                    FAILURE_THRESHOLD,
                )
                outage_reported = True

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
