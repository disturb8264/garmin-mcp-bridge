# Garmin MCP 설정

Garmin 컨테이너는 활동 수집기와 MCP 서버를 함께 실행합니다. 터널은 포함하지 않으며, 같은 호스트의 게이트웨이가 내부 토큰으로 Garmin MCP에 접속합니다. 아래 명령은 저장소 루트에서 실행합니다.

## 1. 실행 설정과 토큰 준비

PostgreSQL 데이터베이스를 먼저 준비합니다. 수집용 계정은 스키마 생성·마이그레이션과 활동 저장 권한이 필요하고, MCP 조회용 계정은 저장 테이블의 `SELECT` 권한이 필요합니다.

```sh
cp .env.example .env
mkdir -p runtime/garmin/data/tokens runtime/gateway
cp services/garmin/.env.example runtime/garmin/.env
cp services/gateway/.env.example runtime/gateway/.env
chmod 700 runtime runtime/garmin runtime/garmin/data runtime/garmin/data/tokens runtime/gateway
chmod 600 .env runtime/garmin/.env runtime/gateway/.env
bash services/garmin/scripts/create-mcp-token.sh
```

`runtime/garmin/.env`에 `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `MCP_PGUSER`, `MCP_PGPASSWORD`를 설정합니다. 기본 예제의 `GARMIN_TOKEN_DIR=../../runtime/garmin/data/tokens`는 로컬 Python 실행용이며 Docker에서는 `/app/data/tokens`로 덮어씁니다. 비밀번호와 토큰 값은 Git이나 문서에 넣지 않습니다.

Garmin만 실행하더라도 Compose는 게이트웨이의 `env_file` 경로를 확인하므로 위 명령에서 빈 `runtime/gateway/.env`도 만듭니다. 게이트웨이를 시작하기 전까지 그 파일의 터널 값을 채울 필요는 없습니다.

루트 `.env`에서는 `PUID`, `PGID`를 토큰 파일 소유자에 맞추고, `MCP_PORT`를 확인합니다. 기본값은 호스트 포트 `18765`, `MCP_BIND_ADDRESS=127.0.0.1`입니다. 게이트웨이가 같은 호스트에서 실행되면 이 바인딩 주소를 유지합니다. `create-mcp-token.sh`는 Garmin MCP용 토큰과 내부 수집 API용 토큰을 각각 만들며, 기존 파일이 있으면 보존합니다.

## 2. 이미지 빌드와 Garmin 첫 로그인

```sh
sh scripts/build-garmin.sh
docker compose run --rm -it --entrypoint python garmin \
  -m app.main --mode recent --limit 5 --dry-run
```

첫 로그인에서 Garmin MFA가 요구되면 터미널에 코드를 입력합니다. 인증 토큰은 `runtime/garmin/data/tokens/`에 저장되어 다음 실행에 사용됩니다. `--dry-run`은 활동을 DB에 저장하지 않으므로 로그인 확인에 사용할 수 있습니다.

새 DB에 최근 활동을 저장하려면 다음 명령을 실행합니다. 이때 수집기가 필요한 스키마·마이그레이션을 적용합니다. **기존 운영 DB에는 완료된 백필·GPS/수영 보강을 다시 실행하지 않습니다.**

```sh
docker compose run --rm --entrypoint python garmin \
  -m app.main --mode recent --limit 10
```

## 3. Garmin MCP 실행과 확인

```sh
docker compose up -d garmin
docker compose ps garmin
docker compose exec -T garmin python -m app.combined_healthcheck
```

Compose는 Garmin 이미지를 직접 빌드하거나 내려받지 않습니다. Garmin MCP는 컨테이너의 `8765` 포트에서 수신하고, Compose가 기본적으로 호스트 `127.0.0.1:18765`에 연결합니다. 내부 수집 API의 `8766` 포트는 호스트에 게시하지 않습니다. 인증 없는 MCP 요청에 HTTP `401`이 반환되는 것은 정상입니다. 게이트웨이에는 `runtime/garmin/data/mcp_internal_token`의 **현재 값**을 토큰 파일로 복사하고, Garmin URL을 `http://127.0.0.1:18765/mcp`로 설정합니다.

## NAS Container Manager에서 직접 실행할 때

NAS에는 빌드한 Garmin 이미지를 별도로 전달하거나 게시해야 합니다. 컨테이너를 만들 때 `runtime/garmin/.env`의 값을 환경변수로 입력하고, `docker-compose.yml`의 `garmin.environment` 값도 적용합니다. 토큰 디렉터리와 두 토큰 파일의 마운트 경로, 컨테이너 포트 `8765` → NAS 호스트 포트 `18765` 설정을 Compose와 동일하게 맞춥니다. 실행 사용자 UID/GID는 파일 소유자에 맞춰 지정하며, 기존 NAS에서 확인된 값은 `1000:1000`입니다. `PUID`·`PGID` 환경변수만 입력해서는 직접 실행 컨테이너의 실행 사용자가 바뀌지 않습니다.

설정 전체의 연결 구조는 [01 서비스 구조](01-architecture.md), 두 컨테이너 실행 방법은 [루트 README](../README.md)를 참고하세요.
