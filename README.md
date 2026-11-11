# Garmin Connect 수집기 + 개인용 MCP 서버

Garmin Connect의 러닝, 사이클, 수영, 멀티스포츠 활동을 PostgreSQL에 저장하고 ChatGPT에서 질의할 수 있도록 MCP로 제공합니다. 활동 요약, 랩, 심박·속도 등 시계열을 수집합니다. Garmin에는 조회 요청만 보내며 운동 기록을 수정하지 않습니다.

## 동작 방식

```text
ChatGPT ─ Secure MCP Tunnel ─ Garmin 컨테이너 ─ PostgreSQL
                              ├─ MCP 서버
                              └─ 수집 API ─ Garmin Connect
```

MCP는 기본적으로 저장된 데이터를 읽습니다. `get_activities_by_date`는 요청한 날짜의 기록이 부족할 때만 내부 수집 API에 요청합니다. 터널, MCP 서버, 수집 API는 하나의 컨테이너에서 각각 별도 프로세스로 실행합니다. MCP의 DB 연결은 읽기 전용 계정을 사용하고 수집 API는 컨테이너 내부의 `127.0.0.1`에서만 수신합니다. 한 컨테이너에 두 DB 계정과 Garmin 인증 정보가 함께 있으므로, 컨테이너 단위의 권한 분리는 없습니다.

지원 종목의 Garmin 하위 유형(실내 사이클, 오픈워터 수영 등)은 종목 계층에 따라 분류합니다. Garmin에서 제공하지 않는 랩이나 시계열 값은 비워 둡니다. 러닝 페이스는 초/km, 수영 페이스는 초/100m, 속도는 m/s, 거리는 m로 저장합니다.

## 준비물

- Docker Compose를 실행할 수 있는 Linux 또는 Synology NAS
- 접속 가능한 PostgreSQL 데이터베이스 **(데이터베이스 자체는 미리 생성)**
- Garmin Connect 계정
- ChatGPT 연결 시 OpenAI Secure MCP Tunnel ID와 Runtime API key

개발 및 테스트를 로컬에서 실행할 때는 Python 3.12도 필요합니다.

## 설정

```bash
cp .env.example .env
chmod 600 .env
bash scripts/create-mcp-token.sh
```

`.env`의 주요 항목은 다음과 같습니다. 실제 값은 Git에 올리지 마세요.

| 항목 | 용도 |
| --- | --- |
| `GARMIN_EMAIL`, `GARMIN_PASSWORD` | 최초 로그인과 토큰 갱신 |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | 수집기의 PostgreSQL 쓰기 계정 |
| `MCP_PGUSER`, `MCP_PGPASSWORD` | MCP 전용 PostgreSQL 읽기 계정 |
| `PUID`, `PGID` | `data/tokens`와 두 내부 토큰 파일의 소유자 UID/GID |
| `MCP_PORT` | NAS 호스트의 로컬 전용 MCP 포트. 기본값 `8765`; 이미 사용 중이면 변경 |
| `GARMIN_IMAGE` | 선택 사항. 기본값은 Docker Hub의 `disturb8264/garmin-mcp-bridge:0.1.0`; GHCR 이미지는 `ghcr.io/disturb8264/garmin-mcp-bridge:0.1.0` |
| `TUNNEL_ID`, `CONTROL_PLANE_API_KEY` | ChatGPT 터널 연결 시 필요 |

DB 스키마는 수집기의 첫 저장 실행 때 자동 적용됩니다. 별도 DB 역할이 없다면, `PGDATABASE=garmin_running`으로 생성한 DB에 관리자 계정을 임시로 설정한 뒤 로컬 Python 환경에서 `scripts/setup_db_roles.py`를 **한 번만** 실행할 수 있습니다. 이 스크립트는 쓰기/읽기 역할을 생성하고 `.env`를 교체하며, 관리자 접속 정보는 Git에서 제외되는 `data/db_admin.env`에 보관합니다. 다른 DB 이름이나 기존 역할을 사용할 때는 PostgreSQL에서 쓰기 계정의 테이블 생성·수정 권한과 읽기 계정의 `SELECT` 권한을 직접 준비하세요. 새 테이블 `garmin_date_coverage`에도 읽기 권한이 필요합니다.

## Docker 실행

처음에는 Garmin 로그인을 대화형으로 확인합니다. MFA가 필요하면 터미널에서 코드를 입력합니다. 성공한 토큰은 `data/tokens`에 남아 이후 실행에서 재사용됩니다.

```bash
sh scripts/build-image.sh
docker compose run --rm -it --entrypoint python garmin -m app.main --mode recent --limit 5 --dry-run
docker compose run --rm --entrypoint python garmin -m app.main --mode recent --limit 10
```

`.env`의 `TUNNEL_ID`와 `CONTROL_PLANE_API_KEY`를 채운 뒤 한 컨테이너를 실행합니다:

```bash
docker compose up -d --remove-orphans
docker compose ps
docker compose exec -T garmin python -m app.combined_healthcheck
```

`sh scripts/build-image.sh`는 같은 빌드 결과에 Docker Hub와 GHCR의 `0.1.0` 태그를 붙입니다. 이미 두 레지스트리에 올린 이미지를 NAS에서 사용할 때는 선택한 이미지를 먼저 내려받으세요:

```sh
docker pull disturb8264/garmin-mcp-bridge:0.1.0
# GHCR을 사용할 경우 .env에 GARMIN_IMAGE=ghcr.io/disturb8264/garmin-mcp-bridge:0.1.0을 설정하고:
docker pull ghcr.io/disturb8264/garmin-mcp-bridge:0.1.0
docker compose up -d --force-recreate
```

Compose는 로컬 이미지만 사용하며 이미지를 직접 빌드하거나 내려받지 않습니다. 코드를 변경해 로컬에서 실행하려면 빌드 스크립트를 다시 실행한 뒤 컨테이너를 교체하세요. 마지막 확인 명령이 성공하면 MCP 서버와 터널이 준비된 상태입니다. MCP 포트는 NAS 호스트의 `127.0.0.1:${MCP_PORT:-8765}`에만 바인딩됩니다. 터널 클라이언트는 `ghcr.io/openai/tunnel-client:v0.0.20`에서 이미지 빌드 시 가져옵니다.

Synology에서는 프로젝트 디렉터리와 `data/tokens`를 영속적으로 유지하세요. NAS의 UID/GID에 맞게 `PUID`, `PGID`를 지정해야 토큰 파일을 읽을 수 있습니다. 운동 직후 조회는 날짜 도구가 필요할 때 Garmin에서 수집합니다. 정기 동기화가 필요하면 NAS 작업 스케줄러에서 `docker compose run --rm --entrypoint python garmin -m app.main --mode sync`를 실행하세요.

과거 운동 전체를 한 번 수집할 때는 Python 환경과 DB 쓰기 계정이 설정된 곳에서 다음 명령을 실행하세요. 월별로 활동·랩·시계열을 저장하고, 완료한 날짜는 DB에 기록합니다. 중간에 멈추거나 Garmin 호출 제한이 발생하면 같은 명령을 다시 실행하면 완료한 달을 건너뜁니다. 현재 날짜는 수집 완료로 표시하지 않도록 종료일은 어제까지만 허용합니다. 기존 활동은 Activity ID 기준으로 갱신되므로 중복 행이 생기지 않습니다.

```sh
.venv/bin/python scripts/backfill-history.py --start 2000-01-01 --pause 1
```

NAS에서 `Collector token file must be private (mode 600)` 또는 MCP 토큰 권한 오류가 나면 프로젝트 디렉터리에서 다음을 실행하세요. 토큰 내용은 출력하지 않습니다.

```sh
stat -c '%n %a %u:%g' data/collector_internal_token data/mcp_internal_token
sudo chown "$(id -u):$(id -g)" data/collector_internal_token data/mcp_internal_token
chmod 600 data/collector_internal_token data/mcp_internal_token
```

`.env`의 `PUID`와 `PGID`를 각각 위 `id -u`, `id -g` 값으로 맞추고 `docker compose up -d --force-recreate`를 실행하세요. Garmin 토큰 디렉터리도 같은 사용자에게 쓰기 권한이 있어야 합니다. NAS 공유 폴더의 ACL 때문에 권한 변경이 반영되지 않으면 토큰 파일을 해당 사용자가 소유한 로컬 디렉터리로 옮겨 마운트 경로를 조정해야 합니다. 이 권한 수정에는 이미지 재빌드가 필요하지 않습니다.

Container Manager에서 Docker 이미지를 직접 실행하면 Compose의 `user: "${PUID}:${PGID}"` 설정이 적용되지 않습니다. 이 이미지의 기본 UID/GID는 `1000:1000`입니다. 토큰 파일을 `600`으로 바꾼 뒤 `Permission denied`가 나오면 `id -u disturb`, `id -g disturb`와 `docker inspect <컨테이너명> --format '{{.Config.User}}'`를 비교하세요. 직접 실행할 때는 컨테이너의 실행 사용자 UID/GID를 토큰 파일 소유자와 같게 지정하거나, Compose 프로젝트로 배포해 `.env`의 `PUID`/`PGID`를 사용하세요. 환경 변수만 추가해도 직접 실행한 컨테이너의 실행 UID/GID는 바뀌지 않습니다.

이미지를 직접 실행할 때는 NAS의 `.env` 파일도 자동으로 컨테이너 환경에 전달되지 않습니다. 날짜 조회 중 `Collector database is not configured`가 나오면 컨테이너 환경에 `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`가 모두 설정됐는지 확인하세요. 이 값들은 수집기의 DB 쓰기 계정이며, MCP 읽기 계정의 `MCP_PGUSER`/`MCP_PGPASSWORD`와 별도입니다. 비밀번호 값은 로그나 터미널에 출력하지 마세요.

Container Manager에서 직접 실행할 때 `MCP_PORT`는 **컨테이너 내부 포트**입니다. 현재 배포 이미지에서는 `8765`로 설정하고, NAS 호스트 포트가 `18765`라면 포트 매핑을 `127.0.0.1:18765 → 컨테이너 8765`로 지정하세요. `MCP_SERVER_URL`도 `http://127.0.0.1:8765/mcp`여야 합니다. Compose에서는 `.env`의 `MCP_PORT`가 호스트 포트이고 컨테이너 내부 포트는 `8765`로 고정됩니다.

## MCP 도구

| 도구 | 기능 |
| --- | --- |
| `list_activities` | 최근 저장 활동 목록, 종목 필터와 최대 20건 제한 |
| `get_activity` | Activity ID로 활동 요약과 랩·샘플 건수 조회 |
| `get_activity_laps` | Activity ID의 랩 조회 |
| `get_activity_samples` | Activity ID의 시계열을 최대 200건씩 조회 |
| `get_sync_status` | 마지막 수집 이력과 최신 저장 활동 조회 |
| `get_activities_by_date` | 현지 날짜 범위 조회, 필요 시 Garmin 수집 후 저장 |

날짜 도구의 입력은 `start_date`(필수, `YYYY-MM-DD`), `end_date`(선택, 기본값 시작일), `sport`(기본값 `all`; `running`, `cycling`, `swimming`, `multisport` 중 선택)입니다. 시작일과 종료일을 모두 포함하며 최대 **31일**입니다. 비교 기준은 Garmin 활동의 `start_local` 날짜입니다.

단일 날짜에 기존 기록이 있으면 DB에서 즉시 반환합니다. 여러 날짜를 요청했을 때는 `garmin_date_coverage`로 범위 전체의 수집 완료 여부를 확인합니다. 완료되지 않은 범위는 **요청 범위 전체**를 Garmin에서 다시 조회하고 Activity ID 기준으로 갱신합니다. `coverage_complete`는 해당 범위를 Garmin에서 오류 없이 전부 확인했는지 나타냅니다. Garmin 조회가 정상 완료돼 활동이 없을 때만 `not_found`를 반환합니다. 인증 실패, API 오류, 타임아웃은 별도 상태로 반환합니다. 요청 상한은 115초이며 내부 수집 작업은 80초가 지나면 종료합니다.

응답 상태 예시(활동 필드는 축약):

```json
{"status":"success","source":"database","activities":[{"activity_id":1}],"coverage_complete":true}
```

새로 수집했으면 `source`가 `garmin`이며, Garmin에서 정상적으로 빈 날짜를 확인했으면 `{"status":"not_found","source":"garmin","activities":[]}`를 반환합니다.

`get_activities_by_date`는 DB 저장을 유발할 수 있어 읽기 전용 도구로 표시하지 않습니다. 나머지 기존 도구는 읽기 전용입니다. 원본 GPS JSON, Garmin 비밀번호, 인증 토큰은 MCP 응답에 포함하지 않습니다.

## 실제 MCP 호출 확인

호스트에 Python 가상환경이 있으면 다음 명령으로 MCP HTTP 도구를 직접 호출할 수 있습니다. 기본 출력은 상태·출처·활동 건수만 표시합니다. `--json`을 붙이면 활동 정보 전체가 출력되므로 개인 기록을 공개 로그에 붙이지 마세요.

```bash
.venv/bin/python scripts/check-date-mcp.py 2026-01-01 --sport running
.venv/bin/python scripts/check-date-mcp.py 2026-01-01 --end-date 2026-01-07 --sport all
```

로컬 Python 환경은 다음처럼 만듭니다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Ubuntu 22.04에 Python 3.12가 없다면 `bash scripts/setup-python312.sh`로 프로젝트 내부 `.python/`에 설치할 수 있습니다.

## ChatGPT 연결

[Secure MCP Tunnel 안내](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)에 따라 Platform에서 만든 터널을 ChatGPT 작업 공간에 연결합니다. ChatGPT Plugins의 **Add custom MCP server → Connection: Tunnel**에서 터널을 선택하고, 이 개인용 구성의 앱 인증은 **No authentication**을 선택합니다. 터널 접근 권한과 내부 토큰으로 연결을 제한합니다. 앱을 설치한 뒤 `get_activities_by_date`로 날짜 조회를 시험하세요. 새 도구가 안 보이면 앱 설정에서 도구를 새로고침합니다. 여러 사용자가 공유하거나 공개 HTTPS로 운영할 때는 별도 사용자 인증 설계가 필요합니다.

## Git에 올리기 전 확인

| Git에 포함 | Git에서 제외 |
| --- | --- |
| `README.md`, `REQUIREMENTS.md`, `.env.example` | 실제 계정·DB·터널 키가 들어간 `.env`, `.env.*` (`.env.example` 제외) |
| `Dockerfile`, `docker-compose.yml`, `requirements.txt` | `data/`의 Garmin 인증 토큰, MCP 내부 토큰, `db_admin.env` |
| `app/`, `scripts/`, `sql/`, `tests/`, `.gitignore`, `.dockerignore` | `.venv/`, `.python/`, 로그·백업·인증서·개인 DB 파일, `*.save` |

Git 저장소가 없다면 먼저 `git init`을 실행합니다. 파일을 추가할 때는 다음처럼 **공개할 경로만 지정**하세요.

```bash
git add README.md REQUIREMENTS.md .env.example .gitignore .dockerignore \
  Dockerfile docker-compose.yml requirements.txt app/ scripts/ sql/ tests/
git diff --cached --name-only
git diff --cached --check
```

추가된 파일 목록에 `.env`, `data/`, 개인 기록 또는 비밀 파일이 없는지 확인한 뒤 커밋·푸시하세요. `.gitignore`는 이미 Git에 추적된 파일을 자동으로 제거하지 않으므로, 기존 저장소라면 추적 중인 비밀 파일도 별도로 확인해야 합니다. 이 프로젝트의 `ss.md.save`는 임시 백업 파일로 제외됩니다.

원래 러닝 중심 요구사항은 `REQUIREMENTS.md`에 남아 있습니다. 현재 구현은 사이클·수영·멀티스포츠와 날짜 기반 MCP 조회까지 확장돼 있습니다.
