# daily-report-generator

오늘 한 일 리포트 자동 생성기

Git/SVN 커밋과 수동 노트를 모아 “시간 + 간략한 작업 내용”으로 정리합니다.

## 요구 사항

- Python 3.8+ 설치
- 선택: `git`, `svn` 명령이 PATH에 있어야 각각의 로그 수집 가능

## 빠른 시작

```
python report.py            # 설정 파일이 있으면 그대로 사용, 결과는 reports/YYYY-MM-DD.md
python report.py --stdout   # 콘솔로만 출력
python report.py --discover # 현재 폴더 하위에서 .git/.svn 자동 검색
```

## 설정 파일 (선택)

- 파일: `report.config.json`
- 예시:

```
{
  "git_paths": ["C:/work/repoA"],
  "svn_paths": ["C:/svn/project"],
  "notes_dir": "notes",
  "output_dir": "reports",
  "discover": false,
  "discover_roots": [],
  "include_working": true,
  "format": "html"  // md|html|csv|json
}
```

우선순위: CLI 인자 > 설정 파일 > 자동 검색

## 사용 방법

도움말 보기:

```
python report.py --help
```

예시:

```
# 오늘 날짜 기준, Git/SVN 커밋 수집
python report.py --git "C:\\work\\repoA" "D:\\src\\repoB" --svn "C:\\svn\\project"

# 비커밋 작업 수동 추가 (크래시 분석 등)
python report.py --add "09:10 크래시 덤프 분석 - 앱 2.3.1" --add "11:30 리포트 초안 작성"

# 노트 파일에서 읽기 (각 줄: HH:MM 내용)
python report.py --notes notes\\2025-09-20.txt

# 파일로 저장 (경로 미지정 시 reports/YYYY-MM-DD.<포맷>)
python report.py --git C:\\work\\repoA -o reports\\2025-09-20.md

# 특정 날짜 리포트 생성
python report.py --date 2025-09-20 --git C:\\work\\repoA

# 자동 검색으로 하위 폴더의 .git/.svn 모두 포함
python report.py --discover --roots D:\\src C:\\work

# 커밋되지 않은 ‘작업 중’ 변경 감지 끄기
python report.py --no-working
```

## 신규 기능 요약 (업데이트)

- 설정 파일 지원: `report.config.json` 에 경로/노트/포맷/출력 디렉토리 지정
- 자동 검색: `--discover`로 루트에서 `.git`/`.svn` 레포 자동 포함
- 기본 저장: `--stdout`가 아니면 `reports/YYYY-MM-DD.<포맷>`로 저장
- 작업 중 변경: 오늘 수정된 미커밋 파일을 항목으로 포함 (`--no-working`으로 끔)
- 다중 출력 포맷: `--format md|html|csv|json`

## 출력 포맷

- `md`(기본): Markdown 리스트
- `html`: 카드형 리스트(시간 · 내용 · 출처 배지), 보기 좋은 단일 HTML 파일
- `csv`: `date,time,source,summary` 헤더의 CSV. 스프레드시트/BI로 임포트 용이
- `json`: 시스템 연동이나 추가 후처리용

예시:

```
python report.py --format html        # reports/YYYY-MM-DD.html 저장
python report.py --format csv --stdout
python report.py --format json -o out\\today.json
```

## 팁

- Windows 콘솔에서 한글이 깨질 경우 PowerShell에서 `chcp 65001` 후 실행하거나 파일로 저장해 편집기로 확인하세요.
- 배치/작업 스케줄러에 등록해 매일 자동 생성하기 좋습니다.
- 커밋 메시지를 간단한 동사형으로 작성하면 리포트가 더 읽기 좋아집니다.

