# 게이트웨이 실행 파일

| 파일·폴더 | 만드는 방법 |
| --- | --- |
| `.env` | `cp services/gateway/.env.example runtime/gateway/.env` 후 터널 ID와 API 키 입력 |
| `gateway.yaml` | `python3 scripts/init-gateway.py` 실행 후 Garmin·InBody 주소 확인 |
| `secrets/gateway_token` | 위 초기화 스크립트가 없을 때만 생성 |
| `secrets/garmin_token`, `secrets/inbody_token` | `sh services/gateway/scripts/copy-upstream-tokens.sh`로 각 MCP의 **현재** 토큰을 복사 |

초기화 스크립트는 호스트에서 실행되며 별도 컨테이너를 만들지 않습니다. 토큰 원본의 경로가 다르면 복사 스크립트 실행 시 `GARMIN_TOKEN_SOURCE`, `INBODY_TOKEN_SOURCE`를 지정합니다. `gateway.yaml`의 기본 접속 주소는 Garmin `127.0.0.1:18765/mcp`, InBody `127.0.0.1:18766/mcp`입니다. NAS에서는 실제 주소로 수정합니다.

`.env`·`gateway.yaml`·토큰 파일은 Git에 올리지 않습니다. `secrets/`는 실행 UID만 들어갈 수 있게 하고 토큰 파일은 mode `600`으로 유지합니다.

실행 순서와 NAS 설정은 [03 게이트웨이 설정](../../docs/03-gateway-setup.md)을 참고하세요.
