> 2026-11-11 당시 인수인계 기록입니다. 현재 구성과 외부 MCP 추가 방법은 [저장소 README](../../../README.md)와 [05 외부 MCP 추가](../../../docs/05-add-upstream-mcp.md)를 참조하세요. 아래의 `bootstrap`, `init`, 별도 Compose 파일 설명은 현재 구성에 적용되지 않습니다.

# MCP Gateway handoff

기준일: 2026-11-11 (KST). 다음 작업자는 이 문서와 `README.md`, `MCP_GATEWAY_DESIGN.md`를 함께 읽는다. 이 문서에는 토큰과 API 키의 **값**을 기록하지 않는다.

## 현재 상태

- 개발서버 `/home/disturb/projects/mcp-gateway`에서 `mcp-gateway:local` 이미지의 **단일 실행 컨테이너** `mcp-gateway`가 실행 중이다. 같은 컨테이너에서 Python 게이트웨이와 `/usr/bin/tunnel-client`를 순서대로 시작한다. Compose의 `init`은 같은 이미지를 쓰는 일회성 작업이며 실행 후 정상 종료한다.
- 게이트웨이 주소: `http://127.0.0.1:18767/mcp`. 호스트 네트워크를 쓰며 루프백에만 바인딩한다. 내부 토큰 헤더 `X-MCP-Internal-Token`이 없으면 401이다.
- 터널 클라이언트 관리 주소: `http://127.0.0.1:8080/readyz`. 기존 Garmin 터널 ID를 사용한다. `.env`의 `TUNNEL_ID`, `CONTROL_PLANE_API_KEY` 값은 출력하거나 문서에 옮기지 말 것.
- InBody MCP: `127.0.0.1:18766/mcp`, Docker 컨테이너 `inbody-mcp`. Garmin MCP: `127.0.0.1:18765/mcp`, 컨테이너 `garmin2-garmin-1`, 이미지 `disturb8264/garmin-mcp-bridge:0.3.0`. Garmin 자체 터널은 끄고 실행 중이다.
- 게이트웨이는 두 서버의 `tools/list`를 시작 시와 60초마다 읽는다. 현재 `allowed_tools: ["*"]`로 InBody 4개와 Garmin 13개, 총 17개 도구를 공개한다. 공개 이름은 `inbody_`/`garmin_` 접두사를 쓴다. InBody 수집 도구 1개와 Garmin의 읽기 전용이 아닌 도구 3개도 포함된다.
- 확인 결과: 게이트웨이 컨테이너 `healthy`, 인증된 `/health` 200, 터널 `/readyz` 200, 양쪽 `get_sync_status` 계열 조회 성공, Garmin 13개 도구의 원본 schema/annotations 보존 확인. 실제 측정값이나 운동 데이터는 검증 출력에 남기지 않았다.

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `gateway/app.py` | 인증, 하위 MCP 접속, 동적 도구 목록, 호출 중계 |
| `gateway/combined.py` | 게이트웨이가 준비된 뒤 터널을 띄우는 단일 컨테이너 실행기 |
| `gateway/combined_healthcheck.py` | 게이트웨이와 터널 ready 동시 확인 |
| `gateway/bootstrap.py` | 개발 Compose 첫 실행 때 `gateway.yaml`과 게이트웨이 토큰 생성. 기존 파일은 덮어쓰지 않음 |
| `Dockerfile` | Python 게이트웨이와 `tunnel-client:v0.0.20`을 한 이미지에 포함 |
| `docker-compose.yml` | 개발서버용 빌드·init·실행. 실행 컨테이너는 하나 |
| `docker-compose.nas.yml` | NAS용 단일 이미지·단일 서비스 예제. 빌드 및 init 없음 |
| `gateway.yaml.example` | 설정 예제. 개발서버의 `gateway.yaml`은 별도 로컬 파일 |
| `scripts/copy-upstream-tokens.sh` | 원본 InBody/Garmin 토큰을 `secrets/`로 복사 |

`gateway.yaml`, `.env`, `secrets/`는 Git과 Docker 빌드 컨텍스트에서 제외한다. 현재 `secrets/`에는 `gateway_token`, `inbody_token`, `garmin_token` 세 파일이 있다. 원본 서버 토큰은 변경하지 않았다.

## 권한과 마운트

- 개발서버의 `.env`는 mode 600, `secrets/`는 mode 700, 세 토큰 파일은 각각 mode 600, 소유 UID/GID는 1000:1000이다. 실행 컨테이너도 1000:1000이다.
- `./gateway.yaml:/app/gateway.yaml:ro`는 설정 파일, `./secrets:/app/secrets:ro`는 세 토큰을 읽기 위해 필요하다. 컨테이너 내부의 `token_file: secrets/...`는 `/app/secrets/...`로 해석된다.
- `:ro`는 **쓰기만 막는다**. 이를 빼도 호스트 파일의 읽기 권한이 생기지 않고 Docker가 bind mount 파일의 소유자나 mode를 자동으로 바꾸지 않는다. NAS에서는 `PUID`가 `secrets/`에 들어가고 토큰을 읽을 수 있게 소유자와 mode를 맞춘다. 간단한 방식은 폴더 700, 토큰 600, 토큰 소유 UID=`PUID`다. `gateway.yaml`도 컨테이너 UID에 읽기 권한이 있어야 한다. `.env`는 Compose를 실행하는 호스트 사용자에게 읽기 권한이 있어야 한다.
- 토큰이 원본 서버에서 교체되면 `scripts/copy-upstream-tokens.sh`를 다시 실행한 뒤 게이트웨이를 재시작한다. 복사본이 원본과 다르면 하위 서버 인증이 실패한다.

## 개발서버 확인 명령

```bash
cd /home/disturb/projects/mcp-gateway
docker compose ps -a
docker compose logs --tail=40 gateway
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/readyz
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "X-MCP-Internal-Token: $(cat secrets/gateway_token)" \
  http://127.0.0.1:18767/health
```

마지막 검증 시 터널 ready와 게이트웨이 health가 각각 200이었다. 로그에는 터널의 OAuth metadata discovery 경고가 보일 수 있다. 현재 서버는 OAuth 대신 터널이 주입한 내부 헤더 토큰을 사용하며, 이 경고가 있어도 `/readyz`와 MCP 초기화는 성공했다. 터널이 게이트웨이보다 먼저 떠 시작 목록 조회에 실패했던 문제는 `combined.py`의 시작 순서로 해결했다.

## NAS로 옮길 때

1. NAS CPU 아키텍처에 맞는 `mcp-gateway` **이미지 하나**를 준비한다. 현재 이미지는 개발서버에서만 빌드했으며 레지스트리에 게시하거나 NAS에 전송하지 않았다. 레지스트리 또는 `docker save`/`docker load`로 전달할 수 있다.
2. NAS 작업 디렉터리에 `docker-compose.nas.yml`, `gateway.yaml`, `.env`, `secrets/`를 준비한다. NAS Compose는 init이 없으므로 `gateway.yaml`과 `gateway_token`을 미리 준비해야 한다. 개발서버의 파일을 안전하게 복사하거나 이미지의 `python -m gateway.bootstrap`을 일회성으로 실행해 생성한다. InBody/Garmin 토큰은 **각 서버의 활성 토큰을 복사**한다. 새 토큰을 임의로 생성하면 인증되지 않는다.
3. `.env`의 `PUID`, `PGID`를 NAS 파일 소유 UID/GID에 맞춘다. `TUNNEL_ID`, `CONTROL_PLANE_API_KEY`를 설정한다. 비밀값은 명령행 인수, 채팅, 이미지에 넣지 않는다. `GATEWAY_IMAGE`를 NAS에서 사용할 이미지 태그로 지정한다.
4. `gateway.yaml`의 InBody/Garmin URL을 NAS에서 실제 접근 가능한 주소로 바꾼다. NAS 예제는 `network_mode: host`이므로 하위 서버가 NAS 호스트 루프백 포트에 게시되면 그 포트를 사용한다. 현재 개발서버의 18765/18766을 NAS의 실제 포트로 재확인해야 한다. 같은 사설 Docker 네트워크에서 서비스 이름을 사용하려면 Compose 네트워크 구성도 별도로 바꿔야 한다.
5. 동일한 `TUNNEL_ID`를 쓰는 개발서버와 NAS 터널 클라이언트를 동시에 장시간 운영하지 않는다. 전환할 때 기존 클라이언트를 멈추고 NAS의 `/readyz`와 실제 도구 호출을 확인한다. 개발서버 게이트웨이 자체를 중지할지 여부는 전환 결과에 따라 결정한다.
6. NAS에서 `docker compose -f docker-compose.nas.yml up -d` 후 컨테이너 health, `/readyz`, 양쪽 `tools/list`와 안전한 조회 호출을 검사한다. ChatGPT 연결은 Refresh 후 새 대화에서 확인한다.

## 남은 일과 주의점

- NAS 실제 파일 경로, 하위 MCP 배포 방식, 포트, Docker 네트워크, UID/GID, 이미지 아키텍처를 확인하지 않았다. NAS 배포와 이미지 게시도 아직 하지 않았다.
- 기존 ChatGPT 플러그인의 오래된 Garmin 도구 이름 `get_sync_status`는 새 게이트웨이에서 `tool_unavailable`을 반환한 적이 있다. 새 이름은 `garmin_get_sync_status`다. 사용자가 Refresh를 한 적은 있지만 Garmin 등록과 단일 이미지 전환 이후의 ChatGPT 신규 대화 호출은 다시 확인해야 한다.
- `allowed_tools: ["*"]`는 새 도구도 자동 공개한다. NAS나 ChatGPT에서 수집·DB 변경 도구까지 노출하는 것이 맞는지 검토하고, 필요하면 명시적 도구 목록으로 제한한다.
- 현재 터널 ID의 원격 이름/설명은 이전 Garmin 전용 설정일 수 있다. 필요하면 터널 메타데이터를 게이트웨이에 맞게 수정한다. 이 변경은 아직 하지 않았다.
- NAS 관리 MCP는 조사·등록하지 않았다.
