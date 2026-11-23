import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_vercel_entry_serves_app():
    from api.index import app
    c = TestClient(app)
    assert c.get("/api/health").json() == {"ok": True, "template": True}
    assert c.get("/").status_code == 200
    assert c.get("/static/sample.md").status_code == 200
