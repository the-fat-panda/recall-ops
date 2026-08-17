# Orders API sandbox

This intentionally tiny FastAPI service demonstrates a real connection-pool exhaustion incident against the configured CockroachDB cluster. It has no fake failure path: `/health` and `/orders` hold an acquired database connection for 1.5 seconds. With `v2.8.1`'s pool size of one, three concurrent health checks force at least one acquire to exceed the two-second pool timeout and return HTTP 500.

## Run and prove the rollback

From the repository root, with `DATABASE_URL` in `.env`:

```powershell
python -m backend.sandbox.migrate_orders
docker compose up -d --build orders-api
curl http://localhost:8080/version
python scripts/trigger_incident.py
curl -X POST http://localhost:8080/rollback
python scripts/trigger_incident.py
curl -X POST http://localhost:8080/reset
```

Expected flow:

1. `/version` initially returns `{"version":"v2.8.1","pool_size":1}`.
2. The first trigger prints at least one HTTP 500 with `"reason":"connection pool exhausted"`.
3. `/rollback` returns `{"rolled_back_to":"v2.8.0","pool_size":20}`.
4. The second trigger prints three HTTP 200 responses.
5. `/reset` restores the intentionally broken `v2.8.1` configuration for another demo.

`POST /reset` is a demo helper, not an operational runbook action.
