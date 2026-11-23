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


def test_section_bullets_share_left_margin():
    """'목적'과 '주요내용'·'추진일정' 대항목의 ◦ 시작 위치(왼쪽 여백)가 같아야 한다."""
    import re
    import zipfile
    h = zipfile.ZipFile(ROOT / "templates" / "weekly_template.hwpx").read("Contents/header.xml").decode()

    def left(pid):
        m = re.search(rf'<hh:paraPr id="{pid}".*?</hh:paraPr>', h, re.S).group(0)
        return re.findall(r'<hc:left value="(-?\d+)"', m)

    assert left("171") == left("172") == left("174")


def test_two_level_dash_list_becomes_headings():
    from engine.md_parser import parse_markdown
    md = (
        "### ① \\[육성\\] 예시 사업(담당자: 홍길동)\n○ **목적**: 예시\n○ **주요내용**\n"
        "- **시스템명**: 「예시 생성기」\n- 접속 주소: example.app\n- **주요기능**\n"
        "  - 입장 코드 인증\n  - 6단계 표준 입력\n○ **추진일정**\n- 테스트: '26. 11. 25.\n"
    )
    secs = parse_markdown(md)["agendas"][0]["sections"]
    main = [(i["type"], i["text"]) for i in secs[1]["items"]]
    assert main[0] == ("heading", "가. **시스템명**: 「예시 생성기」")
    assert main[2] == ("heading", "다. **주요기능**")
    assert main[3] == ("bullet", "입장 코드 인증")
    assert secs[2]["items"][0]["type"] == "bullet"  # 1단 목록은 그대로
    assert all("lvl" not in i for s in secs for i in s["items"])


def test_kpi_uses_thick_arrow():
    """성과지표 줄은 '※' 대신 굵은 화살표(➡)로 시작하고, 각주 표시(*)는 따로 강조한다."""
    import io
    import re
    import zipfile
    from engine.hwpx_writer import build_hwpx
    from engine.md_parser import parse_markdown
    md = ("### ① \\[육성\\] 예시 사업(담당자: 홍길동)\n○ **목적**: 예시\n"
          "➡ **\\[국립대학육성사업 성과지표 목표\\]** 교과목 개발 건수 20개\\*/18개\n")
    sec = zipfile.ZipFile(io.BytesIO(build_hwpx(parse_markdown(md)))).read("Contents/section0.xml").decode()
    p = re.search(r"<hp:p\b[^>]*>(?:(?!</hp:p>).)*성과지표(?:(?!</hp:p>).)*</hp:p>", sec, re.S).group(0)
    assert "<hp:t> ➡<hp:fwSpace/><hp:fwSpace/></hp:t>" in p
    assert "※" not in p
    assert re.search(r"<hp:t>\*</hp:t>", p)
