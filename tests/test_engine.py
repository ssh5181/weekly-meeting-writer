import io
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.hwpx_writer import build_hwpx  # noqa: E402
from engine.md_parser import parse_markdown  # noqa: E402

SAMPLE = (ROOT / "samples" / "sample_draft.md").read_text(encoding="utf-8")


def test_parse_sample():
    d = parse_markdown(SAMPLE)
    assert len(d["agendas"]) == 3
    a = d["agendas"][0]
    assert a["category"] == "육성" and a["owner"] == "홍길동"
    assert [s["kind"] for s in a["sections"]] == ["purpose", "main", "schedule"]
    tables = [i for i in a["sections"][1]["items"] if i["type"] == "table"]
    assert len(tables) == 1 and tables[0]["rows"][-1][0] == "합계"
    assert "성과지표" in d["agendas"][1]["kpi"]


def test_heading_style_markdown():
    md = """# ① [육성] 테스트 사업(담당자: 홍길동)
## 목적
테스트 목적입니다
## 주요내용
- 항목 하나
## 향후 추진일정
- 12월 완료
## 성과지표
지표 3건
"""
    a = parse_markdown(md)["agendas"][0]
    assert a["title"] == "테스트 사업" and a["owner"] == "홍길동"
    assert a["sections"][0]["kind"] == "purpose" and "목적" in a["sections"][0]["label"]
    assert a["sections"][0]["items"][0]["text"] == "테스트 목적입니다"
    assert a["kpi"] == "지표 3건"


def test_build_package():
    data = build_hwpx(parse_markdown(SAMPLE))
    z = zipfile.ZipFile(io.BytesIO(data))
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    for n in ("Contents/header.xml", "Contents/section0.xml"):
        etree.fromstring(z.read(n))
    sec = z.read("Contents/section0.xml").decode()
    assert sec.count("<hp:tbl") >= 3 + 2  # 머리 표 3개 + 본문 표 2개
    assert "교육과정과" in sec
