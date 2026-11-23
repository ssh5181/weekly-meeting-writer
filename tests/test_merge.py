"""팀별 hwpx 합본 기능 테스트 (가상 자료만 사용)."""
import base64
import io
import re
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from engine.hwpx_merge import merge_hwpx, para_text, split_paragraphs, team_info  # noqa: E402
from engine.hwpx_writer import build_hwpx  # noqa: E402
from engine.md_parser import parse_markdown  # noqa: E402

SAMPLE = (ROOT / "samples" / "sample_draft.md").read_text(encoding="utf-8")


def team_file(dept, team, leader):
    return build_hwpx(parse_markdown(SAMPLE), meta={"dept": dept, "team": team, "leader": leader})


def read(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    return z, z.read("Contents/header.xml").decode(), z.read("Contents/section0.xml").decode()


def shift_ids(blob, kind, attr, by):
    """같은 내용이지만 번호 체계가 다른 파일(한글에서 다시 저장한 파일 흉내)."""
    zin = zipfile.ZipFile(io.BytesIO(blob))
    files = {n: zin.read(n) for n in zin.namelist()}
    h = files["Contents/header.xml"].decode()
    h = re.sub(rf'(<hh:{kind} id=")(\d+)"', lambda m: f'{m.group(1)}{int(m.group(2)) + by}"', h)
    h = re.sub(rf'({attr}=")(\d+)"', lambda m: f'{m.group(1)}{int(m.group(2)) + by}"', h)
    s = re.sub(rf'({attr}=")(\d+)"', lambda m: f'{m.group(1)}{int(m.group(2)) + by}"', files["Contents/section0.xml"].decode())
    files["Contents/header.xml"], files["Contents/section0.xml"] = h.encode(), s.encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for n, d in files.items():
            z.writestr(n, d, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def assert_refs_valid(header, section):
    for kind, attr in [("charPr", "charPrIDRef"), ("paraPr", "paraPrIDRef"), ("borderFill", "borderFillIDRef")]:
        ids = set(re.findall(rf'<hh:{kind} id="(\d+)"', header))
        used = set(re.findall(rf'{attr}="(\d+)"', section)) | set(re.findall(rf'{attr}="(\d+)"', header))
        used.discard("4294967295")  # 한글에서 "없음"을 뜻하는 값
        assert used <= ids, (kind, sorted(used - ids)[:5])
        cnt = re.search(rf'<hh:\w+ itemCnt="(\d+)">\s*<hh:{kind} ', header)
        assert int(cnt.group(1)) == len(ids)


def test_team_info():
    info = team_info(team_file("교육과정과", "교양교육팀", "김철수"))
    assert info["dept"] == "교육과정과"
    assert info["team"] == "교양교육팀(팀장: 김철수)"
    assert info["agendas"] >= 1


def test_merge_order_cover_and_departments():
    files = [team_file("교육과정과", "전공교육팀", "홍길동"),
             team_file("교육과정과", "교양교육팀", "김철수"),
             team_file("학사지원과", "학사운영팀", "이영희")]
    out = merge_hwpx(files, {"date": "2026. 12. 2.(수) 14:00", "place": "본부 소회의실"})
    z, header, section = read(out)
    assert z.namelist()[0] == "mimetype" and z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    _pre, paras, _suf = split_paragraphs(section)
    texts = [para_text(p) for p in paras]
    joined = "\n".join(texts)
    # 표지
    assert "2026. 12. 2.(수) 14:00" in joined and "본부 소회의실" in joined
    assert section.count("<hp:secPr") == 1
    # 팀 순서와 부서 제목(같은 부서는 한 번만, 새 부서는 2번)
    order = [t for t in texts if "팀장" in t]
    assert order == ["전공교육팀(팀장: 홍길동)", "교양교육팀(팀장: 김철수)", "학사운영팀(팀장: 이영희)"]
    assert texts.count("1교육과정과") == 1 and texts.count("2학사지원과") == 1
    # 팀마다 새 쪽에서 시작
    starts = [p for p in paras if 'pageBreak="1"' in p[:300]]
    assert len(starts) == 3
    assert_refs_valid(header, section)


def test_merge_remaps_different_style_numbers():
    a = team_file("교육과정과", "전공교육팀", "홍길동")
    b = shift_ids(team_file("교육과정과", "교양교육팀", "김철수"), "charPr", "charPrIDRef", 500)
    out = merge_hwpx([a, b], {"date": "", "place": ""})
    _z, header, section = read(out)
    assert_refs_valid(header, section)
    # 같은 모양은 기존 번호를 다시 써서 header 가 불어나지 않는다
    base = read(merge_hwpx([a, a], {}))[1]
    assert header.count("<hh:charPr ") == base.count("<hh:charPr ")


def test_merge_without_cover():
    out = merge_hwpx([team_file("교육과정과", "전공교육팀", "홍길동"), team_file("교육과정과", "교양교육팀", "김철수")], None)
    _z, header, section = read(out)
    assert section.count("<hp:secPr") == 1
    assert "주간회의 자료" not in section
    assert_refs_valid(header, section)


def test_merge_api():
    client = TestClient(app)
    f1 = base64.b64encode(team_file("교육과정과", "교양교육팀", "김철수")).decode()
    f2 = base64.b64encode(team_file("교육과정과", "전공교육팀", "홍길동")).decode()
    r = client.post("/api/inspect", json={"files": [{"name": "b.hwpx", "data": f1}, {"name": "a.hwpx", "data": f2},
                                                    {"name": "x.hwpx", "data": base64.b64encode(b"nope").decode()}]})
    assert r.status_code == 200
    got = r.json()["files"]
    assert [g["ok"] for g in got] == [True, True, False]
    assert got[1]["order"] < got[0]["order"]  # 전공교육팀이 교양교육팀보다 앞
    r = client.post("/api/merge", json={"files": [{"name": "a", "data": f2}, {"name": "b", "data": f1}],
                                        "date": "2026. 12. 2.(수) 14:00", "filename": "합본"})
    assert r.status_code == 200
    assert "filename*=UTF-8''%ED%95%A9%EB%B3%B8.hwpx" in r.headers["content-disposition"]
    zipfile.ZipFile(io.BytesIO(r.content)).testzip()
    assert client.get("/merge").status_code == 200
