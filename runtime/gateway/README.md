# 게이트웨이 실행 파일

| 파일·폴더 | 만드는 방법 |
| --- | --- |
| `.env` | `cp services/gateway/.env.example runtime/gateway/.env` 후 터널 ID와 API 키 입력 |
| `gateway.yaml` | `services/gateway/gateway.yaml.example`을 복사한 뒤 Garmin·InBody 주소와 공개 도구 확인 |
| `secrets/gateway_token` | `python3 scripts/create-gateway-token.py`가 없을 때만 생성. 직접 만들 수도 있지만 32자 이상의 임의 문자열과 mode `600` 필요 |
| `secrets/garmin_token`, `secrets/inbody_token` | `sh services/gateway/scripts/copy-upstream-tokens.sh`로 각 MCP의 **현재** 토큰을 복사 |
| `secrets/<id>_token` | 추가 MCP의 활성 토큰을 같은 값으로 저장. `gateway.yaml`의 해당 `token_file`에서 참조 |

토큰 생성 스크립트는 호스트에서 실행되며 별도 컨테이너를 만들지 않습니다. Garmin·InBody 토큰은 임의로 만들면 인증되지 않으므로 각각 실행 중인 서버의 활성 토큰을 복사합니다. 원본 경로가 다르면 복사 스크립트 실행 시 `GARMIN_TOKEN_SOURCE`, `INBODY_TOKEN_SOURCE`를 지정합니다. `gateway.yaml`의 기본 접속 주소는 Garmin `127.0.0.1:18765/mcp`, InBody `127.0.0.1:18766/mcp`입니다. NAS에서는 실제 주소로 수정합니다.

`.env`·`gateway.yaml`·토큰 파일은 Git에 올리지 않습니다. `secrets/`는 실행 UID만 들어갈 수 있게 하고 토큰 파일은 mode `600`으로 유지합니다.

실행 순서와 NAS 설정은 [04 게이트웨이 설정](../../docs/04-gateway-setup.md), 토큰별 용도는 [02 토큰 준비](../../docs/02-tokens.md)를 참고하세요.

다른 MCP 서버를 등록하는 방법은 [05 외부 MCP 추가](../../docs/05-add-upstream-mcp.md)에 있습니다.
