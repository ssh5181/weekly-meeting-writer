"""실제로 AI와 대화해서 받은 초안 형식(내용은 가상 데이터로 바꿈)(### 제목, \\[ \\] 이스케이프, **굵게**, ·, ➡, `각주`) 회귀 테스트."""
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.hwpx_writer import build_hwpx  # noqa: E402
from engine.md_parser import parse_markdown  # noqa: E402

DRAFT = (ROOT / "tests" / "fixtures" / "real_draft_escaped.md").read_text(encoding="utf-8")


def _items(sec, kind):
    return [i for i in sec["items"] if i["type"] == kind]


def test_agenda_titles_from_h3_with_escaped_brackets():
    ags = parse_markdown(DRAFT)["agendas"]
    assert len(ags) == 2
    assert [a["category"] for a in ags] == ["육성", "육성"]
    assert all(a["owner"] == "홍길동" for a in ags)
    assert ags[0]["title"].startswith("2026학년도 AX-전환")
    assert ags[0]["title"].endswith("(예시 안건)")


def test_bold_section_labels_are_classified():
    a = parse_markdown(DRAFT)["agendas"][0]
    assert [s["kind"] for s in a["sections"]] == ["purpose", "main", "schedule"]
    assert [s["label"] for s in a["sections"]] == ["목적", "주요내용", "추진일정"]
    assert a["sections"][0]["text"].startswith("2026학년도 AI 융합")


def test_star_bold_subheadings_and_middot_bullets():
    main = parse_markdown(DRAFT)["agendas"][0]["sections"][1]
    heads = [i["text"] for i in _items(main, "heading")]
    assert heads == ["가. AI-X 결과보고서 자동 생성기(웹앱) 구축 및 운영",
                     "나. 사업 운영 개선 및 결과보고서 제출기한 연장",
                     "다. 단과대학별 예산 재배정 수정 추진"]
    bullets = [i["text"] for i in _items(main, "bullet")]
    assert bullets[0].startswith("시스템명:") and "`" not in bullets[0]
    notes = [i["text"] for i in _items(main, "note")]
    assert notes[0].startswith("* 당초 1차") and notes[-1].startswith("※ 예산 지원")
    assert "1~3차" in bullets[2]  # \\~ 이스케이프 제거


def test_schedule_star_items_are_bullets():
    sched = parse_markdown(DRAFT)["agendas"][0]["sections"][2]
    assert len(_items(sched, "bullet")) == 5 and not _items(sched, "note")


def test_arrow_kpi_and_backtick_footnote():
    a1, a2 = parse_markdown(DRAFT)["agendas"]
    assert a1["kpi"] == "[국립대학육성사업 성과지표 목표] AI-X 교과목 개발 건수 20개*/18개"
    assert a1["kpi_notes"] == ["* AI-X 교과목 개발 건수(기존 10개 + 신규 개발 6개 + 인증 4개 = 20개)"]
    assert a2["kpi"].endswith("(정성) 기초학문 학과 지정")


def test_bom_and_crlf():
    a = parse_markdown("﻿" + DRAFT.replace("\n", "\r\n"))["agendas"]
    assert len(a) == 2 and a[0]["sections"][0]["kind"] == "purpose"


def test_build_bold_total_rows_and_kpi_note():
    data = parse_markdown(DRAFT)
    sec = zipfile.ZipFile(io.BytesIO(build_hwpx(data))).read("Contents/section0.xml").decode()
    assert "**" not in sec
    assert ">합계<" in sec and ">총계<" in sec
    assert "인증 4개 = 20개" in sec
