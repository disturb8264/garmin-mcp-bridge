# Garmin 실행 파일

| 파일·폴더 | 만드는 방법 |
| --- | --- |
| `.env` | `cp services/garmin/.env.example runtime/garmin/.env` 후 Garmin 계정과 PostgreSQL 값을 입력 |
| `data/mcp_internal_token`, `data/collector_internal_token` | `bash services/garmin/scripts/create-mcp-token.sh` 실행. 기존 파일은 유지 |
| `data/tokens/` | 아래 명령으로 폴더를 만들고, 첫 Garmin 로그인 후 인증 토큰이 저장됨 |

```sh
mkdir -p runtime/garmin/data/tokens
chmod 700 runtime runtime/garmin runtime/garmin/data runtime/garmin/data/tokens
chmod 600 runtime/garmin/.env
```

첫 로그인은 [Garmin 설정 문서](../../docs/02-garmin-setup.md)의 대화형 dry-run 명령을 사용합니다. DB 자체는 이 폴더에 없으며 별도 PostgreSQL을 사용합니다. `.env`·토큰·활동 데이터는 Git에 올리지 않습니다.
