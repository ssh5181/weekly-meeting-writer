"""구조화된 주간회의 데이터를 주간회의 템플릿(hwpx) 서식에 맞춰 새 hwpx로 만든다.

원칙
- 템플릿의 머리 부분(부서/팀 헤더, 공지사항, 쪽번호 등 secPr)은 그대로 둔다.
- 본문 문단은 템플릿에 정의된 문단/글자 스타일 ID를 그대로 참조한다.
- 템플릿에 없는 스타일(표 머리행 음영, 합계행, 참고/성과지표 문단)은
  styles_extra.xml 의 정의를 header.xml 끝에 새 ID로 추가해서 쓴다.
- mimetype 은 첫 항목, 무압축(ZIP_STORED)으로 저장한다.
"""
from __future__ import annotations

import io
import random
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "templates" / "weekly_template.hwpx"
EXTRA_STYLES = HERE / "styles_extra.xml"

# 템플릿(주간회의template.hwpx)의 스타일 ID
PP = {
    "title": ("170", "1"),
    "purpose": ("171", "2"),
    "main": ("172", "2"),
    "schedule": ("174", "2"),
    "other": ("172", "2"),
    "heading": ("169", "3"),   # 가. 나.
    "bullet": ("173", "3"),    # - (글머리표 자동)
    "text": ("169", "3"),
    "table_host": ("166", "0"),
}
CP = {
    "number": "42",      # ① 굵게
    "category": "188",   # [육성] 파랑 굵게
    "gap": "192",
    "title": "193",      # 제목 굵게
    "body": "41",
    "bold": "193",
}
# 한컴 전용 원문자(①=U+F02B1)
PUA_CIRCLED_BASE = 0xF02B1
TABLE_WIDTH = 46000
HEADER_ROW_H = 1470
BODY_ROW_H = 1600
TOTAL_WORDS = ("합계", "계", "총계", "소계", "합 계", "총 계")


# ---------------------------------------------------------------- header.xml
def _max_id(header: str, tag: str) -> int:
    ids = [int(x) for x in re.findall(rf'<hh:{tag} id="(\d+)"', header)]
    return max(ids) if ids else 0


def _bump_count(header: str, list_tag: str, add: int) -> str:
    def rep(m):
        return f'{m.group(1)}{int(m.group(2)) + add}"'
    return re.sub(rf'(<hh:{list_tag} itemCnt=")(\d+)"', rep, header, count=1)


def install_extra_styles(header: str) -> tuple[str, dict]:
    """styles_extra.xml 의 정의를 header 에 추가하고 {키: 새ID} 를 돌려준다."""
    src = EXTRA_STYLES.read_text(encoding="utf-8")
    blocks = re.findall(r"<!-- (\w+) -->\s*(<hh:(\w+) id=\"\d+\".*?</hh:\3>)", src, re.S)
    ids: dict[str, str] = {}
    add = {"borderFill": [], "charPr": [], "paraPr": []}
    next_id = {t: _max_id(header, t) + 1 for t in add}
    for key, xml, tag in blocks:
        variants = [(key, xml)]
        if key == "pp_cell_center":
            variants += [
                ("pp_cell_left", xml.replace('horizontal="CENTER"', 'horizontal="LEFT"')),
                ("pp_cell_right", xml.replace('horizontal="CENTER"', 'horizontal="RIGHT"')),
            ]
        for k, x in variants:
            nid = next_id[tag]
            next_id[tag] += 1
            x = re.sub(r'^(<hh:\w+ id=")\d+"', rf'\g<1>{nid}"', x)
            add[tag].append(x)
            ids[k] = str(nid)
    for tag, list_tag in (("borderFill", "borderFills"), ("charPr", "charProperties"), ("paraPr", "paraProperties")):
        if not add[tag]:
            continue
        close = f"</hh:{list_tag}>"
        pos = header.find(close)
        header = header[:pos] + "".join(add[tag]) + header[pos:]
        header = _bump_count(header, list_tag, len(add[tag]))
    return header, ids


# ---------------------------------------------------------------- 문단 생성
def _t(text: str) -> str:
    return f"<hp:t>{escape(text)}</hp:t>" if text else "<hp:t/>"


def _run(cp: str, text: str) -> str:
    return f'<hp:run charPrIDRef="{cp}">{_t(text)}</hp:run>'


def _rich_runs(text: str, cp: str, bold_cp: str) -> str:
    """**굵게** 표시를 굵은 글자 스타일로 바꾼다."""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    out = []
    for i, p in enumerate(parts):
        if p:
            out.append(_run(bold_cp if i % 2 else cp, p))
    return "".join(out) or _run(cp, "")


def _para(pp: str, style: str, runs: str) -> str:
    return (f'<hp:p id="2147483648" paraPrIDRef="{pp}" styleIDRef="{style}" '
            f'pageBreak="0" columnBreak="0" merged="0">{runs}</hp:p>')


def _title_para(agenda: dict, idx: int) -> str:
    num = agenda.get("number") or idx
    num_char = chr(PUA_CIRCLED_BASE + num - 1) if 1 <= num <= 20 else f"{num}."
    pp, st = PP["title"]
    title = agenda.get("title", "").strip()
    if agenda.get("owner"):
        title += f"(담당자: {agenda['owner']})"
    runs = _run(CP["number"], num_char + " ")
    if agenda.get("category"):
        runs += _run(CP["category"], f"[{agenda['category']}]")
        runs += f'<hp:run charPrIDRef="{CP["gap"]}"><hp:t><hp:fwSpace/></hp:t></hp:run>'
    runs += _rich_runs(title, CP["title"], CP["title"])
    return _para(pp, st, runs).replace('id="2147483648"', 'id="0"', 1)


def _col_widths(header: list[str], rows: list[list[str]], total: int) -> list[int]:
    def vis(s: str) -> int:
        return sum(2 if ord(c) > 0x2E80 else 1 for c in s)
    n = len(header)
    weights = []
    for c in range(n):
        longest = max([vis(header[c])] + [vis(r[c]) for r in rows if c < len(r)])
        weights.append(min(max(longest, 7), 40))
    s = sum(weights)
    widths = [int(total * w / s) for w in weights]
    widths[-1] += total - sum(widths)
    return widths


def _cell(text, col, row, width, height, bf, pp, cp, header=False):
    return (
        f'<hp:tc name="" header="{1 if header else 0}" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="{bf}">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" '
        'linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        + _para(pp, "0", _rich_runs(text, cp, cp))
        + '</hp:subList>'
        f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        f'<hp:cellSz width="{width}" height="{height}"/>'
        '<hp:cellMargin left="180" right="180" top="110" bottom="110"/></hp:tc>'
    )


def _table_para(item: dict, sid: dict, table_bf: str = "36") -> str:
    header, rows, align = item["header"], item["rows"], item["align"]
    n = len(header)
    widths = _col_widths(header, rows, TABLE_WIDTH)
    pp_align = {"center": sid["pp_cell_center"], "left": sid["pp_cell_left"], "right": sid["pp_cell_right"]}
    trs = []
    trs.append("<hp:tr>" + "".join(
        _cell(h, c, 0, widths[c], HEADER_ROW_H, sid["bf_head"], sid["pp_cell_center"], sid["cp_cell_bold"], header=True)
        for c, h in enumerate(header)) + "</hp:tr>")
    for r, row in enumerate(rows, 1):
        is_total = row and row[0].replace(" ", "") in [w.replace(" ", "") for w in TOTAL_WORDS]
        bf = sid["bf_total"] if is_total else table_bf
        cp = sid["cp_cell_bold"] if is_total else sid["cp_cell"]
        trs.append("<hp:tr>" + "".join(
            _cell(v, c, r, widths[c], BODY_ROW_H, bf,
                  sid["pp_cell_center"] if is_total and c == 0 else pp_align.get(align[c], sid["pp_cell_center"]),
                  cp)
            for c, v in enumerate(row)) + "</hp:tr>")
    height = HEADER_ROW_H + BODY_ROW_H * len(rows)
    tid = random.randint(1_000_000_000, 2_000_000_000)
    tbl = (
        f'<hp:tbl id="{tid}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
        f'dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="{len(rows) + 1}" colCnt="{n}" cellSpacing="0" '
        f'borderFillIDRef="{table_bf}" noAdjust="0">'
        f'<hp:sz width="{TABLE_WIDTH}" widthRelTo="ABSOLUTE" height="{height}" heightRelTo="ABSOLUTE" protect="0"/>'
        '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
        'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        '<hp:outMargin left="141" right="141" top="141" bottom="141"/>'
        '<hp:inMargin left="141" right="141" top="141" bottom="141"/>'
        + "".join(trs) + "</hp:tbl>"
    )
    pp, st = PP["table_host"]
    return _para(pp, st, f'<hp:run charPrIDRef="{CP["body"]}">{tbl}<hp:t/></hp:run>')


def _item_para(item: dict, sid: dict) -> str:
    t = item["type"]
    if t == "table":
        return _table_para(item, sid)
    text = item.get("text", "")
    if t == "heading":
        pp, st = PP["heading"]
        m = re.match(r"^(\S+\.)\s*(.*)$", text)
        if m:
            return _para(pp, st, _run(CP["body"], f"  {m.group(1)} ") + _rich_runs(m.group(2), CP["body"], CP["bold"]))
        return _para(pp, st, _rich_runs("  " + text, CP["body"], CP["bold"]))
    if t == "bullet":
        pp, st = PP["bullet"]
        return _para(pp, st, _rich_runs(text, CP["body"], CP["bold"]))
    if t == "note":
        return _para(sid["pp_note"], "0", _rich_runs(text, sid["cp_note"], sid["cp_note"]))
    pp, st = PP["text"]
    return _para(pp, st, _rich_runs(text, CP["body"], CP["bold"]))


def build_body(data: dict, sid: dict) -> tuple[str, list[str]]:
    out, plain = [], []
    for idx, a in enumerate(data.get("agendas", []), 1):
        out.append(_title_para(a, idx))
        plain.append(f"{a.get('category','')} {a.get('title','')}")
        for sec in a.get("sections", []):
            pp, st = PP.get(sec.get("kind") or "other", PP["other"])
            label = sec.get("label", "").strip()
            text = sec.get("text", "").strip()
            line = f"{label}: {text}" if text else label
            out.append(_para(pp, st, _rich_runs(line, CP["body"], CP["bold"])))
            plain.append(line)
            for it in sec.get("items", []):
                out.append(_item_para(it, sid))
                if it["type"] != "table":
                    plain.append(it.get("text", ""))
        if a.get("kpi"):
            kpi = a["kpi"].strip()
            if not kpi.startswith("※"):
                kpi = "※ " + kpi
            out.append(_para(sid["pp_note"], "0", _run(sid["cp_kpi"], kpi)))
            plain.append(kpi)
    return "".join(out), plain


# ---------------------------------------------------------------- 머리 영역
def apply_meta(prefix: str, meta: dict | None) -> str:
    if not meta:
        return prefix
    rep = {
        "dept": ("<hp:t>교육과정과</hp:t>", "<hp:t>{}</hp:t>"),
        "team": ("<hp:t> 전공교육팀</hp:t>", "<hp:t> {}</hp:t>"),
        "leader": ("<hp:t>(팀장: 서자희)</hp:t>", "<hp:t>(팀장: {})</hp:t>"),
    }
    for k, (old, new) in rep.items():
        if meta.get(k):
            prefix = prefix.replace(old, new.format(escape(meta[k])), 1)
    return prefix


# ---------------------------------------------------------------- 패키징
def build_hwpx(data: dict, template: str | Path | bytes = DEFAULT_TEMPLATE, meta: dict | None = None) -> bytes:
    if isinstance(template, (str, Path)):
        template = Path(template).read_bytes()
    zin = zipfile.ZipFile(io.BytesIO(template))
    files = {n: zin.read(n) for n in zin.namelist()}
    order = zin.namelist()

    header, sid = install_extra_styles(files["Contents/header.xml"].decode("utf-8"))
    section = files["Contents/section0.xml"].decode("utf-8")

    # 템플릿 본문의 첫 안건 제목 문단(paraPrIDRef=170) 앞까지가 머리 영역
    m = re.search(r'<hp:p [^>]*paraPrIDRef="170"', section)
    if not m:
        raise ValueError("템플릿에서 안건 제목 문단(paraPrIDRef=170)을 찾지 못했습니다.")
    prefix = apply_meta(section[: m.start()], meta)
    body, plain = build_body(data, sid)
    section = prefix + body + "</hs:sec>"

    files["Contents/header.xml"] = header.encode("utf-8")
    files["Contents/section0.xml"] = section.encode("utf-8")
    if "Preview/PrvText.txt" in files:
        files["Preview/PrvText.txt"] = "\r\n".join(plain)[:1024].encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for n in order:
            if n == "mimetype":
                continue
            z.writestr(n, files[n], compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()
