# 05. 외부 MCP 추가

게이트웨이에 다른 MCP 서버를 연결할 때는 `runtime/gateway/gateway.yaml`에 하위 서버를 등록합니다. **게이트웨이 이미지 0.4.1 이상이라면 호환되는 서버를 추가할 때 이미지 재빌드 없이 설정 수정과 재시작만** 필요합니다. 아래 명령은 저장소 루트에서 실행합니다.

## 연결 가능한 서버

현재 게이트웨이는 HTTP 기반 Streamable MCP의 **도구(`tools/list`, `tools/call`)**를 중계합니다. 새 서버는 `X-MCP-Internal-Token` 헤더로 인증해야 하며, 게이트웨이에 해당 서버의 **활성 토큰** 파일이 있어야 합니다. `Authorization: Bearer`만 검사하는 서버는 인증 헤더를 맞춰야 합니다. 원격 호스트에는 HTTPS를 권장합니다. 사설망 IPv4 주소의 HTTP는 서버 항목에 `allow_private_http: true`를 명시하면 사용할 수 있습니다. 이 경우 토큰과 데이터가 네트워크에서 암호화되지 않습니다. 원격 서버에 연결할 때는 브리지 네트워크도 사용할 수 있습니다. stdio 전용 서버나 OAuth 등 다른 인증 방식의 서버는 현재 설정만으로 등록할 수 없습니다.

## 1. 하위 서버 토큰 준비

새 서버의 활성 내부 토큰을 게이트웨이의 `secrets/` 폴더에 복사합니다. 예를 들어 `example` 서버를 추가한다면:

```sh
install -m 600 /실제/서버/활성/토큰/경로 runtime/gateway/secrets/example_token
```

토큰을 임의로 새로 만들면 하위 서버와 값이 달라 인증되지 않습니다. 테스트용 서버를 직접 만든다면 토큰을 한 번 생성해 **서버와 게이트웨이 양쪽에 같은 값**을 설정하면 됩니다. 토큰 파일은 ASCII 32자 이상이며 mode `600`이어야 합니다. 원본이 다른 호스트에 있다면 안전하게 전달한 뒤 같은 경로에 저장합니다. 게이트웨이 컨테이너의 실행 UID가 `runtime/gateway/secrets/`에 들어가 파일을 읽을 수 있어야 합니다. 토큰 파일을 교체한 뒤에는 게이트웨이를 재시작합니다.

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

다른 서버의 사설망 HTTP MCP를 추가하는 경우에는 다음과 같이 적습니다. `url`은 `/health`가 아닌 실제 MCP 엔드포인트여야 하며, **서버가 실제 수신하는 IP와 포트**를 확인합니다. 아래 예시는 Echo 서버가 `192.168.100.12:8767`에서 수신하고, `echo_token`이 서버의 **활성 토큰과 같은 값**이며, 도구의 원본 이름이 `echo`일 때 사용합니다.

```yaml
  - id: echo
    url: http://192.168.100.12:8767/mcp
    token_file: secrets/echo_token
    allow_private_http: true
    allowed_tools: ["echo"]
```

게이트웨이 컨테이너에서 `secrets/echo_token`을 `/app/secrets/echo_token`으로 읽을 수 있어야 합니다. 이 설정으로 공개되는 이름은 `echo_echo`입니다. `allow_private_http`는 게이트웨이 이미지 `0.4.1` 이상에서 지원합니다. 이전 이미지를 사용 중이면 새 이미지를 내려받고 **컨테이너를 재생성**해야 합니다. 이미지 태그만 바꾸거나 기존 컨테이너를 재시작해도 실행 중인 코드가 바뀌지 않습니다.

## 3. 게이트웨이 재시작과 확인

```sh
docker compose restart gateway
docker compose exec -T gateway python -m gateway.combined_healthcheck
docker compose logs --tail=40 gateway
```

로그에서 새 서버 ID의 `refreshed upstream=example tools=...` 항목을 확인합니다. Echo 예시라면 `refreshed upstream=echo tools=1`이 성공 상태입니다. 접속에 실패하면 `refresh failed upstream=echo error=ExceptionGroup`처럼 기록될 수 있습니다. 설정 파일을 바꾸면 **재시작해야** 새 서버가 등록됩니다. 등록 후 도구 정의는 기본 60초마다 갱신되지만, ChatGPT 연결에서 새 도구를 보려면 연결 Refresh가 필요합니다.

NAS Container Manager에서 직접 실행한다면 수정한 `gateway.yaml`과 새 토큰 파일이 기존 마운트에 있는지 확인한 뒤 **게이트웨이 컨테이너 한 개만** 재시작합니다. 전체 절차의 기본 설정은 [04 게이트웨이 설정](04-gateway-setup.md)을 참고하세요.

## 문제 해결

| 증상 | 확인할 점 |
| --- | --- |
| `upstream echo needs loopback HTTP or HTTPS` | 이전 게이트웨이 이미지가 실행 중입니다. `0.4.1` 이상을 내려받고 컨테이너를 재생성합니다. |
| `refresh failed upstream=echo error=ExceptionGroup` | 게이트웨이 컨테이너에서 Echo 서버의 실제 IP·포트에 접속되는지 확인합니다. 예시 서버 포트는 **8767**입니다. 그다음 아래 인증 검사를 실행합니다. |
| 인증 검사에서 `401` | 서버의 활성 토큰과 `/app/secrets/echo_token`이 같은지, 서버가 `X-MCP-Internal-Token` 헤더를 받는지 확인합니다. `Authorization: Bearer`만 받는 서버는 401을 반환합니다. |
| `refreshed upstream=echo tools=0` | `allowed_tools`에 서버가 실제 공개하는 **원본 도구 이름**을 적었는지 확인합니다. Echo 예시는 `echo`입니다. |
| `refreshed upstream=echo tools=1`인데 ChatGPT에 도구가 없음 | ChatGPT의 게이트웨이 MCP 연결을 Refresh합니다. 공개 이름은 `echo_echo`입니다. |

`/health`의 HTTP 200은 서버 프로세스가 응답한다는 뜻이며 MCP 인증이나 도구 등록까지 보장하지 않습니다. 다음 검사는 **게이트웨이 컨테이너에 실제 마운트된 토큰**을 사용합니다. `<gateway-container>`를 NAS의 실제 컨테이너 이름으로 바꿔 실행합니다. 토큰 값은 출력하지 않습니다.

```sh
docker exec -i <gateway-container> python - <<'PY'
from pathlib import Path
import httpx

token = Path('/app/secrets/echo_token').read_text().strip()
response = httpx.post(
    'http://192.168.100.12:8767/mcp',
    headers={
        'X-MCP-Internal-Token': token,
        'Accept': 'application/json, text/event-stream',
    },
    json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'gateway-probe', 'version': '1'},
        },
    },
    timeout=5,
)
print('MCP initialize HTTP status:', response.status_code)
PY
```

정상 서버는 이 초기화 요청에 HTTP `200`을 반환합니다. 연결 거부가 나면 서버 IP·포트·실행 상태를 확인합니다. 인증이 통과한 뒤 게이트웨이 로그에 `refreshed upstream=echo tools=1`이 기록되어야 ChatGPT에 새 도구를 노출할 수 있습니다.
