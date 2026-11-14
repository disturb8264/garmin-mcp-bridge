> 2026-11-11 당시 설계 기록입니다. 현재 구성과 외부 MCP 추가 방법은 [저장소 README](../../../README.md)와 [05 외부 MCP 추가](../../../docs/05-add-upstream-mcp.md)를 참조하세요. 아래의 초기화 컨테이너 설명은 현재 구성에 적용되지 않습니다.

# MCP 게이트웨이 설계

작성 기준: 2026-11-11. 개발서버에서 InBody와 Garmin 게이트웨이 및 터널을 실행한다. 기존 서버의 데이터 처리 로직은 변경하지 않았다.

## 로컬 구현 현황 (2026-11-11)

- 개발서버의 `mcp-gateway` 컨테이너가 `127.0.0.1:18767/mcp`에서 실행 중이다. 기존 `inbody-mcp`는 그대로 유지한다.
- Compose 첫 실행 시 `gateway.yaml`과 게이트웨이 토큰을 자동 생성한다. 기존 파일은 덮어쓰지 않는다.
- 설정된 InBody 서버에서 시작 시와 60초마다 `tools/list`를 읽어 `inbody_` 접두사로 공개한다. 컨테이너를 임의 검색해 자동 등록하는 방식은 아니다. 새 서버는 설정에 ID·URL·토큰 파일을 추가해야 한다.
- 현재 `allowed_tools: ["*"]`로 원본 도구 전체를 공개한다. 여기에는 수집 도구 `sync_inbody_measurements`도 포함된다. 제한이 필요하면 원본 도구 이름 목록으로 바꿀 수 있다.
- 원본 도구의 스키마·annotations 동일성과 실제 조회 호출, 무인증 401을 확인했다.
- 게이트웨이 전용 토큰과 InBody 토큰은 서로 분리한다. Docker Compose는 InBody의 기존 토큰 파일을 읽기 전용으로 마운트한다.
- 공개 이름은 연결 호환성을 위해 `inbody_get_latest_body_composition`처럼 밑줄 규칙으로 고정했다. ChatGPT 측 연결 갱신·도구 호출 검증은 이후 작업이다.
- 개발서버의 `tunnel-client`를 기존 Garmin 터널 ID로 실행했다. 로컬 `/readyz`는 200 `ready`를 반환했고 터널 메타데이터 조회와 MCP 초기화가 성공했다. 터널 이름과 기존 ChatGPT 플러그인의 도구 목록은 여전히 Garmin 기준일 수 있으므로 ChatGPT Refresh와 실제 호출 검증이 남았다.
- 기존 Garmin ChatGPT 플러그인의 `get_sync_status` 호출이 새 게이트웨이까지 도달해 `tool_unavailable`을 반환했다. 이는 터널 경로가 살아 있고 ChatGPT에 저장된 도구 목록은 이전 Garmin 상태임을 보여준다. InBody 도구를 쓰려면 해당 플러그인을 Refresh하거나 새 연결을 만들어야 한다.
- Garmin MCP `127.0.0.1:18765/mcp`를 두 번째 하위 서버로 등록했다. Garmin 13개와 InBody 4개, 총 17개 도구를 공개한다. Garmin 스키마·annotations 보존과 양쪽 상태 조회 호출을 확인했다.
- 터널이 게이트웨이 초기화 전에 시작하면 시작 목록 조회가 실패해 `/readyz`가 503이 됐다. 게이트웨이 healthcheck 통과 후 터널을 시작하도록 Compose 의존성을 바꿨고 `/readyz` 200을 확인했다.
- 세 토큰을 게이트웨이 프로젝트의 `secrets/` 폴더에 모으되, InBody와 Garmin 원본 토큰은 복사만 한다. 게이트웨이는 `secrets/` 한 폴더를 읽기 전용 마운트하고 터널은 `gateway_token` 파일만 읽는다. 복사 후 17개 도구와 양쪽 조회 호출 및 터널 ready를 재확인했다.
- NAS용 단일 이미지를 위해 게이트웨이 이미지에 `tunnel-client` 바이너리를 포함하고 한 컨테이너에서 두 프로세스를 실행한다. 개발서버에서도 단일 실행 컨테이너로 전환해 양쪽 연결과 `/readyz`를 확인했다. NAS Compose 예제는 소스 마운트나 빌드 없이 이 이미지를 사용한다. 비밀 파일은 이미지에 넣지 않고 NAS 호스트에서 UID/GID와 mode 600을 맞춰 읽기 전용 마운트한다.

## 목표

```text
ChatGPT → Secure MCP Tunnel → MCP 게이트웨이
                                ├─ Garmin MCP
                                ├─ InBody MCP
                                ├─ NAS 관리 MCP (등록 전 검증 필요)
                                └─ 향후 추가할 MCP
```

ChatGPT에는 게이트웨이 하나를 연결한다. 게이트웨이는 허용된 하위 서버의 도구 정의를 읽어 고유한 이름으로 공개하고, 호출을 원래 서버에 전달한다. 하위 서버의 데이터 수집, 백필, DB 접근 로직은 게이트웨이에 복사하지 않는다. OpenAI의 MCP 설명은 연결 시 서버의 도구 목록을 가져와 모델에 제공하는 흐름을 명시한다. [OpenAI MCP servers](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)

## 현재 확인된 구성

| 서버 | 현재 위치·접속 | 인증 | 상태 |
| --- | --- | --- | --- |
| Garmin MCP | NAS의 로컬 전용 HTTP 포트, `/mcp` | `X-MCP-Internal-Token` | Garmin 자체 터널이 연결된 구성. 실제 NAS 포트와 컨테이너 네트워크는 배포 환경에서 재확인 필요 |
| InBody MCP | Ubuntu `127.0.0.1:18766/mcp` | 별도 `X-MCP-Internal-Token` | Docker 실행 중. 수동 MCP 동기화와 매일 06:15 KST cron 동기화 확인 |
| NAS 관리 MCP | 미확인 | 미확인 | 서버 주소·도구·권한을 조사한 뒤 등록 |

근거는 로컬 Garmin `docker-compose.yml`·`app/mcp_server.py`, InBody `docker-compose.yml`·`inbody_mcp.py`이다. 두 서버 모두 호스트의 `127.0.0.1`에 바인딩하므로 서로 다른 호스트의 게이트웨이에서 그 주소로 바로 접근할 수 없다. 비밀 토큰은 문서나 설정 예제에 기재하지 않는다.

## 배치 결정

**운영 권장안:** 게이트웨이와 하위 MCP를 NAS의 사설 Docker 네트워크에 배치한다. Garmin은 기존 이미지·DB·백필·터널 동작을 그대로 유지한다. InBody 이미지를 NAS에도 배포하고, 스냅샷/`.env`/토큰을 권한을 유지해 옮기거나 별도 비밀 파일로 구성한다. 게이트웨이는 Docker 서비스 이름으로 하위 MCP에 접속한다. 하위 MCP 포트를 LAN에 공개할 필요가 없다. 게이트웨이와 터널 클라이언트만 같은 사설 네트워크에서 통신한다. InBody 정기 동기화는 이전 후 한 호스트에서만 실행해 중복 수집을 막는다.

이 안을 실행하기 전 NAS의 실제 Garmin 배포 방식과 Docker 네트워크를 확인해야 한다. 현재 SSH 계정은 NAS Docker 데몬 접근이 거부되고 `sudo` 비밀번호가 필요해 NAS 배포·네트워크 확인을 실행할 수 없다. 권한이 준비되기 전에는 Garmin 또는 NAS의 실행 구성을 바꾸지 않는다.

**로컬 시험안:** Ubuntu에서 게이트웨이를 실행하고 InBody에는 로컬 Docker 포트로 연결한다. Garmin에는 NAS에서 Ubuntu로 향하는 인증된 사설 경로(예: 유지·재접속되는 SSH 포트 포워드)를 만든 뒤 연결한다. 임시 포워드가 끊기면 Garmin 호출은 실패하므로 운영 배치로 간주하지 않는다. NAS의 Garmin 로컬 포트를 LAN 전체에 열어 해결하지 않는다.

## 게이트웨이 동작

1. 설정 파일에 하위 서버별 고정 ID(`garmin`, `inbody`, `nas`), 내부 URL, 토큰 **파일 경로**, 공개할 도구 allowlist를 적는다. URL과 토큰을 외부 도구 정의에 노출하지 않는다.
2. 시작 시 하위 MCP에 `initialize`와 `tools/list`를 호출한다. 원본 도구의 설명, 입력·출력 스키마, 안전성 annotations를 보존해 공개 목록을 만든다. 공개 이름과 원본 서버·도구 이름의 매핑을 저장한다.
3. 공개 이름은 `garmin.search_activities`, `inbody.get_latest_body_composition` 같은 접두사 규칙을 목표로 한다. OpenAI 연결에서 점(`.`)이 포함된 이름의 호환성을 MCP Inspector와 ChatGPT 연결 검사로 확인한다. 거부되면 `garmin_search_activities`처럼 밑줄 이름으로 **한 번 결정해 고정**한다. 같은 공개 이름의 중복은 시작 실패로 처리한다.
4. `tools/call`을 받으면 공개 이름을 정확히 조회하고 원본 이름과 인수를 해당 하위 서버에 전달한다. MCP 클라이언트 세션을 서버별로 재사용하되 끊기면 재연결한다. 결과의 text/image 등 content, structured content, `isError`를 임의로 문자열화하거나 성공으로 바꾸지 않는다.
5. 새 서버 등록·도구 변경은 주기적 재조회와 운영자 명령으로 감지한다. 검증된 새 목록을 원자적으로 교체한다. 하위 서버가 일시적으로 끊긴 경우 기존 도구 목록은 유지하되 해당 호출에는 `upstream_unavailable`을 반환한다. 시작 시 한번도 조회에 성공하지 못한 서버의 도구는 공개하지 않는다.
6. 호출 중 도구가 삭제되거나 스키마가 변경되면 이름을 다른 도구에 재배정하지 않는다. 호출은 명시적 `tool_unavailable` 오류로 끝낸다. 변경된 목록을 ChatGPT에서 다시 가져오는 절차를 따른다.

첫 버전은 **tools만 중계**한다. resources, prompts, sampling, elicitation, 서버별 UI 리소스가 필요한 하위 MCP는 별도 설계를 거쳐 추가한다. 도구 전체를 무제한 공개하면 목록 크기와 모델 선택 품질에 영향을 주므로 서버별 allowlist를 기본으로 한다. OpenAI 문서도 필요한 도구만 가져오는 `allowed_tools` 사용을 설명한다. [OpenAI MCP servers](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)

## 권한과 보안

- ChatGPT → 터널 → 게이트웨이에는 게이트웨이 전용 내부 토큰을 둔다. 터널 클라이언트가 게이트웨이에 헤더를 주입한다. 게이트웨이는 인증 없는 HTTP 요청을 401로 거부하고 호스트 포트는 `127.0.0.1`에만 바인딩한다.
- 게이트웨이 → Garmin/InBody/NAS에는 **각 서버의 별도 토큰**을 붙인다. ChatGPT나 터널에서 받은 인증 헤더를 하위 서버에 그대로 전달하지 않는다. 토큰은 `600` 파일로 읽기 전용 마운트하고 이미지·Git·로그에 넣지 않는다.
- NAS 관리 도구는 처음에 읽기 도구만 allowlist에 넣는다. 삭제·설정 변경·재시작 도구는 목적과 승인 흐름을 검토한 뒤 명시적으로 추가한다. Garmin/InBody의 쓰기·수집 도구 annotations도 원본과 동일하게 유지한다.
- 도구 인수·원본 응답·개인 측정값을 일반 로그에 남기지 않는다. 로그에는 공개 도구명, 하위 서버 ID, 지연 시간, 성공/오류 종류, 요청 ID만 기록한다. 응답 크기와 호출 시간에 상한을 둔다.
- 내부 HTTP라도 서버 간 통신이 다른 호스트를 지나면 사설 터널이나 TLS를 사용한다. 현재 InBody DB 서버는 TLS를 지원하지 않으므로 게이트웨이가 DB에 직접 접속하는 설계는 피한다.

Secure MCP Tunnel은 내부 서버로 향하는 아웃바운드 연결이다. 터널 클라이언트는 게이트웨이에 도달할 수 있는 위치에서 실행해야 하며, 현재 Garmin 터널의 설정을 바로 바꾸기보다 게이트웨이용 터널을 병행 검증한 뒤 전환한다. [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)

## 구현 파일 초안

```text
mcp-gateway/
├── README.md                 # 실행·장애 대응
├── gateway.yaml.example     # 서버 ID, URL, 도구 allowlist; 비밀값 없음
├── gateway/                  # MCP 서버, registry, upstream client, auth
├── tests/                    # 목록·호출·인증·장애 테스트
├── Dockerfile
├── docker-compose.yml
└── secrets/                  # Git 제외, 토큰 파일만 저장
```

Python MCP SDK의 설치 버전에서 동적 도구 등록·목록 변경 지원을 먼저 확인한다. 정적 데코레이터만으로 구현하지 말고, 게이트웨이의 `tools/list`가 registry의 현재 스냅샷을 반환하도록 한다. HTTP transport는 Streamable HTTP `/mcp`를 사용한다. 구현 시 SDK 버전을 고정하고 서버·클라이언트 양쪽에서 protocol 테스트를 작성한다.

## 작업 순서와 완료 기준

1. **연결 조사:** NAS Garmin의 실제 포트/네트워크/토큰 파일 위치를 값 노출 없이 확인한다. NAS 관리 MCP의 도구 목록과 권한을 조사한다. 게이트웨이 호스트를 확정한다.
2. **로컬 구현:** 모의 하위 MCP 두 개로 목록 접두사, allowlist, 중복 이름, 호출·오류 중계, schema/annotations 보존, 토큰 불일치, 연결 실패를 검증한다.
3. **실서버 연결:** Garmin 조회 도구와 InBody 조회 도구를 게이트웨이에서 호출한다. `inbody.sync_inbody_measurements`는 명시적 수집 요청에서만 호출되는지 확인한다. 기존 Garmin 도구와 수집/백필 동작은 회귀 검사한다.
4. **Docker 배포:** 비밀 파일을 제외한 이미지를 빌드하고 사설 네트워크에서 게이트웨이·터널을 실행한다. 게이트웨이 외부 포트는 루프백만 바인딩한다. 헬스체크는 하위 서버별 연결 상태와 목록 갱신 상태를 분리해 보여준다.
5. **ChatGPT 연결:** 새 게이트웨이 터널로 별도 custom MCP 연결을 만들고 안전한 조회 도구를 시험한다. 새 연결이 검증된 다음 기존 Garmin 터널·연결의 정리 여부를 결정한다. 기존 연결을 먼저 끊지 않는다.

완료 기준: 무인증 요청 401, Garmin/InBody 양쪽 `tools/list`와 조회 호출 성공, 실패 서버만 오류 처리, 토큰·개인정보 로그 미노출, 기존 Garmin 기능 정상, 새 서버 추가 후 게이트웨이 목록 갱신 및 ChatGPT에서 Refresh 후 새 도구 확인.

## ChatGPT 도구 갱신 절차

게이트웨이 내부 목록이 갱신돼도 ChatGPT에 이미 연결된 custom MCP의 메타데이터가 즉시 갱신된다고 가정하지 않는다. 게이트웨이를 배포/재시작하고 ChatGPT Plugins의 해당 연결에서 **Refresh**를 누른 뒤, 목록이 바뀌었는지 확인하고 새 대화에서 시험한다. 이는 OpenAI의 custom MCP 테스트 안내에 나온 절차다. [OpenAI Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)

Responses API의 `mcp_list_tools` 항목은 대화 문맥에 유지되면 매 턴 다시 가져오지 않는다. 따라서 API 쪽 테스트도 새 요청 문맥에서 도구 목록을 확인해야 한다. [OpenAI MCP servers](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)

## 롤백

게이트웨이 장애 시 새 ChatGPT 연결만 비활성화하고 기존 Garmin 연결을 사용한다. 기존 Garmin 서버와 터널을 유지한 상태에서 게이트웨이를 검증하므로 Garmin DB·백필·기존 MCP 이미지를 되돌릴 필요가 없다. InBody의 기존 Docker 컨테이너와 06:15 정기 동기화는 게이트웨이 도입과 독립적으로 유지한다.
