"""팀별 주간회의 hwpx 여러 개를 표지와 함께 하나의 합본 hwpx 로 합친다.

HWPX 는 문단이 글자 모양(charPr)·문단 모양(paraPr)·테두리(borderFill) 등을 header.xml 의
번호로 참조한다. 파일마다 번호 체계가 다르므로, 각 팀 파일의 본문을 붙일 때
  1) 본문이 쓰는 스타일만 골라 합본 header 로 가져오고(같은 내용이면 기존 번호 재사용)
  2) 본문의 참조 번호를 새 번호로 바꾸고
  3) 그림(BinData)도 새 이름으로 복사한다.
쪽 설정(secPr)은 표지(첫 문단)의 것만 남긴다.

합본 구성(교육혁신처 전체 합본 서식 기준)
  표지 → [부서 제목(1 교육과정과)] → 팀 제목(전공교육팀(팀장: …)) → 공지사항 → 안건 …
  - 팀마다 새 쪽에서 시작
  - 같은 부서의 팀이 이어지면 부서 제목은 처음 한 번만
  - 안건 번호(①②…)는 팀마다 새로 시작(각 팀 파일 그대로)
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVER_TEMPLATE = ROOT / "templates" / "cover.hwpx"

# header.xml refList 안의 순서
LIST_ORDER = [
    ("fontfaces", None),
    ("borderFills", "borderFill"),
    ("charProperties", "charPr"),
    ("tabProperties", "tabPr"),
    ("numberings", "numbering"),
    ("bullets", "bullet"),
    ("paraProperties", "paraPr"),
    ("styles", "style"),
    ("memoProperties", "memoPr"),
]
KIND_LIST = {item: lst for lst, item in LIST_ORDER if item}
FONT_LANGS = ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]

COVER_DATE_DEFAULT = "2026. 11. 18.(수) 14:00"
COVER_PLACE_DEFAULT = "교육혁신처 회의실(402호)"


# ---------------------------------------------------------------- 공통 도구
def _item_rx(tag: str) -> re.Pattern:
    return re.compile(rf"<hh:{tag}\b[^>]*?(?:/>|>.*?</hh:{tag}>)", re.S)


def _id_of(xml: str) -> str:
    return re.search(r'\bid="([^"]*)"', xml).group(1)


def _strip_id(xml: str) -> str:
    return re.sub(r'\bid="[^"]*"', 'id=""', xml, count=1)


def split_paragraphs(section: str) -> tuple[str, list[str], str]:
    """section XML 을 (머리, 최상위 문단 목록, 꼬리) 로 나눈다."""
    start = section.index(">", section.index("<hs:sec")) + 1
    paras, depth, cur, last_end = [], 0, None, start
    for m in re.finditer(r"<hp:p\b|</hp:p>", section[start:]):
        pos = m.start() + start
        if m.group(0) == "<hp:p":
            if depth == 0:
                cur = pos
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                last_end = pos + len("</hp:p>")
                paras.append(section[cur:last_end])
    first = section.index("<hp:p", start) if paras else start
    return section[:first], paras, section[last_end:]


def para_text(p: str) -> str:
    return "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", p)).strip()


def _strip_secpr(p: str) -> str:
    p = re.sub(r"<hp:secPr\b.*?</hp:secPr>", "", p, flags=re.S)
    p = re.sub(r"<hp:ctrl><hp:colPr\b[^>]*?(?:/>|>.*?</hp:colPr>)</hp:ctrl>", "", p, flags=re.S)
    # 쪽 번호 감추기 같은 쪽 단위 설정은 표지에만 의미가 있다
    p = re.sub(r"<hp:ctrl><hp:pageHiding\b[^>]*/></hp:ctrl>", "", p)
    return p


def _is_empty_para(p: str) -> bool:
    return not para_text(p) and not re.search(r"<hp:(tbl|pic|rect|ellipse|line|container|ole|equation)\b", p)


class Doc:
    """읽어 들인 hwpx 한 개."""

    def __init__(self, data: bytes):
        self.zip = zipfile.ZipFile(io.BytesIO(data))
        self.names = self.zip.namelist()
        self.header = self.zip.read("Contents/header.xml").decode("utf-8")
        self.hpf = self.zip.read("Contents/content.hpf").decode("utf-8")
        secs = sorted(
            (n for n in self.names if re.fullmatch(r"Contents/section\d+\.xml", n)),
            key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group()),
        )
        self.sections = [self.zip.read(n).decode("utf-8") for n in secs]
        self.items: dict[str, dict[str, str]] = {}
        for _lst, tag in LIST_ORDER:
            if tag:
                self.items[tag] = {_id_of(x): x for x in _item_rx(tag).findall(self.header)}
        self.fonts: dict[str, dict[str, str]] = {}
        for m in re.finditer(r'<hh:fontface lang="(\w+)"[^>]*>(.*?)</hh:fontface>', self.header, re.S):
            self.fonts[m.group(1).lower()] = {_id_of(f): f for f in _item_rx("font").findall(m.group(2))}
        self.bin_items = {
            m.group(1): m.group(0)
            for m in re.finditer(r'<opf:item id="([^"]+)" href="BinData/[^"]+"[^>]*/>', self.hpf)
        }

    def paragraphs(self) -> list[str]:
        out = []
        for s in self.sections:
            out += split_paragraphs(s)[1]
        return out

    def bin_data(self, item_id: str) -> tuple[str, bytes, str]:
        x = self.bin_items[item_id]
        href = re.search(r'href="([^"]+)"', x).group(1)
        mt = re.search(r'media-type="([^"]+)"', x).group(1)
        return href, self.zip.read(href), mt


# ---------------------------------------------------------------- 합본 만들기
class Merger:
    def __init__(self, base: bytes):
        self.base = Doc(base)
        self.header = self.base.header
        self.hpf = self.base.hpf
        self.files = {n: self.base.zip.read(n) for n in self.base.names}
        self.prefix, self.paras, self.suffix = split_paragraphs(self.base.sections[0])
        # 내용이 같은 스타일은 같은 번호를 쓰도록 (번호를 뺀 XML → 번호)
        self.known: dict[str, dict[str, str]] = {
            tag: {_strip_id(x): i for i, x in items.items()} for tag, items in self.base.items.items()
        }
        self.next_id = {
            tag: max([int(i) for i in items] + [-1]) + 1 for tag, items in self.base.items.items()
        }
        self.added: dict[str, list[str]] = {tag: [] for tag in self.base.items}
        self.font_by_face = {
            lang: {re.search(r'face="([^"]*)"', f).group(1): i for i, f in fonts.items()}
            for lang, fonts in self.base.fonts.items()
        }
        self.font_next = {lang: max([int(i) for i in f] + [-1]) + 1 for lang, f in self.base.fonts.items()}
        self.font_added: dict[str, list[str]] = {lang: [] for lang in self.base.fonts}
        self.bin_by_hash = {}
        for iid in self.base.bin_items:
            _h, data, _m = self.base.bin_data(iid)
            self.bin_by_hash[hashlib.sha1(data).hexdigest()] = iid
        nums = [int(m) for m in re.findall(r'<opf:item id="image(\d+)"', self.hpf)]
        self.bin_next = max(nums + [0]) + 1
        self.obj_id = 1_700_000_000

    # --- 스타일 가져오기 --------------------------------------------------
    def _font(self, src: Doc, lang: str, fid: str) -> str:
        f = src.fonts.get(lang, {}).get(fid)
        if f is None or lang not in self.font_by_face:
            return fid
        face = re.search(r'face="([^"]*)"', f).group(1)
        if face in self.font_by_face[lang]:
            return self.font_by_face[lang][face]
        new = str(self.font_next[lang])
        self.font_next[lang] += 1
        self.font_by_face[lang][face] = new
        self.font_added[lang].append(re.sub(r'\bid="[^"]*"', f'id="{new}"', f, count=1))
        return new

    def _bin(self, src: Doc, iid: str) -> str:
        if iid not in src.bin_items:
            return iid
        href, data, mt = src.bin_data(iid)
        h = hashlib.sha1(data).hexdigest()
        if h in self.bin_by_hash:
            return self.bin_by_hash[h]
        new = f"image{self.bin_next}"
        self.bin_next += 1
        ext = href.rsplit(".", 1)[-1]
        path = f"BinData/{new}.{ext}"
        self.files[path] = data
        item = f'<opf:item id="{new}" href="{path}" media-type="{mt}" isEmbeded="1"/>'
        self.hpf = self.hpf.replace("</opf:manifest>", item + "</opf:manifest>", 1)
        self.bin_by_hash[h] = new
        return new

    def _import(self, src: Doc, tag: str, sid: str, cache: dict) -> str:
        key = (tag, sid)
        if key in cache:
            return cache[key]
        xml = src.items.get(tag, {}).get(sid)
        if xml is None:
            cache[key] = sid
            return sid
        xml = self._remap_refs(src, xml, cache, inside_header=True)
        k = _strip_id(xml)
        if k in self.known[tag]:
            new = self.known[tag][k]
        else:
            new = str(self.next_id[tag])
            self.next_id[tag] += 1
            self.known[tag][k] = new
            self.added[tag].append(re.sub(r'\bid="[^"]*"', f'id="{new}"', xml, count=1))
        cache[key] = new
        return new

    def _remap_refs(self, src: Doc, xml: str, cache: dict, inside_header=False) -> str:
        imp = lambda tag: (lambda m: f'{m.group(1)}="{self._import(src, tag, m.group(2), cache)}"')  # noqa: E731
        xml = re.sub(r'\b(borderFillIDRef)="(\d+)"', imp("borderFill"), xml)
        xml = re.sub(r'\b(charPrIDRef)="(\d+)"', imp("charPr"), xml)
        xml = re.sub(r'\b(paraPrIDRef)="(\d+)"', imp("paraPr"), xml)
        xml = re.sub(r'\b(tabPrIDRef)="(\d+)"', imp("tabPr"), xml)
        xml = re.sub(
            r'(<hh:heading type="(BULLET|NUMBER|OUTLINE)" idRef=")(\d+)"',
            lambda m: m.group(1)
            + (self._import(src, "bullet" if m.group(2) == "BULLET" else "numbering", m.group(3), cache)
               if m.group(3) != "0" else "0") + '"',
            xml,
        )
        xml = re.sub(
            r"<hh:fontRef ([^>]*)/>",
            lambda m: "<hh:fontRef "
            + re.sub(r'(\w+)="(\d+)"', lambda a: f'{a.group(1)}="{self._font(src, a.group(1), a.group(2))}"', m.group(1))
            + "/>",
            xml,
        )
        xml = re.sub(r'\b(binaryItemIDRef)="([^"]+)"', lambda m: f'{m.group(1)}="{self._bin(src, m.group(2))}"', xml)
        if not inside_header:
            xml = re.sub(r'\bstyleIDRef="\d+"', 'styleIDRef="0"', xml)
            xml = re.sub(r'(<hp:(?:tbl|pic|rect|ellipse|line|container|ole|equation|arc|polygon|curve|connectLine|textart)\b[^>]*?\bid=")\d+"',
                         self._new_obj_id, xml)
        return xml

    def _new_obj_id(self, m) -> str:
        self.obj_id += 1
        return f'{m.group(1)}{self.obj_id}"'

    def import_paragraphs(self, src: Doc, paras: list[str]) -> list[str]:
        cache: dict = {}
        return [self._remap_refs(src, p, cache) for p in paras]

    # --- 저장 -------------------------------------------------------------
    def _write_header(self) -> str:
        h = self.header
        for lst, tag in LIST_ORDER:
            if not tag or not self.added.get(tag):
                continue
            add = "".join(self.added[tag])
            n = len(self.added[tag])
            m = re.search(rf"<hh:{lst}\b[^>]*>", h)
            if m:
                h = h.replace(f"</hh:{lst}>", add + f"</hh:{lst}>", 1)
                h = re.sub(rf'(<hh:{lst} itemCnt=")(\d+)"', lambda x: f'{x.group(1)}{int(x.group(2)) + n}"', h, count=1)
            else:
                block = f'<hh:{lst} itemCnt="{n}">{add}</hh:{lst}>'
                later = [l2 for l2, _t in LIST_ORDER[LIST_ORDER.index((lst, tag)) + 1:]]
                pos = None
                for l2 in later:
                    mm = re.search(rf"<hh:{l2}\b", h)
                    if mm:
                        pos = mm.start()
                        break
                if pos is None:
                    pos = h.index("</hh:refList>")
                h = h[:pos] + block + h[pos:]
        for lang, fonts in self.font_added.items():
            if not fonts:
                continue
            m = re.search(rf'<hh:fontface lang="{lang.upper()}" fontCnt="(\d+)">(.*?)</hh:fontface>', h, re.S)
            new = f'<hh:fontface lang="{lang.upper()}" fontCnt="{int(m.group(1)) + len(fonts)}">{m.group(2)}{"".join(fonts)}</hh:fontface>'
            h = h[: m.start()] + new + h[m.end():]
        return h

    def to_bytes(self) -> bytes:
        files = dict(self.files)
        files["Contents/header.xml"] = self._write_header().encode("utf-8")
        files["Contents/content.hpf"] = self.hpf.encode("utf-8")
        files["Contents/section0.xml"] = (self.prefix + "".join(self.paras) + self.suffix).encode("utf-8")
        files.pop("Preview/PrvImage.png", None)
        files["Preview/PrvText.txt"] = "\n".join(para_text(p) for p in self.paras[:60]).encode("utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
            for n, data in files.items():
                if n.startswith("Preview/PrvImage"):
                    continue
                z.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
        return buf.getvalue()


# ---------------------------------------------------------------- 팀 파일 분석
# 교육혁신처 전체 합본의 팀 순서. 목록에 없는 팀은 올린 순서대로 뒤에 붙는다.
TEAM_ORDER = ["전공교육팀", "교양교육팀", "교수학습팀", "IC-PBL센터", "공동교육센터"]


def sort_key(info: dict) -> int:
    name = (info.get("team") or "").replace(" ", "")
    for i, t in enumerate(TEAM_ORDER):
        if name.startswith(t) or t in name:
            return i
    return len(TEAM_ORDER)


DEPT_RX = re.compile(r"^(\d+)\s*(\S.*)$")


def team_info(data: bytes) -> dict:
    """팀 파일 첫머리에서 부서(1 교육과정과)와 팀(전공교육팀(팀장: …)) 제목을 찾는다."""
    doc = Doc(data)
    paras = doc.paragraphs()
    dept_idx = team_idx = None
    dept = team = ""
    for i, p in enumerate(paras[:12]):
        if "<hp:tbl" not in p:
            continue
        t = para_text(p)
        if dept_idx is None and team_idx is None:
            m = DEPT_RX.match(t)
            if m and len(t) < 30 and "팀장" not in t:
                dept_idx, dept = i, m.group(2).strip()
                continue
        if team_idx is None and t and len(t) < 60 and "공지" not in t:
            team_idx, team = i, t
            break
    agendas = sum(1 for p in paras if para_text(p)[:1] and 0xF02B1 <= ord(para_text(p)[0]) <= 0xF02D0)
    return {"dept": dept, "team": team, "dept_idx": dept_idx, "team_idx": team_idx, "agendas": agendas}


def _set_dept_number(p: str, n: int) -> str:
    return re.sub(r"<hp:t>\s*\d+\s*</hp:t>", f"<hp:t>{n}</hp:t>", p, count=1)


def merge_hwpx(team_files: list[bytes], cover: dict | None = None,
               cover_template: str | Path | bytes = COVER_TEMPLATE) -> bytes:
    """team_files 순서대로 합친 합본 hwpx 를 돌려준다.

    cover: {"date": "...", "place": "..."} (None 이면 표지 없이 첫 팀부터)
    """
    if not team_files:
        raise ValueError("합칠 파일이 없어요.")
    if cover is not None:
        base = cover_template if isinstance(cover_template, bytes) else Path(cover_template).read_bytes()
        mg = Merger(base)
        date = (cover.get("date") or "").strip() or COVER_DATE_DEFAULT
        place = (cover.get("place") or "").strip() or COVER_PLACE_DEFAULT
        mg.paras = [p.replace(COVER_DATE_DEFAULT, _xml_text(date)).replace(COVER_PLACE_DEFAULT, _xml_text(place))
                    for p in mg.paras]
        start = 0
    else:
        # 표지가 없으면 첫 팀 파일을 바탕으로(쪽 설정 포함) 삼는다
        mg = Merger(team_files[0])
        start = 1
    prev_dept = None
    dept_no = 0
    infos = [team_info(f) for f in team_files]
    for k, (data, info) in enumerate(zip(team_files, infos)):
        if k < start:
            prev_dept = info["dept"] or prev_dept
            if info["dept"]:
                dept_no = 1
                if info["dept_idx"] is not None:
                    mg.paras[info["dept_idx"]] = _set_dept_number(mg.paras[info["dept_idx"]], dept_no)
            continue
        doc = Doc(data)
        paras = [_strip_secpr(p) for p in doc.paragraphs()]
        same_dept = info["dept"] and info["dept"] == prev_dept
        if info["dept_idx"] is not None and same_dept and info["team_idx"] is not None:
            paras = paras[info["team_idx"]:]
        elif info["dept_idx"] is not None:
            dept_no += 1
            paras[info["dept_idx"]] = _set_dept_number(paras[info["dept_idx"]], dept_no)
            paras = paras[info["dept_idx"]:]
        while paras and _is_empty_para(paras[0]):
            paras.pop(0)
        if not paras:
            continue
        if info["dept"]:
            prev_dept = info["dept"]
        paras = mg.import_paragraphs(doc, paras)
        paras[0] = re.sub(r'(<hp:p\b[^>]*?)\bpageBreak="0"', r'\1pageBreak="1"', paras[0], count=1)
        mg.paras += paras
    return mg.to_bytes()


def _xml_text(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
