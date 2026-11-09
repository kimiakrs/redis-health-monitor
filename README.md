# Redis Health Monitor

A Python mini project that monitors Redis availability using Docker Compose.

## Features

- Checks Redis with PING.
- Reports an alert after three consecutive failures.
- Reports recovery when Redis responds again.
- Reads the Redis hostname and port from environment variables.

## Run

```bash
docker compose -p redis-health-monitor up -d
docker compose -p redis-health-monitor logs -f monitor
```

## Test an outage

In another terminal:

```bash
docker compose -p redis-health-monitor stop redis
```

Wait for the alert, then restore Redis:

```bash
docker compose -p redis-health-monitor start redis
```

Check the monitor logs for the recovery message.

## Stop

```bash
docker compose -p redis-health-monitor down
```

## Requirements

Docker Engine and Docker Compose.
