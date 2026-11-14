# Synology Container Manager 직접 실행

Compose를 사용하지 않고 Docker 앱에서 컨테이너를 직접 만들 때는 **Garmin 1개, 게이트웨이 1개**를 만듭니다. 환경변수는 아래 두 파일의 항목을 각각 해당 컨테이너에 모두 입력합니다. 빈 값은 실제 값으로 채웁니다. 이 파일들은 입력 목록이며 실제 비밀 값을 적어 Git에 올리지 않습니다.

- [Garmin 환경변수 전체 목록](garmin.env.example)
- [게이트웨이 환경변수 전체 목록](gateway.env.example)

루트 `.env`의 `GARMIN_IMAGE`, `GATEWAY_IMAGE`, `PUID`, `PGID`, `MCP_BIND_ADDRESS`는 **Compose 설정**입니다. Docker 앱에서는 이미지, 실행 사용자, 포트·네트워크를 화면에서 직접 지정합니다. `PUID`·`PGID`를 환경변수로만 넣어도 실행 UID/GID가 바뀌지 않습니다.

| 컨테이너 | 실행 사용자·네트워크 | 마운트 | 포트 |
| --- | --- | --- | --- |
| Garmin | 토큰 파일을 읽고 `tokens/`에 쓸 수 있는 UID/GID. 기존 NAS 정상 값 `1000:1000` | `runtime/garmin/data/tokens` → `/app/data/tokens`; `runtime/garmin/data/mcp_internal_token` → `/run/secrets/mcp_internal_token:ro`; `runtime/garmin/data/collector_internal_token` → `/run/secrets/collector_internal_token:ro` | 컨테이너 `8765` → NAS `18765`; 수집 API `8766`은 게시하지 않음 |
| 게이트웨이 | 설정·토큰 파일을 읽을 수 있는 UID/GID. 호스트 네트워크 | `runtime/gateway/gateway.yaml` → `/app/gateway.yaml:ro`; `runtime/gateway/secrets` → `/app/secrets:ro` | 별도 포트 매핑 없음. 호스트에서 `127.0.0.1:18767/mcp` 사용 |

Garmin을 먼저 시작해 정상 상태를 확인한 뒤 게이트웨이를 시작합니다. `gateway.yaml`의 Garmin·InBody URL은 NAS에서 실제 접근 가능한 주소로 수정합니다. 같은 터널 ID를 쓰는 기존 터널 클라이언트는 새 게이트웨이 시작 전에 중지합니다. 토큰 생성과 복사 방법은 [02 토큰 준비](../../docs/02-tokens.md), 각 서비스 절차는 [03 Garmin 설정](../../docs/03-garmin-setup.md)과 [04 게이트웨이 설정](../../docs/04-gateway-setup.md)을 참고하세요.

**게이트웨이 네트워크는 반드시 호스트 모드로 지정합니다.** Docker 앱의 기본 브리지 모드에서는 `gateway.yaml`의 `127.0.0.1`이 NAS가 아니라 게이트웨이 컨테이너 자신을 가리켜 두 하위 MCP 연결이 실패합니다. 컨테이너 터미널에서 다음 명령의 결과가 두 포트 모두 `0`인지 확인합니다.

```sh
python -c 'import socket; print([(p, socket.socket().connect_ex(("127.0.0.1", p))) for p in (18765, 18766)])'
```

호스트 모드에서도 `111`(연결 거부)이 나오면 Garmin·InBody의 NAS 포트가 루프백 `127.0.0.1`에서 수신하는지 확인합니다. 현재 게이트웨이는 `http://192.168.100.25:...` 같은 LAN HTTP 주소를 하위 서버 URL로 허용하지 않습니다.
