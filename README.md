# 주간회의 작성기

AI와 대화해서 만든 주간회의 초안(Markdown)을 올리면 `주간회의template.hwpx` 서식에 맞춰 한글(hwpx) 파일로 만들어 주는 웹앱입니다.
브라우저에서 미리보기로 내용을 고친 뒤 hwpx로 내려받을 수 있습니다.

## 사용 방법

1. MD 파일을 끌어다 놓거나 내용을 붙여넣으면 주간회의 서식 모양으로 미리보기가 나옵니다.
2. 미리보기에서 글자를 바로 고칩니다. `Ctrl+B` 는 굵게, 줄마다 이동·삭제·추가, 표 행/열 추가가 됩니다.
3. 왼쪽에서 부서명·팀명·팀장을 바꾸면 문서 머리와 파일 이름에 반영됩니다.
4. `hwpx 다운로드`를 누르면 템플릿 서식으로 만든 파일을 받습니다.

## 초안(MD) 작성 규칙

| MD | hwpx |
|---|---|
| `제목: ① [육성] 사업명(담당자: 홍길동)` 또는 `# ① [육성] ...` | 안건 제목 (원문자·파란 [구분]·굵은 제목) |
| `○ 목적: ...` 또는 `## 목적` | ◦ 목적 |
| `○ 주요내용` 또는 `## 주요내용` | ◦ 주요내용 |
| `○ 향후 추진일정` 또는 `## 향후 추진일정` | ◦ 향후 추진일정 |
| `가. ...` | 가. 중항목 |
| `- ...` | 세부항목 (글머리표 자동) |
| `* ...` | 참고 문구 (작은 글씨) |
| `※ [... 성과지표 ...]` 또는 `## 성과지표` | 성과지표 (빨간 글씨) |
| 마크다운 표 | 한글 표 (머리행 음영, `합계` 행 회색·굵게, 정렬은 `:---:` 표기를 따름) |
| `**굵게**` | 굵은 글씨 |

예시는 [`samples/sample_draft.md`](samples/sample_draft.md) (가상 데이터)를 보세요.

## 내 컴퓨터에서 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000
# 브라우저에서 http://localhost:8000
```

명령줄 변환만 할 때: `python convert.py 초안.md 결과.hwpx`

## 팀원용 배포 (Render 무료)

1. [Render](https://render.com) 에 GitHub 계정으로 로그인합니다.
2. **New → Blueprint** 를 누르고 이 저장소를 고르면 `render.yaml` 설정대로 웹 서비스가 만들어집니다.
3. `APP_PASSWORD` 값을 물으면 팀 공용 비밀번호를 넣습니다. 접속할 때 브라우저가 비밀번호를 묻고, 사용자 이름은 아무거나 넣으면 됩니다.
4. 배포가 끝나면 `https://weekly-meeting-writer-xxxx.onrender.com` 같은 주소가 나오고, 이 주소를 팀원에게 공유하면 됩니다.

무료 요금제는 15분 동안 접속이 없으면 잠들어서, 다음 첫 접속은 30초~1분 정도 걸립니다.
올린 초안과 만든 파일은 서버에 저장하지 않습니다.

## 구조

- `engine/md_parser.py`: MD → 안건 구조(JSON)
- `engine/hwpx_writer.py`: 템플릿 머리 영역(부서·팀·공지사항·쪽번호)을 유지하고 본문을 템플릿 스타일로 생성
- `engine/styles_extra.xml`: 템플릿에 없는 표 머리행·합계행·참고·성과지표 스타일
- `app/main.py`: 웹 서버 (`POST /api/parse`, `POST /api/build`)
- `app/static/`: 업로드·미리보기·편집 화면
- `templates/weekly_template.hwpx`: 주간회의 서식

## 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```
