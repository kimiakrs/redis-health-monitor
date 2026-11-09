import os
import socket
import time

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

    print(f"Monitoring Redis at {REDIS_HOST}:{REDIS_PORT}", flush=True)

    while True:
        try:
            ping_redis()

            if outage_reported:
                print("RECOVERED: Redis is reachable again", flush=True)
            elif first_success:
                print("OK: Redis is reachable", flush=True)

            failures = 0
            outage_reported = False
            first_success = False

        except OSError as error:
            failures += 1
            print(f"Check failed ({failures}): {error}", flush=True)

            if failures >= FAILURE_THRESHOLD and not outage_reported:
                print(
                    f"ALERT: Redis failed {FAILURE_THRESHOLD} consecutive checks",
                    flush=True,
                )
                outage_reported = True

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
