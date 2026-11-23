"""주간회의 작성기 웹 서버.

실행: uvicorn app.main:app --reload
"""
from __future__ import annotations

import base64
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.hwpx_writer import DEFAULT_TEMPLATE, build_hwpx  # noqa: E402
from engine.md_parser import parse_markdown  # noqa: E402
from engine.hwpx_merge import COVER_TEMPLATE, merge_hwpx, sort_key, team_info  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
MAX_MD_BYTES = 1_000_000

app = FastAPI(title="주간회의 작성기")

# 공개 주소로 배포할 때 팀원만 쓰도록, APP_PASSWORD 환경변수가 있으면 공용 비밀번호를 묻는다.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


@app.middleware("http")
async def shared_password(request: Request, call_next):
    if not APP_PASSWORD or request.url.path == "/api/health":
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            _, _, pw = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
        except ValueError:
            pw = ""
        if secrets.compare_digest(pw.encode(), APP_PASSWORD.encode()):
            return await call_next(request)
    return Response("비밀번호가 필요해요.", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="weekly-meeting", charset="UTF-8"'})


class ParseRequest(BaseModel):
    markdown: str = Field(..., max_length=MAX_MD_BYTES)


class Meta(BaseModel):
    dept: str = ""
    team: str = ""
    leader: str = ""


class BuildRequest(BaseModel):
    data: dict
    meta: Meta = Meta()
    filename: str = "주간회의.hwpx"


@app.get("/api/health")
def health():
    """서버와 템플릿 파일이 준비됐는지 확인한다(배포 점검용)."""
    return {"ok": True, "template": DEFAULT_TEMPLATE.is_file()}


@app.get("/api/defaults")
def defaults():
    """기본 부서/팀 값. 팀장 이름은 개인정보라 기본값을 두지 않는다."""
    return {"dept": "교육과정과", "team": "전공교육팀", "leader": ""}


@app.post("/api/parse")
def parse(req: ParseRequest):
    data = parse_markdown(req.markdown)
    if not data["agendas"]:
        first = next((l.strip() for l in req.markdown.splitlines() if l.strip()), "")
        raise HTTPException(
            422,
            "안건을 찾지 못했어요. '① [구분] 사업명(담당자: 이름)' 형식의 안건 제목이 있는지 확인해 주세요."
            f" (읽은 글자 수 {len(req.markdown):,}자, 첫 줄: \"{first[:40]}\")",
        )
    return data


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip() or "주간회의"
    if not name.lower().endswith(".hwpx"):
        name += ".hwpx"
    return name[:120]


@app.post("/api/build")
def build(req: BuildRequest):
    agendas = req.data.get("agendas")
    if not isinstance(agendas, list) or not agendas:
        raise HTTPException(422, "안건이 비어 있어요.")
    try:
        blob = build_hwpx(req.data, DEFAULT_TEMPLATE, meta=req.meta.model_dump())
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, f"문서를 만드는 중 문제가 생겼어요: {e}")
    fname = _safe_filename(req.filename)
    return Response(
        blob,
        media_type="application/hwp+zip",
        headers={"Content-Disposition": f"attachment; filename=\"weekly.hwpx\"; filename*=UTF-8''{quote(fname)}"},
    )


# Vercel 함수는 요청 본문이 4.5MB 를 넘으면 받지 못한다(base64 로 늘어나는 것까지 고려).
MAX_MERGE_BYTES = 3_200_000


class UploadedFile(BaseModel):
    name: str = ""
    data: str  # base64


class InspectRequest(BaseModel):
    files: list[UploadedFile]


class MergeRequest(BaseModel):
    files: list[UploadedFile]
    cover: bool = True
    date: str = ""
    place: str = ""
    filename: str = "주간회의(교육혁신처 전체).hwpx"


def _decode_files(files: list[UploadedFile]) -> list[bytes]:
    out, total = [], 0
    for f in files:
        try:
            data = base64.b64decode(f.data, validate=True)
        except ValueError:
            raise HTTPException(422, f"{f.name}: 파일을 읽지 못했어요.")
        total += len(data)
        if total > MAX_MERGE_BYTES:
            raise HTTPException(413, "파일 크기 합계가 3MB를 넘어요. 그림이 큰 파일은 한글에서 그림 크기를 줄여 저장해 주세요.")
        out.append(data)
    return out


@app.post("/api/inspect")
def inspect(req: InspectRequest):
    """올린 팀 파일마다 부서·팀 이름과 안건 수, 기본 순서를 알려 준다."""
    result = []
    for f, data in zip(req.files, _decode_files(req.files)):
        try:
            info = team_info(data)
        except Exception:  # noqa: BLE001 - 깨진 파일은 목록에서 알려 준다
            result.append({"name": f.name, "ok": False, "error": "hwpx 파일이 아니거나 손상됐어요."})
            continue
        result.append({"name": f.name, "ok": True, "dept": info["dept"], "team": info["team"],
                       "agendas": info["agendas"], "order": sort_key(info)})
    return {"files": result}


@app.post("/api/merge")
def merge(req: MergeRequest):
    if not req.files:
        raise HTTPException(422, "합칠 파일이 없어요.")
    blobs = _decode_files(req.files)
    try:
        cover = {"date": req.date, "place": req.place} if req.cover else None
        blob = merge_hwpx(blobs, cover, COVER_TEMPLATE)
    except (KeyError, ValueError, IndexError, AttributeError) as e:
        raise HTTPException(422, f"합치는 중 문제가 생겼어요: {e}")
    fname = _safe_filename(req.filename)
    return Response(
        blob,
        media_type="application/hwp+zip",
        headers={"Content-Disposition": f"attachment; filename=\"weekly-all.hwpx\"; filename*=UTF-8''{quote(fname)}"},
    )


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/merge")
def merge_page():
    return FileResponse(STATIC / "merge.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
