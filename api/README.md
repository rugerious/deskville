# Deskville API

FastAPI service for residents' questions. The council is taken from the verified Cognito ID token only ([D34](../docs/DECISIONS.md)).

| Endpoint | Auth | What it does |
|---|---|---|
| `GET /health` | none | load balancer health check, no database |
| `GET /search?q=…&k=5` | Bearer ID token | Titan embedding of `q` → `app.search_public` → public chunks with sources and date read |
| `GET /requests/{reference}` | Bearer ID token | one service request; another council's reference answers exactly like a missing one (404) |

Tests: `tests/test_api.py` (22), run by the `api` workflow on every PR against PostgreSQL + pgvector with the project's migrations and data, tokens signed with a key pair generated in the test, fake vectors instead of Bedrock. Locally:

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
DESKVILLE_TEST_DB="host=… port=… dbname=deskville user=deskville_app" .venv/bin/python -m unittest -v tests.test_api
```
