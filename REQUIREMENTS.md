Garmin Connect 러닝 데이터 자동 수집
프로젝트 1. 프로젝트 목표 Python으로
Garmin Connect의 러닝 데이터를 자동
수집하여 PostgreSQL에 저장하는
시스템을 개발한다. 최종 운영 환경은
Synology NAS의 Docker 컨테이너이며,
초기 개발 및 테스트는 로컬 Python
가상환경 ".venv"에서 진행한다.
사용자가 Garmin 시계로 러닝을
완료하고 Garmin Connect에 동기화하면
별도의 캡처나 수동 입력 없이 데이터를
수집하는 것이 목표다. 2. 개발 원칙 -
Python 3.12 사용 - 프로젝트 루트에
".venv" 생성 - 초기 개발과 테스트는
".venv"에서 실행 - Docker는 초기
단계에서 실행하지 않음 - 추후 Docker
배포가 가능하도록 프로젝트 구조 설계
- PostgreSQL 사용 - Garmin Connect
비공식 API 라이브러리 "garminconnect"
사용 - 설정은 ".env"로 관리 -
비밀번호, 토큰 등 인증 정보는 Git에
포함하지 않음 - 기능별 모듈 분리 -
과도한 프레임워크 사용 지양 - 실행
로그 및 오류 처리 구현 - Garmin
Connect 데이터 조회만 수행하고
수정·삭제하지 않음 3. 개발 환경
가상환경 생성 및 패키지 설치:
python3.12 -m venv .venv source
.venv/bin/activate python -m pip
install --upgrade pip Windows에서는
".venv\Scripts\activate" 사용. 필요한
라이브러리는 "requirements.txt"로
관리한다. 주요 라이브러리: -
garminconnect - python-dotenv -
psycopg[binary] - 기타 필요한
최소한의 패키지 실제 라이브러리 버전
및 API 사용법은 구현 시 확인한다. 4.
Garmin Connect 인증 요구사항 1.
Garmin 계정의 이메일과 비밀번호로
로그인 2. MFA가 활성화된 계정도 지원
3. 최초 인증 성공 후 로그인 토큰을
로컬 디렉터리에 저장 4. 이후
실행에서는 저장된 토큰 재사용 5. 토큰
만료 시 갱신 시도 6. 재인증이 필요한
경우 명확한 오류 메시지 출력 7. 자동
실행 중 MFA 입력이 필요하면 무한
대기하지 않고 종료 8. 비밀번호와
토큰을 로그에 출력하지 않음 인증
정보는 ".env" 또는 안전한 환경변수로
관리한다. 토큰 저장 경로는 환경변수로
지정할 수 있어야 한다. Docker 배포 시
토큰 디렉터리를 볼륨으로 마운트할 수
있도록 설계한다. 5. 수집 대상 데이터
5.1 러닝 활동 기본 정보 - Garmin
Activity ID - 활동 이름 - 활동 유형 -
시작 일시(로컬 및 UTC) - 거리(m) - 총
소요 시간 - 이동 시간 - 평균 페이스 -
평균 심박 - 최대 심박 - 평균 케이던스
- 평균 보폭(제공되는 경우) - 평균
파워(제공되는 경우) - 누적 상승 고도
- 누적 하강 고도 - 평균 속도 - 최대
속도 - 칼로리 - 유산소 및 무산소
Training Effect - 활동 원본 JSON
API에서 제공하지 않는 값은 NULL
처리한다. 거리와 시간은 원본 단위를
보존하며, km 및 min/km 변환은 분석
단계에서 수행할 수 있도록 한다. 5.2
랩 데이터 가능하면 각 활동의 랩
정보를 수집한다. - Activity ID - Lap
번호 - 거리 - 소요 시간 - 평균 페이스
- 평균 심박 - 최대 심박 - 평균
케이던스 - 상승 고도 - 원본 JSON 자동
랩과 수동 랩을 구분할 수 있다면 해당
정보도 저장한다. 5.3 심박 및 시계열
데이터 활동 상세 API에서 제공하는
시계열 데이터를 수집한다. - Activity
ID - 경과 시간 또는 타임스탬프 - 심박
- 속도 - 거리 - 고도 - 케이던스 -
파워(지원되는 경우) 시계열 데이터는
원본 샘플링 간격을 유지한다. 불필요한
보간이나 임의의 값 생성은 하지
않는다. 활동별 시계열 데이터가
제공되지 않을 경우 오류 없이 건너뛰고
로그에 기록한다. 5.4 추가 데이터
가능한 경우 다음 데이터를 수집한다. -
심박 구간별 체류 시간 - 러닝 Training
Effect - 운동 수행 관련 지표 VO2max,
HRV, 수면 등 일일 건강 지표는 초기
구현 범위에서 제외하고 추후 확장할 수
있도록 한다. 6. PostgreSQL 저장 기존
PostgreSQL 인스턴스를 사용하며,
새로운 PostgreSQL 컨테이너를 생성하지
않는다. DB 접속 정보는 ".env"에서
관리한다. 테이블 설계 최소한 다음
테이블을 구성한다. -
"garmin_activities": 활동 기본 정보 -
"garmin_laps": 활동별 랩 정보 -
"garmin_samples": 심박 및 시계열
데이터 - "garmin_sync_history":
동기화 실행 이력 필요한 경우 테이블을
추가할 수 있다. 데이터 저장 정책 -
Activity ID를 기준으로 활동 중복 저장
방지 - 동일 활동 재수집 시 UPSERT
지원 - 랩과 시계열 데이터 재수집 시
중복 방지 - 활동 단위 트랜잭션 처리 -
수집 실패한 활동은 다음 실행에서
재시도 가능 - 원본 JSON을 JSONB
컬럼에 저장 - 활동 시작 일시 및
Activity ID에 적절한 인덱스 생성 - DB
스키마 생성용 SQL 파일 제공 -
테이블과 컬럼에 이해하기 쉬운 주석
추가 7. 데이터 수집 기능 다음 실행
모드를 지원한다. 최근 활동 조회
python -m app.main --mode recent
--limit 10 최근 활동 10개를 조회하고
러닝 활동만 수집한다. 날짜 범위 조회
python -m app.main --mode range
--start 2026-01-01 --end 2026-11-11
지정된 날짜 범위의 러닝 데이터를
수집한다. 증분 동기화 python -m
app.main --mode sync DB에 저장된
기록을 기준으로 신규 활동과 최근
수정된 활동을 수집한다. 최근 며칠간의
활동은 다시 조회하여 Garmin
Connect에서 수정된 데이터도 반영할 수
있도록 한다. 초기 구현에서는 기본
재조회 범위를 최근 7일로 설정하고
환경변수로 변경할 수 있게 한다.
미리보기 python -m app.main --mode
recent --limit 5 --dry-run DB에
저장하지 않고 조회 결과를 콘솔에
출력한다. 8. 프로젝트 구조 다음
구조를 기본으로 하되 필요하면
개선한다. garmin-collector/ ├──
.venv/ ├── .env ├── .env.example ├──
.gitignore ├── requirements.txt ├──
README.md ├── Dockerfile ├──
docker-compose.yml ├── app/ │ ├──
__init__.py │ ├── main.py │ ├──
config.py │ ├── garmin_client.py │
├── collector.py │ ├── database.py │
└── models.py ├── sql/ │ └──
schema.sql ├── data/ │ └── tokens/
├── logs/ └── tests/ ".venv", ".env",
토큰, 로그는 Git에서 제외한다. 9.
Docker 배포 준비 최종 운영 환경은
Synology NAS의 Docker다. 초기
개발에서는 Docker를 실행하지 않지만
다음 파일은 작성한다. - "Dockerfile"
- "docker-compose.yml" -
".dockerignore" Docker 요구사항 -
Python 3.12 기반 공식 이미지 사용 -
가능한 한 경량 이미지 사용 - 단일
수집 컨테이너 - 기존 외부 PostgreSQL
접속 - 인증 토큰 디렉터리 볼륨 마운트
- 로그 및 시간대 처리 - 컨테이너
재생성 시에도 인증 토큰 유지 -
환경변수 기반 설정 - 비root 사용자
실행 - 불필요한 포트 노출 금지 초기
Docker 실행은 하지 않는다. 스케줄링은
Synology 작업 스케줄러 또는 외부
cron에서 컨테이너를 주기적으로
실행하는 방식을 우선 고려한다.
애플리케이션 자체에 별도의 상주
스케줄러를 구현할 필요는 없다. 10.
오류 처리 다음 상황을 처리한다. -
Garmin 로그인 실패 - MFA 필요 - 인증
토큰 만료 - Garmin API 응답 오류 -
API 요청 제한 - 네트워크 연결 실패 -
PostgreSQL 연결 실패 - 일부 활동
데이터 누락 - 활동별 수집 실패
일시적인 네트워크 및 서버 오류는
제한된 횟수로 재시도한다. 인증 실패나
MFA 필요 상태에서는 무한 재시도하지
않는다. 11. 구현 순서 1단계: 개발
환경 1. 프로젝트 디렉터리 구성 2.
Python ".venv" 생성 3. 패키지 설치 4.
".env.example" 작성 5. Git 제외 설정
2단계: Garmin 인증 및 조회 1. Garmin
Connect 로그인 구현 2. MFA 지원 3.
토큰 저장 및 재사용 4. 최근 러닝 활동
목록 조회 5. 활동 상세 정보 조회 6.
랩 데이터 조회 7. 심박 시계열 조회 8.
콘솔 출력으로 검증 이 단계에서는 DB가
없어도 동작해야 한다. 3단계:
PostgreSQL 1. DB 스키마 작성 2. DB
연결 기능 구현 3. 활동 정보 저장 4.
랩 정보 저장 5. 시계열 저장 6. 중복
방지 및 재수집 테스트 4단계: 자동
수집 1. 증분 동기화 구현 2. 동기화
이력 기록 3. 오류 복구 및 재시도 구현
4. CLI 옵션 정리 5단계: Docker 준비
1. Dockerfile 작성 2.
docker-compose.yml 작성 3. 볼륨 및
환경변수 구성 4. Synology NAS 배포
방법 README 작성 Docker 빌드와 실제
실행은 별도 요청이 있을 때 진행한다.
12. Codex 작업 지침 - 이 문서를
기준으로 프로젝트를 구현한다. - 먼저
기존 프로젝트 파일과 실행 환경을
확인한다. - Python 3.12가 없다면
임의로 시스템 Python을 변경하지 말고
사용자에게 알린다. - ".venv"를
사용하여 개발한다. - 인증에 사용하는
라이브러리의 실제 API를 확인한다. -
존재하지 않는 Garmin API 필드나
메서드를 추측해서 구현하지 않는다. -
Garmin API 응답 필드가 불확실하면
원본 JSON을 확인한 후 매핑한다. -
최초 구현은 Garmin 인증과 러닝 조회가
성공하는 것을 우선한다. - 인증 정보가
없으면 ".env.example"을 제공하고 입력
방법을 안내한다. - PostgreSQL 접속
정보가 없더라도 Garmin 조회
기능까지는 구현한다. - 테스트 코드는
실제 Garmin 계정 없이도 Mock 데이터를
이용해 실행할 수 있도록 한다. - 주요
단계 완료 시 구현 결과와 테스트
결과를 요약한다. - 불필요한 기능이나
복잡한 아키텍처를 추가하지 않는다. -
Docker 컨테이너 실행 및 운영 환경
배포는 사용자 승인 전까지 수행하지
않는다. 13. 완료 기준 다음 조건을
만족하면 초기 개발 완료로 판단한다.
1. ".venv"에서 프로그램 실행 가능 2.
Garmin Connect 로그인 성공 3. 인증
토큰 재사용 가능 4. 최근 러닝 활동
조회 가능 5. 러닝 상세 및 랩 데이터
조회 가능 6. 가능한 경우 심박 시계열
데이터 조회 가능 7. PostgreSQL에
데이터 저장 가능 8. 동일 활동을 여러
번 수집해도 중복되지 않음 9. 증분
동기화 실행 가능 10. Docker 배포용
파일과 실행 가이드 준비 완료
최종 목표는 Garmin 러닝 데이터를 NAS의 PostgreSQL에 자동으로 축적하여 향후 러닝 훈련 분석에 활용하는 것이다.
