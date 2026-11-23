"""주간회의 MD 초안을 안건 단위의 구조화된 데이터로 바꾸는 파서.

지원하는 형식 (섞여 있어도 됨)
1) 기호형:  제목: ① [육성] ...(담당자: 홍길동) / ○ 목적: ... / ○ 주요내용 / 가. / - / * / ※ / 표
2) 제목형:  ## 목적 / ## 주요내용 / ## 향후 추진일정 / ## 성과지표

결과 모델 (웹 편집 화면에서도 그대로 사용)
{
  "agendas": [
    {"number": 1, "category": "육성", "title": "...", "owner": "홍길동",
     "sections": [
        {"kind": "purpose",  "label": "목적", "text": "...", "items": []},
        {"kind": "main",     "label": "주요내용", "text": "", "items": [item, ...]},
        {"kind": "schedule", "label": "향후 추진일정", "text": "", "items": [...]},
     ],
     "kpi": "[국립대학육성사업 성과지표 목표] ..."}
  ]
}
item = {"type": "heading"|"bullet"|"note"|"text", "text": str}
     | {"type": "table", "header": [..], "rows": [[..], ..], "align": ["center"|"left"|"right", ..]}
"""
from __future__ import annotations

import re

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

SECTION_KEYS = [
    ("purpose", "목적", re.compile(r"^(사업\s*)?목\s*적$")),
    ("main", "주요내용", re.compile(r"^(주요\s*내용|추진\s*내용|주요\s*추진\s*내용|추진\s*현황)$")),
    ("schedule", "향후 추진일정", re.compile(r"^(향후\s*)?(추진\s*)?(일정|계획)$|^향후\s*추진\s*일정$")),
    ("kpi", "성과지표", re.compile(r"^(성과\s*지표|성과\s*지표\s*목표)")),
]

KOREAN_ORDINALS = "가나다라마바사아자차카타파하"


def _strip_md_escapes(s: str) -> str:
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|~>])", r"\1", s)


def _classify_label(label: str):
    label = label.strip().rstrip(":").strip()
    for kind, canon, rx in SECTION_KEYS:
        if rx.search(label.replace(" ", "")) or rx.search(label):
            return kind, canon
    return None, label


def parse_title(raw: str) -> dict:
    """'① [육성] 사업명(담당자: 홍길동)' 형태를 분해."""
    s = raw.strip()
    s = re.sub(r"^(제목|안건명|안건)\s*[:：]\s*", "", s)
    number = None
    if s and s[0] in CIRCLED:
        number = CIRCLED.index(s[0]) + 1
        s = s[1:].strip()
    else:
        m = re.match(r"^(\d+)[.)]\s+", s)
        if m:
            number = int(m.group(1))
            s = s[m.end():]
    category = ""
    m = re.match(r"^\[([^\]]+)\]\s*", s)
    if m:
        category = m.group(1).strip()
        s = s[m.end():]
    owner = ""
    m = re.search(r"\(\s*담당(?:자)?\s*[:：]\s*([^)]+)\)\s*$", s)
    if m:
        owner = m.group(1).strip()
        s = s[: m.start()].rstrip()
    return {"number": number, "category": category, "title": s.strip(), "owner": owner}


def _parse_table(lines: list[str]) -> dict:
    def cells(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [c.strip() for c in line.split("|")]

    header = cells(lines[0])
    align = ["center"] * len(header)
    body_start = 1
    if len(lines) > 1 and re.match(r"^\s*\|?\s*:?-{2,}", lines[1]):
        align = []
        for c in cells(lines[1]):
            if c.startswith(":") and c.endswith(":"):
                align.append("center")
            elif c.endswith(":"):
                align.append("right")
            elif c.startswith(":"):
                align.append("left")
            else:
                align.append("center")
        body_start = 2
    rows = [cells(l) for l in lines[body_start:]]
    n = len(header)
    rows = [(r + [""] * n)[:n] for r in rows]
    align = (align + ["center"] * n)[:n]
    return {"type": "table", "header": header, "rows": rows, "align": align}


def _new_agenda(title_raw: str) -> dict:
    a = parse_title(title_raw)
    a["sections"] = []
    a["kpi"] = ""
    return a


def parse_markdown(md: str) -> dict:
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = [_strip_md_escapes(l.rstrip()) for l in md.split("\n")]

    agendas: list[dict] = []
    cur: dict | None = None
    sec: dict | None = None
    pending_agenda_heading = False  # "## [안건 1]" 다음 줄에 제목이 오는 경우
    in_kpi_section = False

    def ensure_agenda():
        nonlocal cur
        if cur is None:
            cur = _new_agenda("")
            agendas.append(cur)
        return cur

    def ensure_section(kind="main", label="주요내용"):
        nonlocal sec
        ensure_agenda()
        if sec is None:
            sec = {"kind": kind, "label": label, "text": "", "items": []}
            cur["sections"].append(sec)
        return sec

    def open_section(kind, label, text=""):
        nonlocal sec, in_kpi_section
        ensure_agenda()
        in_kpi_section = False
        if kind == "kpi":
            in_kpi_section = True
            if text:
                cur["kpi"] = (cur["kpi"] + " " + text).strip()
            sec = None
            return
        sec = {"kind": kind or "other", "label": label, "text": text.strip(), "items": []}
        cur["sections"].append(sec)

    def add_item(item):
        nonlocal in_kpi_section
        if in_kpi_section and cur is not None:
            if item["type"] != "table":
                cur["kpi"] = (cur["kpi"] + " " + item["text"]).strip()
                return
        ensure_section()["items"].append(item)

    i = 0
    started = False
    while i < len(raw_lines):
        line = raw_lines[i]
        s = line.strip()
        i += 1
        if not s or re.fullmatch(r"-{3,}|\*{3,}|_{3,}", s):
            continue

        # 표
        if s.startswith("|"):
            block = [s]
            while i < len(raw_lines) and raw_lines[i].strip().startswith("|"):
                block.append(raw_lines[i].strip())
                i += 1
            if started:
                add_item(_parse_table(block))
            continue

        # 마크다운 제목
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            text = m.group(2).strip().strip("*").strip()
            if re.match(r"^\[?\s*안건\s*\d*\s*\]?$", text):
                pending_agenda_heading = True
                started = True
                continue
            kind, canon = _classify_label(text.split(":")[0] if ":" in text else text)
            if kind and started:
                rest = text.split(":", 1)[1].strip() if ":" in text else ""
                open_section(kind, canon, rest)
                continue
            if not started and not (text[:1] in CIRCLED or text.startswith("[")):
                # 문서 앞부분(지시문 등)은 무시
                continue
            # 새 안건 제목
            started = True
            cur = _new_agenda(text)
            agendas.append(cur)
            sec = None
            in_kpi_section = False
            pending_agenda_heading = False
            continue

        # 제목: ...
        if re.match(r"^(제목|안건명)\s*[:：]", s) or (pending_agenda_heading and s[:1] in CIRCLED + "["):
            started = True
            cur = _new_agenda(s)
            agendas.append(cur)
            sec = None
            in_kpi_section = False
            pending_agenda_heading = False
            continue
        if not started:
            if s[:1] in CIRCLED and "[" in s:
                started = True
                cur = _new_agenda(s)
                agendas.append(cur)
                sec = None
                continue
            continue

        # ○ 대항목
        m = re.match(r"^[○◦●•ㅇ]\s*(.*)$", s)
        if m:
            body = m.group(1).strip()
            if ":" in body or "：" in body:
                label, rest = re.split(r"[:：]", body, maxsplit=1)
            else:
                label, rest = body, ""
            kind, canon = _classify_label(label)
            if kind is None:
                canon = label.strip()
            open_section(kind, canon, rest.strip())
            continue

        # ※ 성과지표 / 참고
        m = re.match(r"^※\s*(.*)$", s)
        if m:
            body = m.group(1).strip()
            if "성과지표" in body or in_kpi_section:
                ensure_agenda()
                cur["kpi"] = (cur["kpi"] + " " + body).strip()
                sec = None if in_kpi_section else sec
                continue
            add_item({"type": "note", "text": "※ " + body})
            continue

        # 가. 나. 중항목
        m = re.match(rf"^([{KOREAN_ORDINALS}])[.)]\s*(.*)$", s)
        if m:
            add_item({"type": "heading", "text": f"{m.group(1)}. {m.group(2).strip()}"})
            continue

        # '* ' 로 시작하는 줄은 참고(주석) 문구
        m = re.match(r"^[*＊]\s+(.*)$", s)
        if m:
            add_item({"type": "note", "text": "* " + m.group(1).strip()})
            continue

        # - 세부항목
        m = re.match(r"^[-–·∙]\s*(.*)$", s)
        if m:
            add_item({"type": "bullet", "text": m.group(1).strip()})
            continue

        # 그 외 일반 문장
        add_item({"type": "text", "text": s})

    # 번호 채우기
    for idx, a in enumerate(agendas, 1):
        if not a.get("number"):
            a["number"] = idx
    return {"agendas": agendas}


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(parse_markdown(open(sys.argv[1], encoding="utf-8").read()), ensure_ascii=False, indent=2))
