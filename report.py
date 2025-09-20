#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple


def _local_today_range(date_str: Optional[str]) -> Tuple[dt.datetime, dt.datetime]:
    if date_str:
        base = dt.datetime.strptime(date_str, "%Y-%m-%d")
    else:
        now = dt.datetime.now()
        base = dt.datetime(year=now.year, month=now.month, day=now.day)
    start = base
    end = base + dt.timedelta(days=1) - dt.timedelta(seconds=1)
    return start, end


def _run(cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"


def _is_git_repo(path: str) -> bool:
    code, out, _ = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
    return code == 0 and out.strip() == "true"


def _is_svn_repo(path: str) -> bool:
    if os.path.isdir(os.path.join(path, ".svn")):
        return True
    code, _, _ = _run(["svn", "info"], cwd=path)
    return code == 0


@dataclass
class Entry:
    when: dt.datetime
    source: str
    summary: str

    def time_str(self) -> str:
        return self.when.strftime("%H:%M")


def collect_git(path: str, start: dt.datetime, end: dt.datetime) -> List[Entry]:
    if not _is_git_repo(path):
        return []
    cmd = [
        "git",
        "log",
        f"--since={start.isoformat(sep=' ')}",
        f"--until={end.isoformat(sep=' ')}",
        "--date=iso-strict",
        "--pretty=%H%x1f%ad%x1f%s",
    ]
    code, out, _ = _run(cmd, cwd=path)
    if code != 0 or not out.strip():
        return []
    repo_name = os.path.basename(os.path.abspath(path))
    entries: List[Entry] = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        _, ad, subj = parts
        try:
            when = dt.datetime.fromisoformat(ad.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except Exception:
            try:
                when = dt.datetime.strptime(ad.split(" ")[0] + " " + ad.split(" ")[1], "%Y-%m-%d %H:%M:%S")
            except Exception:
                when = start
        summary = subj.strip()
        entries.append(Entry(when=when, source=f"git:{repo_name}", summary=summary))
    return entries


def collect_svn(path: str, start: dt.datetime, end: dt.datetime) -> List[Entry]:
    if not _is_svn_repo(path):
        return []
    cmd = [
        "svn",
        "log",
        "--xml",
        f"-r{{{start.isoformat(sep=' ')}}}:{{{end.isoformat(sep=' ')}}}",
    ]
    code, out, _ = _run(cmd, cwd=path)
    if code != 0 or not out.strip():
        return []
    repo_name = os.path.basename(os.path.abspath(path))
    entries: List[Entry] = []
    date_re = re.compile(r"<date>(.*?)</date>")
    msg_re = re.compile(r"<msg>([\s\S]*?)</msg>")
    dates = date_re.findall(out)
    msgs = msg_re.findall(out)
    for ad, msg in zip(dates, msgs):
        try:
            when = dt.datetime.fromisoformat(ad.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except Exception:
            when = start
        summary = re.sub(r"\s+", " ", msg.strip())
        entries.append(Entry(when=when, source=f"svn:{repo_name}", summary=summary))
    return entries


def collect_git_working(path: str, start: dt.datetime, end: dt.datetime) -> List[Entry]:
    if not _is_git_repo(path):
        return []
    code, out, _ = _run(["git", "status", "--porcelain"], cwd=path)
    if code != 0 or not out.strip():
        return []
    repo_name = os.path.basename(os.path.abspath(path))
    entries: List[Entry] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        rel = line[3:].strip()
        abs_path = os.path.join(path, rel)
        try:
            mtime = dt.datetime.fromtimestamp(os.path.getmtime(abs_path))
        except Exception:
            mtime = start
        if not (start <= mtime <= end):
            continue
        label = _vcs_status_label(status)
        entries.append(Entry(when=mtime, source=f"git:{repo_name}", summary=f"작업 중: {rel} ({label})"))
    return entries


def collect_svn_working(path: str, start: dt.datetime, end: dt.datetime) -> List[Entry]:
    if not _is_svn_repo(path):
        return []
    code, out, _ = _run(["svn", "status"], cwd=path)
    if code != 0 or not out.strip():
        return []
    repo_name = os.path.basename(os.path.abspath(path))
    entries: List[Entry] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status = line[0]
        rel = line[8:].strip() if len(line) > 8 else line[1:].strip()
        abs_path = os.path.join(path, rel)
        try:
            mtime = dt.datetime.fromtimestamp(os.path.getmtime(abs_path))
        except Exception:
            mtime = start
        if not (start <= mtime <= end):
            continue
        label = _svn_status_label(status)
        entries.append(Entry(when=mtime, source=f"svn:{repo_name}", summary=f"작업 중: {rel} ({label})"))
    return entries


def parse_notes(path: str, date_base: dt.datetime) -> List[Entry]:
    entries: List[Entry] = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"^(\d{1,2}):(\d{2})\s+(.+)$", line)
                if m:
                    hh, mm, text = m.groups()
                    hh = int(hh)
                    mm = int(mm)
                    when = date_base.replace(hour=hh, minute=mm, second=0)
                    entries.append(Entry(when=when, source="note", summary=text.strip()))
                else:
                    when = date_base.replace(hour=9, minute=0, second=0)
                    entries.append(Entry(when=when, source="note", summary=line))
    except FileNotFoundError:
        pass
    return entries


def _vcs_status_label(xy: str) -> str:
    x, y = xy[:1], xy[1:2]
    code = y or x
    mapping = {
        "M": "수정",
        "A": "추가",
        "D": "삭제",
        "R": "이동",
        "C": "복사",
        "U": "병합충돌",
        "?": "미추적",
    }
    return mapping.get(code, code or "변경")


def _svn_status_label(ch: str) -> str:
    mapping = {
        "M": "수정",
        "A": "추가",
        "D": "삭제",
        "R": "이동",
        "C": "충돌",
        "!": "누락",
        "?": "미추적",
    }
    return mapping.get(ch, ch or "변경")


def render_markdown(entries: List[Entry], date_label: str) -> str:
    lines: List[str] = []
    lines.append(f"# {date_label} 오늘 한 일")
    if not entries:
        lines.append("- (항목 없음) 옵션 또는 설정 파일로 --add, --notes, --git/--svn/--discover를 사용하세요.")
    else:
        for e in entries:
            lines.append(f"- {e.time_str()} · {e.summary} ({e.source})")
    return "\n".join(lines) + "\n"


def render_html(entries: List[Entry], date_label: str, title: Optional[str] = None) -> str:
    title = title or f"{date_label} 오늘 한 일"
    style = """
    body{font-family: system-ui,-apple-system,Segoe UI,Roboto,Apple SD Gothic Neo,Noto Sans KR,Malgun Gothic,sans-serif; margin:24px; background:#f7f8fa; color:#1f2937}
    .wrap{max-width:860px; margin:0 auto}
    h1{font-size:22px; margin:0 0 16px}
    .item{display:flex; align-items:center; gap:10px; background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:10px 12px; margin:8px 0; box-shadow:0 1px 2px rgba(0,0,0,.04)}
    .time{font-weight:600; color:#2563eb; min-width:52px}
    .summary{flex:1}
    .badge{font-size:12px; padding:2px 8px; border-radius:999px; background:#eef2ff; color:#3730a3; border:1px solid #c7d2fe}
    .badge.git{background:#ecfdf5; color:#065f46; border-color:#a7f3d0}
    .badge.svn{background:#fff7ed; color:#9a3412; border-color:#fed7aa}
    .badge.note,.badge.manual{background:#f1f5f9; color:#0f172a; border-color:#e2e8f0}
    footer{margin-top:16px; font-size:12px; color:#6b7280}
    """
    rows = []
    if not entries:
        rows.append('<div class="item"><div class="summary">(항목 없음)</div></div>')
    else:
        for e in entries:
            src_kind = e.source.split(":", 1)[0]
            badge_class = f"badge {src_kind}"
            badge = f'<span class="{badge_class}">{e.source}</span>'
            rows.append(f'<div class="item"><div class="time">{e.time_str()}</div><div class="summary">{_html_escape(e.summary)}</div><div>{badge}</div></div>')
    html = f"""<!doctype html>
<html lang=ko>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{_html_escape(title)}</title>
<style>{style}</style>
<body><div class=wrap>
<h1>{_html_escape(title)}</h1>
{''.join(rows)}
<footer>생성일: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}</footer>
</div></body>
</html>"""
    return html


def render_csv(entries: List[Entry], date_label: str) -> str:
    lines = ["date,time,source,summary"]
    for e in entries:
        def esc(s: str) -> str:
            return '"' + s.replace('"', '""') + '"'
        lines.append(
            ",".join([date_label, e.time_str(), esc(e.source), esc(e.summary)])
        )
    return "\n".join(lines) + "\n"


def render_json(entries: List[Entry], date_label: str) -> str:
    payload = [
        {"date": date_label, "time": e.time_str(), "source": e.source, "summary": e.summary}
        for e in entries
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _dedup_paths(paths: List[str]) -> List[str]:
    seen = set()
    result = []
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            result.append(ap)
    result.sort()
    filtered: List[str] = []
    for p in result:
        if not any(p != q and p.startswith(q + os.sep) for q in result):
            filtered.append(p)
    return filtered


def _discover_repos(roots: List[str]) -> Tuple[List[str], List[str]]:
    git_found: List[str] = []
    svn_found: List[str] = []
    for root in roots:
        root = os.path.abspath(root)
        for dirpath, dirnames, filenames in os.walk(root):
            if ".git" in dirnames and os.path.isdir(os.path.join(dirpath, ".git")):
                git_found.append(dirpath)
                dirnames[:] = [d for d in dirnames if d not in {".git"}]
                continue
            if ".svn" in dirnames and os.path.isdir(os.path.join(dirpath, ".svn")):
                svn_found.append(dirpath)
                dirnames[:] = [d for d in dirnames if d != ".svn"]
    return _dedup_paths(git_found), _dedup_paths(svn_found)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="오늘 한 일 리포트 자동 생성기 (Git/SVN + 노트)")
    p.add_argument("--date", help="리포트 날짜 (YYYY-MM-DD). 기본: 오늘")
    p.add_argument("--git", nargs="*", default=[], help="Git 저장소 경로들")
    p.add_argument("--svn", nargs="*", default=[], help="SVN 저장소 경로들")
    p.add_argument("--notes", help="수동 노트 파일 경로 (각 줄: 'HH:MM 내용')")
    p.add_argument("--add", action="append", default=[], help="수동 항목 추가. 예: --add '09:10 크래시 분석 - 2.3.1'")
    p.add_argument("--output", "-o", help="결과 저장 경로 (예: reports/2025-09-20.md)")
    p.add_argument("--no-vcs", action="store_true", help="Git/SVN 수집 건너뛰기")
    p.add_argument("--config", help="설정 파일 경로 (기본: report.config.json)")
    p.add_argument("--discover", action="store_true", help="루트에서 Git/SVN 저장소 자동 검색")
    p.add_argument("--roots", nargs="*", default=[], help="--discover 검색 루트 경로들 (미지정 시 CWD 또는 설정)")
    p.add_argument("--stdout", action="store_true", help="항상 표준출력으로만 출력 (파일 저장 안 함)")
    p.add_argument("--no-working", action="store_true", help="커밋되지 않은 작업 중 변경 감지 끄기")
    p.add_argument("--format", choices=["md", "html", "csv", "json"], help="출력 포맷 (기본: md 또는 설정의 format)")
    args = p.parse_args(argv)

    cfg_path = args.config or os.path.join(os.getcwd(), "report.config.json")
    config = {}
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
        except Exception:
            config = {}

    start, end = _local_today_range(args.date)
    date_label = start.strftime("%Y-%m-%d")

    git_paths: List[str] = list(args.git) or list(config.get("git_paths", []))
    svn_paths: List[str] = list(args.svn) or list(config.get("svn_paths", []))

    discover_flag = args.discover or bool(config.get("discover", False))
    roots = args.roots or list(config.get("discover_roots", []))
    if discover_flag:
        if not roots:
            roots = [os.getcwd()]
        found_git, found_svn = _discover_repos(roots)
        git_paths = _dedup_paths(git_paths + found_git)
        svn_paths = _dedup_paths(svn_paths + found_svn)

    notes_path = args.notes or config.get("notes_file")
    if not notes_path and config.get("notes_dir"):
        notes_dir = config.get("notes_dir")
        candidate = os.path.join(notes_dir, f"{date_label}.txt")
        if os.path.isfile(candidate):
            notes_path = candidate

    include_working = (not args.no_working) if (args.no_working is not None) else bool(config.get("include_working", True))

    all_entries: List[Entry] = []
    date_base = start

    if notes_path:
        all_entries.extend(parse_notes(notes_path, date_base))

    for add_item in args.add:
        m = re.match(r"^(\d{1,2}):(\d{2})\s+(.+)$", add_item.strip())
        if m:
            hh, mm, text = m.groups()
            when = date_base.replace(hour=int(hh), minute=int(mm), second=0)
            all_entries.append(Entry(when=when, source="manual", summary=text.strip()))
        else:
            when = date_base.replace(hour=9, minute=0, second=0)
            all_entries.append(Entry(when=when, source="manual", summary=add_item.strip()))

    if not args.no_vcs:
        for repo in git_paths:
            if os.path.isdir(repo):
                all_entries.extend(collect_git(repo, start, end))
                if include_working:
                    all_entries.extend(collect_git_working(repo, start, end))
        for repo in svn_paths:
            if os.path.isdir(repo):
                all_entries.extend(collect_svn(repo, start, end))
                if include_working:
                    all_entries.extend(collect_svn_working(repo, start, end))

    all_entries.sort(key=lambda e: e.when)

    fmt = (args.format or config.get("format", "md")).lower()
    if fmt == "html":
        output = render_html(all_entries, date_label)
    elif fmt == "csv":
        output = render_csv(all_entries, date_label)
    elif fmt == "json":
        output = render_json(all_entries, date_label)
    else:
        fmt = "md"
        output = render_markdown(all_entries, date_label)

    if args.stdout:
        sys.stdout.write(output)
    else:
        out_path = args.output
        if not out_path:
            out_dir = config.get("output_dir", os.path.join(os.getcwd(), "reports"))
            os.makedirs(out_dir, exist_ok=True)
            ext = ".html" if fmt == "html" else ".csv" if fmt == "csv" else ".json" if fmt == "json" else ".md"
            out_path = os.path.join(out_dir, f"{date_label}{ext}")
        else:
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"리포트를 저장했습니다: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

