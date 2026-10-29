"""#951 — FastAPI >= 0.132 (`strict_content_type`, the default) rejects a JSON body sent WITHOUT a
Content-Type header before any handler runs. The console always sends `application/json` and tests use
`json=`; the docstrings that invite curl / script callers now say the header is required. Deliberately
NOT disabled: it is FastAPI's CSRF hardening for exactly this kind of unauthenticated localhost app."""
import json

from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server

ROUTE = "/api/handoff/dispatch"   # `{}` returns 400 'no districts selected' before any DB access — a DB-free control


def test_json_body_without_content_type_is_422_before_any_handler():
    r = TestClient(server.app).post(ROUTE, content=json.dumps({}))        # no Content-Type at all
    assert r.status_code == 422 and "dict_type" in r.text


def test_json_body_with_content_type_reaches_the_handler():
    r = TestClient(server.app).post(ROUTE, json={})
    assert r.status_code == 400 and "no districts selected" in r.text
