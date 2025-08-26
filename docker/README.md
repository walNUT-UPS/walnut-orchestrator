# Docker usage

This folder contains Docker assets to build and run the walNUT backend.

## Images

- Multi-stage build with a slim Python runtime
- Installs SQLCipher runtime and optional tools (ipmitool, telnet)
- Exposes `8000` and runs `uvicorn walnut.app:app`

## Requirements

- Set `WALNUT_DB_KEY` to a strong secret (>=32 chars). Required for SQLCipher.
- Optional: set `INSTALL_EXTRAS=transports` to include SNMP/Modbus/NETCONF/gNMI clients.

## Build

```
# From repo root
docker build -f docker/Dockerfile -t walnut/walnut-api:dev .
# Include optional transports
docker build -f docker/Dockerfile --build-arg INSTALL_EXTRAS=transports -t walnut/walnut-api:transports .
```

### Production build

```
# Plain prod build
docker build -f docker/Dockerfile.prod -t walnut/walnut-api:prod .
# With optional transports
docker build -f docker/Dockerfile.prod --build-arg INSTALL_EXTRAS=transports -t walnut/walnut-api:prod-transports .
```

## Run

```
# Simple run
docker run --rm -p 8000:8000 \
  -e WALNUT_DB_KEY="<at_least_32_chars>" \
  -v walnut_data:/app/data \
  walnut/walnut-api:dev
```

Or via Compose:

```
# Create .env next to this file or export in shell
# WALNUT_DB_KEY=<at_least_32_chars>
# INSTALL_EXTRAS=transports   # optional

docker compose -f docker/docker-compose.yml up --build -d
```

### Production Compose

```
# .env should define WALNUT_DB_KEY and optionally INSTALL_EXTRAS, WORKERS, TIMEOUT, KEEPALIVE
docker compose -f docker/docker-compose.prod.yml up --build -d
```

## Notes

- The encrypted database is stored in `/app/data/walnut.db` (volume `walnut_data`).
- For IPMI operations, the image includes the `ipmitool` binary.
- SNMP/Modbus/gNMI/NETCONF client libraries are included only when `INSTALL_EXTRAS=transports` is set at build time.
- Frontend is not included; this image serves the backend API only.
