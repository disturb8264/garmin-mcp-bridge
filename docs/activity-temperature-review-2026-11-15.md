# Garmin 활동 온도 데이터 조사 — 2026-11-15

## 현재 확인된 데이터

- 운영 DB 조회 당시 `garmin_activities`는 869건이었다. `raw_json->'activity'->'summaryDTO'`에 `averageTemperature`, `minTemperature`, `maxTemperature` 값이 있는 활동은 각각 425건으로, 모두 사이클링 활동이었다. 사이클링 전체는 649건이었다.
- `garmin_laps` 4,187건 중 `raw_json`의 `averageTemperature` 값이 있는 랩은 567건이었다. 온도 값이나 계정 정보는 이 문서에 기록하지 않는다.
- 전체 시간별 샘플의 온도 키 존재 여부를 확인하려던 조회는 10초 제한으로 종료됐다. 샘플 온도는 **미확인**이다.

## 코드 경로

- `services/garmin/app/collector.py`는 활동 목록·상세·시계열·랩을 Garmin에서 읽는다.
- `services/garmin/app/models.py`의 `activity_row`, `lap_rows`, `sample_rows`는 선택한 필드를 컬럼으로 옮기면서 원본을 `raw_json`에 보존한다.
- `services/garmin/app/mcp_data.py`의 `activity_details`와 `activity_laps`는 현재 온도 값을 선택하지 않는다. 따라서 `get_activity`와 `get_activity_laps` MCP 결과에는 온도가 없다.
- 수집 대상 종목은 러닝·사이클링·수영·멀티스포츠다. 수면·스트레스·Body Battery 같은 일상 건강 데이터는 이 활동 수집기의 대상이 아니다.

## 다음에 할 일

사용자가 온도 기능은 다음에 진행하기로 했다. 활동별 평균·최저·최고 온도와 랩 평균 온도를 보여주려면 기존 `raw_json`에서 값을 선택해 `get_activity`와 필요 시 `get_activity_laps` 결과에 추가한다. 이미 저장된 활동에는 DB 마이그레이션과 재수집이 필요 없다. 값이 없는 활동은 `null`로 구분하고, 단위는 원본·Garmin 표시와 대조한 후 명시한다. 도구 설명을 갱신한 새 Garmin 이미지를 배포하면 Gateway의 도구 갱신과 ChatGPT 연결 Refresh를 확인한다. 시간별 온도 기능은 원본 샘플 존재 여부를 먼저 확인한다.
