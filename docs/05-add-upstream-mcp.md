# 05. 외부 MCP 추가

게이트웨이에 다른 MCP 서버를 연결할 때는 `runtime/gateway/gateway.yaml`에 하위 서버를 등록합니다. **호환되는 서버라면 게이트웨이 이미지 재빌드 없이 설정 수정과 재시작만** 필요합니다. 아래 명령은 저장소 루트에서 실행합니다.

## 연결 가능한 서버

현재 게이트웨이는 HTTP 기반 Streamable MCP의 **도구(`tools/list`, `tools/call`)**를 중계합니다. 새 서버는 `X-MCP-Internal-Token` 헤더로 인증해야 하며, 게이트웨이에 해당 서버의 **활성 토큰** 파일이 있어야 합니다. 원격 호스트는 `https://` 주소를 사용합니다. 일반 HTTP는 `127.0.0.1` 또는 `localhost` 주소만 허용합니다. stdio 전용 서버나 OAuth 등 다른 인증 방식의 서버는 현재 설정만으로 등록할 수 없습니다.

## 1. 하위 서버 토큰 준비

새 서버의 활성 내부 토큰을 게이트웨이의 `secrets/` 폴더에 복사합니다. 예를 들어 `example` 서버를 추가한다면:

```sh
install -m 600 /실제/서버/활성/토큰/경로 runtime/gateway/secrets/example_token
```

토큰을 임의로 새로 만들면 하위 서버와 값이 달라 인증되지 않습니다. 토큰 파일은 ASCII 32자 이상이며 mode `600`이어야 합니다. 원본이 다른 호스트에 있다면 안전하게 전달한 뒤 같은 경로에 저장합니다. 게이트웨이 컨테이너의 실행 UID가 `runtime/gateway/secrets/`에 들어가 파일을 읽을 수 있어야 합니다.

## 2. `gateway.yaml`에 서버 추가

`runtime/gateway/gateway.yaml`의 `upstreams:` 아래에 항목을 하나 추가합니다. 다음 값은 **예시**이므로 실제 서버 URL, 토큰 파일 이름, 도구 이름으로 바꿉니다.

```yaml
  - id: example
    url: https://mcp.example.net/mcp
    token_file: secrets/example_token
    allowed_tools: ["get_status"]
```

`id`는 다른 서버와 겹치지 않는 소문자·숫자·밑줄 이름이어야 하며 소문자로 시작합니다. 공개 도구 이름은 `example_get_status`처럼 `<id>_<원본 도구 이름>`이 됩니다. `token_file`은 컨테이너의 `/app/gateway.yaml`을 기준으로 해석되므로, `secrets/example_token`은 `/app/secrets/example_token`을 가리킵니다.

`allowed_tools`에는 공개할 **원본 도구 이름**을 적습니다. `['*']`도 가능하지만 해당 서버의 모든 도구가 공개되므로 수집·변경 도구가 있는지 먼저 확인합니다. 도구 이름을 모른다면 하위 서버의 도구 목록을 확인한 뒤 필요한 이름을 적습니다.

## 3. 게이트웨이 재시작과 확인

```sh
docker compose restart gateway
docker compose exec -T gateway python -m gateway.combined_healthcheck
docker compose logs --tail=40 gateway
```

로그에서 새 서버 ID의 `refreshed upstream=example tools=...` 항목을 확인합니다. 접속에 실패하면 `refresh failed upstream=example`이 기록됩니다. 설정 파일을 바꾸면 **재시작해야** 새 서버가 등록됩니다. 등록 후 도구 정의는 기본 60초마다 갱신되지만, ChatGPT 연결에서 새 도구를 보려면 연결 Refresh가 필요합니다.

NAS Container Manager에서 직접 실행한다면 수정한 `gateway.yaml`과 새 토큰 파일이 기존 마운트에 있는지 확인한 뒤 **게이트웨이 컨테이너 한 개만** 재시작합니다. 전체 절차의 기본 설정은 [04 게이트웨이 설정](04-gateway-setup.md)을 참고하세요.
