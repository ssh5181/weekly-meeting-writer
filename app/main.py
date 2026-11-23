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
    """템플릿에 들어 있는 기본 부서/팀/팀장 값."""
    return {"dept": "교육과정과", "team": "전공교육팀", "leader": "서자희"}


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


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
