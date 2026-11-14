# Garmin MCP + MCP 게이트웨이

이 저장소에서 Docker 이미지 **두 개**를 빌드합니다. Garmin은 수집기와 MCP 서버만 실행하고 터널은 사용하지 않습니다. 게이트웨이는 Garmin과 외부 InBody MCP의 도구를 모아 Secure MCP Tunnel로 제공합니다. 루트 `docker-compose.yml`의 서비스는 `garmin`, `gateway` 두 개뿐입니다.

문서는 [01 서비스 구조](docs/01-architecture.md) → [02 토큰 준비](docs/02-tokens.md) → [03 Garmin MCP 설정](docs/03-garmin-setup.md) → [04 게이트웨이 설정](docs/04-gateway-setup.md) → [05 외부 MCP 추가](docs/05-add-upstream-mcp.md) 순서로 읽으면 됩니다.

## 폴더 구조

| 경로 | 용도 |
| --- | --- |
| `services/garmin/` | Garmin 소스, SQL, 테스트, Dockerfile |
| `services/gateway/` | 게이트웨이 소스, Dockerfile, 설정 예제 |
| `scripts/build-garmin.sh`, `scripts/build-gateway.sh` | 각 이미지의 별도 빌드 스크립트 |
| `scripts/create-gateway-token.py` | 호스트에서 게이트웨이 자체 토큰 생성. 컨테이너를 만들지 않음 |
| `runtime/garmin/` | Garmin `.env`, 토큰, 로컬 데이터. 실행 파일은 Git 제외 |
| `runtime/gateway/` | 게이트웨이 `.env`, `gateway.yaml`, 토큰 복사본. 실행 파일은 Git 제외 |
| `docs/archive/` | 이전 배포 안내. 현재 경로에는 적용되지 않음 |

InBody는 이 저장소 밖에서 운영합니다. 기본 게이트웨이 설정은 Garmin `127.0.0.1:18765/mcp`, InBody `127.0.0.1:18766/mcp`에 연결하며, 게이트웨이 자체는 `127.0.0.1:18767/mcp`에서 수신합니다. 다른 호스트에 배포할 때는 `runtime/gateway/gateway.yaml`의 하위 서버 주소를 실제 주소로 바꿉니다.

실행 파일별 생성 방법은 [runtime 안내](runtime/README.md)에 정리했습니다.

## 실행 파일 준비

```sh
cp .env.example .env
mkdir -p runtime/garmin/data/tokens runtime/gateway
cp services/garmin/.env.example runtime/garmin/.env
cp services/gateway/.env.example runtime/gateway/.env
chmod 700 runtime runtime/garmin runtime/garmin/data runtime/garmin/data/tokens runtime/gateway
chmod 600 .env runtime/garmin/.env runtime/gateway/.env
bash services/garmin/scripts/create-mcp-token.sh
test -f runtime/gateway/gateway.yaml || cp services/gateway/gateway.yaml.example runtime/gateway/gateway.yaml
python3 scripts/create-gateway-token.py
sh services/gateway/scripts/copy-upstream-tokens.sh
```

`runtime/garmin/.env`에 Garmin 계정과 PostgreSQL 설정을 입력합니다. 로컬 Python 실행에는 `GARMIN_TOKEN_DIR=../../runtime/garmin/data/tokens`를 사용하고, Docker에서는 `/app/data/tokens`로 덮어씁니다. `runtime/gateway/.env`에는 `TUNNEL_ID`와 `CONTROL_PLANE_API_KEY`를 입력합니다. 루트 `.env`에는 이미지 이름·포트·UID/GID 같은 Compose 설정만 둡니다.

`gateway.yaml`은 샘플을 복사해 Garmin·InBody 주소와 공개할 도구를 확인합니다. 토큰 생성 스크립트는 게이트웨이 자체 토큰이 없을 때만 만들며 기존 파일은 보존합니다. 토큰 복사 스크립트는 기본적으로 InBody의 `/home/disturb/projects/inbody/data/mcp_internal_token`과 `runtime/garmin/data/mcp_internal_token`을 복사합니다. 실제 위치가 다르면 `INBODY_TOKEN_SOURCE` 또는 `GARMIN_TOKEN_SOURCE`를 지정합니다. 하위 서버 토큰이 바뀌면 다시 복사하고 게이트웨이를 재시작합니다.

## 빌드 및 실행

```sh
sh scripts/build-garmin.sh
sh scripts/build-gateway.sh
docker compose config --quiet
docker compose up -d
docker compose ps
```

두 빌드 스크립트는 각각 `services/garmin`, `services/gateway`만 빌드 대상으로 사용합니다. Compose는 로컬 이미지 두 개를 사용하며 이미지를 직접 빌드하거나 내려받지 않습니다. 게이트웨이는 Garmin이 정상 상태가 된 뒤 시작합니다. InBody도 별도로 접근 가능해야 InBody 도구가 동작합니다.

빌드 스크립트와 Compose는 모두 루트 `.env`의 `GARMIN_IMAGE`, `GATEWAY_IMAGE`를 사용합니다. 버전을 바꿀 때는 이 두 태그를 함께 수정하고, 새 배포용 기본값은 `.env.example`에도 반영합니다.

```sh
docker compose exec -T garmin python -m app.combined_healthcheck
docker compose exec -T gateway python -m gateway.combined_healthcheck
```

게이트웨이는 시작할 때와 60초마다 하위 서버의 도구 목록을 읽습니다. 기본 `allowed_tools: ["*"]`는 수집·데이터 변경 도구까지 공개합니다. 공개 범위를 제한하려면 `runtime/gateway/gateway.yaml`을 수정합니다. 도구 이름에는 `garmin_`, `inbody_` 접두사가 붙습니다. ChatGPT에서 도구 정의가 바뀐 뒤에는 연결 Refresh가 필요할 수 있습니다.

## Synology Container Manager

실행 컨테이너는 **Garmin 1개와 게이트웨이 1개**입니다. NAS에서도 위 실행 파일을 먼저 준비합니다. 게이트웨이 이미지에만 터널 클라이언트가 들어 있으며 초기화 컨테이너는 필요하지 않습니다.

- 두 컨테이너 모두 마운트한 토큰 파일을 읽을 수 있는 UID/GID로 실행합니다. Garmin NAS의 마지막 정상 실행 값은 `1000:1000`입니다.
- Garmin: `runtime/garmin/.env` 값을 전달하고 `runtime/garmin/data/tokens`를 `/app/data/tokens`에, 두 내부 토큰 파일을 `docker-compose.yml`에 적힌 경로에 마운트합니다. 컨테이너의 8765 포트를 NAS의 18765 포트에 연결합니다. 수집 API의 8766 포트는 컨테이너 내부에 둡니다.
- 게이트웨이: `runtime/gateway/.env` 값을 전달하고 `gateway.yaml`을 `/app/gateway.yaml:ro`, `secrets/`를 `/app/secrets:ro`로 마운트합니다. Garmin·InBody의 호스트 포트에 닿도록 호스트 네트워크를 사용합니다. 추가 환경변수는 `docker-compose.yml`의 `gateway.environment`를 따릅니다.
- `gateway.yaml`의 Garmin·InBody 주소를 NAS의 실제 주소로 확인합니다. 같은 터널 ID를 쓰는 기존 클라이언트와 새 클라이언트를 동시에 실행하지 않습니다.

로컬 빌드한 `disturb8264/garmin-mcp:0.4.0`, `disturb8264/mcp-gateway:0.4.0` 이미지는 레지스트리에 게시하지 않았습니다. NAS에는 두 이미지를 각각 전달하거나 게시한 뒤 배포합니다. 이 저장소의 폴더 변경으로 기존 NAS 컨테이너가 바뀌지는 않습니다.

## 로컬 테스트

```sh
PYTHONPATH=services/garmin .venv/bin/python -m unittest discover -s services/garmin/tests -q
```

이전 Garmin 상세 문서는 `docs/archive/garmin-readme-before-layout.md`에 보관했습니다. DB 백업과 완료된 백필은 이번 구조 변경의 대상이 아닙니다. 같은 운영 DB에 마이그레이션이나 보강을 다시 실행하지 않습니다.
