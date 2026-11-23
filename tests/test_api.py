import io
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import app  # noqa: E402

client = TestClient(app)
SAMPLE = (ROOT / "samples" / "sample_draft.md").read_text(encoding="utf-8")


def test_index_and_static():
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_parse_and_build():
    data = client.post("/api/parse", json={"markdown": SAMPLE}).json()
    assert len(data["agendas"]) == 3
    r = client.post("/api/build", json={"data": data, "meta": {"dept": "교육과정과", "team": "새팀", "leader": "홍길동"},
                                        "filename": "주간회의(새팀)"})
    assert r.status_code == 200
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    sec = zipfile.ZipFile(io.BytesIO(r.content)).read("Contents/section0.xml").decode()
    assert "새팀" in sec and "홍길동" in sec


def test_parse_rejects_empty():
    r = client.post("/api/parse", json={"markdown": "안건 없는 글"})
    assert r.status_code == 422
    assert "첫 줄: \"안건 없는 글\"" in r.json()["detail"]
    assert client.post("/api/build", json={"data": {"agendas": []}}).status_code == 422


def test_shared_password(monkeypatch):
    import app.main as m
    monkeypatch.setattr(m, "APP_PASSWORD", "팀비번")
    assert client.get("/").status_code == 401
    assert client.get("/api/health").status_code == 200
    ok = client.get("/", auth=("team", "팀비번"))
    assert ok.status_code == 200
    assert client.get("/", auth=("team", "wrong")).status_code == 401


def test_no_default_leader_name():
    """팀장 이름은 기본값으로 채우지 않고, 비워 두면 문서에도 예시 이름이 남지 않는다."""
    assert client.get("/api/defaults").json()["leader"] == ""
    import io
    import zipfile
    from engine.md_parser import parse_markdown
    data = parse_markdown((ROOT / "samples" / "sample_draft.md").read_text(encoding="utf-8"))
    r = client.post("/api/build", json={"data": data, "meta": {"dept": "교육과정과", "team": "전공교육팀", "leader": ""}})
    sec = zipfile.ZipFile(io.BytesIO(r.content)).read("Contents/section0.xml").decode()
    assert "<hp:t>(팀장: )</hp:t>" in sec
