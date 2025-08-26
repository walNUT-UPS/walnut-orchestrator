# docker-full: Run frontend + backend together

This setup builds and runs both the walNUT backend and the React frontend in one compose file, with nginx serving the UI and reverse-proxying API and WebSockets to the backend.

## What it does

- Backend: `docker-full/Dockerfile.backend` (Gunicorn + Uvicorn workers), encrypted DB in `/app/data`.
- Frontend: `docker-full/Dockerfile.frontend` builds Vite assets and serves via nginx.
- nginx proxies `/api/*` and `/ws*` to the backend service.
- Single public port `8080` -> frontend; backend is only reachable via the proxy.

## Prereqs

- `.env` at repo root with required secrets (see `.env.example`):
  - `WALNUT_DB_KEY` (>= 32 chars), `WALNUT_JWT_SECRET`.
- Optional: `INSTALL_EXTRAS=transports` at build time to include SNMP/Modbus/NETCONF/gNMI.

## Build & Run

```
# From repo root
docker compose -f docker-full/docker-compose.yml up --build -d
```

Open http://localhost:8080

## Notes

- The backend database is persisted in the `walnut_data` volume.
- To change Gunicorn settings, set `WORKERS`, `TIMEOUT`, `KEEPALIVE` in `.env`.
- The nginx config (`docker-full/nginx.conf`) handles SPA fallback and proxies `/api` and `/ws` to `backend:8000`.
