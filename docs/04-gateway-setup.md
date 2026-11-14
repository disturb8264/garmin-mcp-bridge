# 04. MCP 게이트웨이 설정

게이트웨이는 Garmin·InBody MCP의 도구를 모아 하나의 Secure MCP Tunnel로 제공합니다. Docker 이미지는 Garmin과 별도로 빌드하며, 실행 컨테이너는 **게이트웨이 1개**입니다. 아래 명령은 저장소 루트에서 실행합니다.

## 1. 설정 파일과 토큰 준비

Garmin MCP와 InBody MCP가 먼저 실행 중이어야 합니다. 같은 호스트에서 접근할 때 기본 주소는 Garmin `127.0.0.1:18765/mcp`, InBody `127.0.0.1:18766/mcp`입니다.

```sh
mkdir -p runtime/gateway
test -f runtime/gateway/.env || cp services/gateway/.env.example runtime/gateway/.env
test -f runtime/gateway/gateway.yaml || cp services/gateway/gateway.yaml.example runtime/gateway/gateway.yaml
chmod 600 runtime/gateway/.env
python3 scripts/create-gateway-token.py
sh services/gateway/scripts/copy-upstream-tokens.sh
```

`gateway.yaml`은 저장소의 샘플을 복사한 뒤 직접 수정합니다. `upstreams`의 Garmin·InBody `url`, `token_file`, `allowed_tools`를 확인하세요. 이미 운영 중인 설정 파일은 위 명령이 덮어쓰지 않습니다.

| 값 | 준비 방법 |
| --- | --- |
| `runtime/gateway/secrets/gateway_token` | `create-gateway-token.py`가 임의의 긴 토큰을 생성. 직접 만들어도 되지만 **32자 이상**, ASCII, 파일 mode `600` 필요 |
| `runtime/gateway/secrets/garmin_token` | Garmin MCP의 **활성** 내부 토큰 복사 |
| `runtime/gateway/secrets/inbody_token` | InBody MCP의 **활성** 내부 토큰 복사 |
| `.env`의 `TUNNEL_ID`, `CONTROL_PLANE_API_KEY` | 사용할 터널의 실제 ID와 발급받은 키 입력. 임의로 만들 수 없음 |

게이트웨이 자체 토큰 생성 스크립트는 기존 토큰을 덮어쓰지 않으며 별도 컨테이너를 실행하지 않습니다. Garmin·InBody 토큰을 임의로 새로 만들면 하위 서버 인증이 실패합니다.

토큰 복사 스크립트는 Garmin의 `runtime/garmin/data/mcp_internal_token`과 기본 InBody 경로 `/home/disturb/projects/inbody/data/mcp_internal_token`에서 활성 토큰을 복사합니다. 다른 위치에 있다면 다음처럼 원본 경로를 지정합니다.

```sh
INBODY_TOKEN_SOURCE=/실제/인바디/토큰/경로 \
GARMIN_TOKEN_SOURCE=/실제/가민/토큰/경로 \
sh services/gateway/scripts/copy-upstream-tokens.sh
```

`runtime/gateway/gateway.yaml`의 두 `url`을 실제 접근 주소로 확인합니다. 게이트웨이는 호스트 네트워크를 사용하므로 같은 호스트에 게시된 포트에는 `127.0.0.1`로 접근할 수 있습니다. 다른 호스트의 하위 MCP에는 HTTPS 주소가 필요합니다. `allowed_tools: ["*"]`는 수집·데이터 변경 도구도 공개하므로, 필요한 도구만 공개하려면 원본 도구 이름 목록으로 바꿉니다.

## 2. 빌드와 실행

루트 `.env`의 `GATEWAY_IMAGE`에 원하는 이미지 이름과 태그를 지정합니다. 빌드 스크립트와 Compose가 모두 이 값을 사용합니다.

```sh
sh scripts/build-gateway.sh
docker compose config --quiet
docker compose up -d gateway
docker compose ps gateway
docker compose exec -T gateway python -m gateway.combined_healthcheck
```

Compose의 `gateway`는 Garmin이 정상 상태가 된 뒤 시작합니다. 게이트웨이는 `127.0.0.1:18767/mcp`에서 수신하고 터널 클라이언트는 같은 컨테이너에서 실행됩니다. 터널 준비 상태는 호스트에서 `curl -sS http://127.0.0.1:8080/readyz`로 확인할 수 있습니다. 도구 목록은 시작 시와 60초마다 갱신되며 공개 이름에는 `garmin_`, `inbody_` 접두사가 붙습니다. ChatGPT에서 변경된 도구를 사용하려면 연결을 Refresh합니다.

## NAS Container Manager에서 직접 실행할 때

게이트웨이 이미지를 NAS에 전달하거나 게시한 뒤 컨테이너 **한 개**를 만듭니다. 초기화 컨테이너는 만들지 않습니다. Docker 앱의 환경변수에는 [게이트웨이 변수 전체 목록](../deploy/synology/gateway.env.example)을 사용합니다. 이 파일은 터널 값과 Compose가 추가하는 컨테이너 내부 설정을 **한곳에 모은 입력 목록**입니다.

`gateway.yaml`을 `/app/gateway.yaml:ro`, `secrets/`를 `/app/secrets:ro`로 마운트하고 호스트 네트워크를 선택합니다. 실행 UID/GID는 설정·토큰 파일을 읽을 수 있어야 합니다. `secrets/`는 mode `700`, 토큰 파일은 mode `600`으로 유지합니다. NAS의 실제 Garmin·InBody 포트에 맞춰 `gateway.yaml`의 주소를 수정합니다. 같은 `TUNNEL_ID`를 쓰는 기존 터널 클라이언트는 새 컨테이너를 올리기 전에 중지합니다. 마운트와 네트워크 설정은 [Synology 직접 실행 안내](../deploy/synology/README.md)의 표에도 정리했습니다.

Docker 앱의 기본 브리지 네트워크에서는 `127.0.0.1`이 게이트웨이 컨테이너 자신을 가리킵니다. 두 하위 MCP가 NAS 호스트의 루프백 포트에 있다면 게이트웨이를 **호스트 네트워크**로 실행해야 합니다. 연결 확인 명령과 실패 시 분기 방법은 [Synology 직접 실행 안내](../deploy/synology/README.md)에 있습니다.

필요한 파일 목록은 [runtime/gateway 안내](../runtime/gateway/README.md), 토큰 종류는 [02 토큰 준비](02-tokens.md), 전체 연결 구조는 [01 서비스 구조](01-architecture.md)를 참고하세요.
