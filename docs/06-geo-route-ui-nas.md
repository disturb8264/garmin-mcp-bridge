# 06. Geo Route 이미지 뷰어: NAS 적용과 확인

기준: 2026-11-16. Gateway `disturb8264/mcp-gateway:0.4.2`, Geo Route `disturb8264/geo-route-mcp:0.3.1`.

Gateway 0.4.2는 허용된 도구의 `_meta.ui.resourceUri`가 가리키는 MCP App 리소스를 `resources/list`와 `resources/read`로 중계합니다. 개발 서버에서 **Docker Hub에 게시한 두 이미지**를 사용해 `geo_route_render_route`의 메타데이터, `text/html;profile=mcp-app` HTML, 240×320 PNG를 Gateway 경유로 확인했습니다. NAS의 터널과 ChatGPT 화면은 아직 검증하지 않았습니다.

## 1. NAS 배치 조건

- 게시된 두 이미지는 Linux `amd64`입니다. NAS CPU가 `x86_64`인지 확인합니다.
- Gateway가 호스트 네트워크로 실행되고 Geo Route가 같은 NAS의 호스트 포트 `127.0.0.1:18768`에 게시된 경우에만 아래 URL을 그대로 사용합니다. 개발 서버의 Geo Route는 개발 서버 자신의 `127.0.0.1`에만 게시되어 있으므로 NAS에서 그 주소로 접근할 수 없습니다.
- Geo Route 토큰 원본을 Gateway의 `secrets/geo_route_token`에 **같은 값**으로 복사합니다. 파일은 컨테이너 실행 UID가 읽을 수 있어야 하고 mode `600`을 유지합니다. 토큰 값은 명령 인수·로그·Wiki에 넣지 않습니다.
- 기존 Garmin·InBody·Echo 항목과 그 토큰 파일은 유지합니다.

같은 NAS 호스트에서 실행할 때 Gateway의 `gateway.yaml`에 아래 항목을 추가합니다. `upstreams:` 아래의 다른 항목과 같은 들여쓰기를 사용합니다.

```yaml
  - id: geo_route
    url: http://127.0.0.1:18768/mcp
    token_file: secrets/geo_route_token
    allowed_tools: ["*"]
```

Geo Route가 **다른 서버**에서 실행된다면 그 서버가 실제 수신하는 HTTPS 주소를 사용합니다. 사설망 IPv4 HTTP 주소를 쓰는 경우에만 `allow_private_http: true`를 추가합니다. 원격 서버의 포트가 루프백에만 바인딩됐다면 NAS에서 연결할 수 없습니다.

## 2. 적용 순서

1. Geo Route `0.3.1`이 NAS Gateway에서 접근 가능한 `/mcp` 주소로 실행 중인지 확인합니다.
2. Gateway `0.4.2` 이미지를 내려받아 **기존 Gateway 컨테이너를 새 이미지로 재생성**합니다. 재시작만으로는 이미지 코드가 교체되지 않습니다. 기존 `gateway.yaml`, `secrets/`, 터널 환경변수와 호스트 네트워크 설정을 유지합니다.
3. Gateway 로그에서 `refreshed upstream=geo_route tools=5`를 확인합니다. 이 로그는 도구 발견을 뜻하며 UI 리소스 조회 성공의 단독 증거는 아닙니다.
4. Gateway MCP에서 아래 검사를 실행합니다. 도구 메타데이터, 리소스 목록·읽기와 PNG 호출이 모두 통과해야 합니다.
5. 터널 `/readyz`를 확인한 뒤 ChatGPT의 Gateway 연결을 **Refresh**하고 새 대화에서 `geo_route_render_route`를 시험합니다. 화면에 그림이 표시되는지는 이 단계에서만 확정할 수 있습니다.

아래 검사는 NAS의 Gateway 컨테이너 터미널에서 실행합니다. 별도의 컨테이너 이름이나 호스트 토큰 경로를 명령에 적지 않습니다.

```sh
python - <<'PY'
import asyncio
import base64
from pathlib import Path

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client


async def main():
    token = Path('/app/secrets/gateway_token').read_text().strip()
    async with httpx.AsyncClient(headers={'X-MCP-Internal-Token': token}, trust_env=False) as client:
        async with streamable_http_client('http://127.0.0.1:18767/mcp', http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool = next(t for t in tools.tools if t.name == 'geo_route_render_route')
                uri = tool.meta['ui']['resourceUri']
                assert uri == 'ui://geo-route/route-viewer-v1.html'
                resources = await session.list_resources()
                resource = next(r for r in resources.resources if str(r.uri) == uri)
                assert resource.mime_type == 'text/html;profile=mcp-app'
                read = await session.read_resource(uri)
                assert read.contents and '<html' in read.contents[0].text.lower()
                result = await session.call_tool('geo_route_render_route', {
                    'source': {'format': 'coordinates', 'content': [[37.5, 127.0], [37.6, 127.1]],
                               'coordinate_order': 'lat_lon'},
                    'provider': 'none', 'width': 240, 'height': 320,
                })
                assert not result.is_error and isinstance(result.content[0], types.ImageContent)
                assert result.content[0].mime_type == 'image/png'
                assert base64.b64decode(result.content[0].data).startswith(b'\x89PNG')
                print('Gateway UI resource and PNG: OK')


asyncio.run(main())
PY
```

## 문제가 남을 때

| 증상 | 먼저 확인할 곳 |
| --- | --- |
| `geo_route_render_route`가 없음 | Gateway의 실제 이미지 태그, `gateway.yaml`의 URL·토큰·`allowed_tools`, `refreshed upstream=geo_route` 로그 |
| 도구는 있지만 리소스가 없음 | Gateway가 `0.4.2`로 **재생성**됐는지와 Geo Route가 `0.3.1`인지 확인 |
| PNG 호출이 `upstream_unavailable` | Geo Route 연결·인증·서버 로그 확인 |
| 위 검사는 통과하지만 ChatGPT 화면이 비어 있음 | Gateway 연결 Refresh 후 새 대화에서 재시험. 도구 결과와 ChatGPT UI 로딩 오류·터널 `/readyz` 확인 |

OpenAI는 UI 도구에 `_meta.ui.resourceUri`와 등록된 `text/html;profile=mcp-app` 리소스를 요구하며, UI 리소스가 바뀌면 ChatGPT 연결 Refresh와 새 대화 테스트를 안내합니다. [OpenAI UI 안내](https://developers.openai.com/plugins/build/chatgpt-ui), [연결과 테스트](https://developers.openai.com/plugins/deploy/connect-chatgpt), [문제 해결](https://developers.openai.com/plugins/deploy/troubleshooting).
