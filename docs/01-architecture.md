# 01. 서비스 구조

이 저장소는 Garmin MCP와 MCP 게이트웨이를 **별도 Docker 이미지 두 개**로 관리합니다. 루트 `docker-compose.yml`에는 `garmin`, `gateway` 두 서비스만 있습니다. InBody MCP와 PostgreSQL은 이 Compose 밖에서 운영합니다.

```mermaid
flowchart LR
    ChatGPT[ChatGPT] <-->|Secure MCP Tunnel| Gateway[Gateway 컨테이너]
    Gateway <-->|HTTP MCP · 내부 토큰| Garmin[Garmin 컨테이너]
    Gateway <-->|HTTP MCP · 내부 토큰| InBody[InBody MCP · 외부 서비스]
    Garmin -->|활동 조회·수집| GarminConnect[Garmin Connect]
    Garmin <-->|저장·조회| DB[(PostgreSQL)]
```

Garmin 컨테이너는 수집기와 MCP 서버를 실행하며 터널 클라이언트는 포함하지 않습니다. 게이트웨이 컨테이너가 하위 MCP의 도구 목록을 읽고 `garmin_`, `inbody_` 이름으로 제공하며, 터널 클라이언트도 이 컨테이너에서 실행합니다.

| 경로 | 역할 |
| --- | --- |
| `services/garmin/` | Garmin 코드와 Dockerfile |
| `services/gateway/` | 게이트웨이 코드와 Dockerfile |
| `scripts/build-garmin.sh`, `scripts/build-gateway.sh` | 이미지별 빌드 |
| `runtime/garmin/`, `runtime/gateway/` | 실행 설정·토큰·데이터. 안내 문서만 Git 포함 |
| `scripts/create-gateway-token.py` | 게이트웨이 자체 토큰을 호스트에서 생성. 별도 컨테이너 없음 |

기본 구성은 게이트웨이와 두 하위 MCP가 같은 호스트에 있어, 게이트웨이가 호스트 네트워크에서 Garmin `127.0.0.1:18765/mcp`, InBody `127.0.0.1:18766/mcp`에 연결합니다. 다른 서버에 있는 MCP는 `runtime/gateway/gateway.yaml`에 HTTPS URL을 지정합니다. 네트워크 모드는 루트 `.env`의 `GATEWAY_NETWORK_MODE`로 선택합니다. 실행 방법과 NAS 설정은 루트 [README](../README.md)를 참고하세요.
