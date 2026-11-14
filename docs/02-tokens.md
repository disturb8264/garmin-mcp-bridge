# 02. 토큰 준비

이 구성에는 서로 다른 용도의 토큰이 있습니다. **새로 만들어도 되는 토큰**과 **실행 중인 서버의 값을 복사해야 하는 토큰**을 구분합니다. 명령은 저장소 루트에서 실행합니다.

| 토큰 | 쓰는 곳 | 준비 방법 |
| --- | --- | --- |
| Garmin MCP 내부 토큰 | 게이트웨이 → Garmin MCP 인증 | `bash services/garmin/scripts/create-mcp-token.sh`가 `runtime/garmin/data/mcp_internal_token`에 생성 |
| Garmin 수집 API 내부 토큰 | Garmin 컨테이너 안의 MCP → 수집 API 인증 | 같은 스크립트가 `runtime/garmin/data/collector_internal_token`에 생성 |
| Garmin Connect 로그인 토큰 | Garmin 계정 로그인 유지 | [03 Garmin 설정](03-garmin-setup.md)의 첫 대화형 로그인에서 `runtime/garmin/data/tokens/`에 저장 |
| 게이트웨이 자체 토큰 | 터널 클라이언트 → 게이트웨이 인증 | `python3 scripts/create-gateway-token.py`가 `runtime/gateway/secrets/gateway_token`에 생성 |
| 게이트웨이의 Garmin·InBody 토큰 복사본 | 게이트웨이 → 각 하위 MCP 인증 | `sh services/gateway/scripts/copy-upstream-tokens.sh`로 **각 서버의 활성 토큰**을 복사 |
| 추가 MCP의 토큰 복사본 | 게이트웨이 → 추가 MCP 인증 | 추가 서버의 **활성 토큰과 같은 값**을 `runtime/gateway/secrets/<id>_token`에 저장. 서버가 `X-MCP-Internal-Token` 헤더를 받아야 함 |
| `TUNNEL_ID`, `CONTROL_PLANE_API_KEY` | 터널 연결 | 실제 터널 ID와 발급받은 키를 `runtime/gateway/.env`에 입력. 임의 생성 불가 |

```sh
bash services/garmin/scripts/create-mcp-token.sh
python3 scripts/create-gateway-token.py
sh services/gateway/scripts/copy-upstream-tokens.sh
```

Garmin과 게이트웨이의 자체 내부 토큰은 스크립트가 임의로 생성하며, **이미 있으면 덮어쓰지 않습니다**. 게이트웨이의 `garmin_token`은 새 토큰이 아니라 Garmin MCP의 `mcp_internal_token` 복사본이어야 합니다. InBody 토큰도 InBody MCP에서 현재 사용하는 값을 복사해야 합니다. 하위 서버 토큰을 교체했다면 복사 스크립트를 다시 실행하고 게이트웨이를 재시작합니다.

현재 코드는 내부 토큰을 **파일에서 읽습니다**. `MCP_TOKEN_FILE`, `COLLECTOR_TOKEN_FILE`, `MCP_COLLECTOR_TOKEN_FILE`과 `gateway.yaml`의 `token_file`은 토큰 문자열이 아닌 **파일 경로**입니다. 여기에 토큰 값을 환경변수처럼 넣으면 동작하지 않습니다. 게이트웨이는 하위 서버마다 `X-MCP-Internal-Token` 헤더에 해당 토큰을 담아 보냅니다. `Authorization: Bearer`만 받는 서버는 현재 설정만으로 연결되지 않습니다. 파일은 mode `600`, 토큰 디렉터리는 mode `700`으로 유지하고 Git에 올리지 않습니다. 실제 마운트 경로는 루트 `docker-compose.yml`을 따릅니다.
