"""명령줄 변환기: python convert.py 초안.md 결과.hwpx [--template 템플릿.hwpx]"""
import argparse
import json
from pathlib import Path

from engine.hwpx_writer import DEFAULT_TEMPLATE, build_hwpx
from engine.md_parser import parse_markdown


def main():
    ap = argparse.ArgumentParser(description="주간회의 MD 초안 → hwpx")
    ap.add_argument("md")
    ap.add_argument("out")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--dump-json", help="파싱 결과를 JSON 으로 저장")
    args = ap.parse_args()

    data = parse_markdown(Path(args.md).read_text(encoding="utf-8"))
    if args.dump_json:
        Path(args.dump_json).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out).write_bytes(build_hwpx(data, args.template))
    print(f"안건 {len(data['agendas'])}건 → {args.out}")


if __name__ == "__main__":
    main()
