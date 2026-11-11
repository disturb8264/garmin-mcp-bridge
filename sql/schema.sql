CREATE TABLE IF NOT EXISTS garmin_activities (
    activity_id BIGINT PRIMARY KEY,
    name TEXT,
    activity_type TEXT,
    sport_group TEXT,
    start_local TIMESTAMP,
    start_utc TIMESTAMPTZ,
    distance_m DOUBLE PRECISION,
    duration_s DOUBLE PRECISION,
    moving_duration_s DOUBLE PRECISION,
    average_pace_s_per_km DOUBLE PRECISION,
    average_pace_s_per_100m DOUBLE PRECISION,
    average_hr DOUBLE PRECISION,
    max_hr DOUBLE PRECISION,
    average_cadence DOUBLE PRECISION,
    average_stride_length DOUBLE PRECISION,
    average_power DOUBLE PRECISION,
    elevation_gain_m DOUBLE PRECISION,
    elevation_loss_m DOUBLE PRECISION,
    average_speed_mps DOUBLE PRECISION,
    max_speed_mps DOUBLE PRECISION,
    calories DOUBLE PRECISION,
    aerobic_te DOUBLE PRECISION,
    anaerobic_te DOUBLE PRECISION,
    hr_zones JSONB,
    raw_json JSONB NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_garmin_activities_start_utc ON garmin_activities(start_utc);
COMMENT ON TABLE garmin_activities IS 'Garmin 운동 활동 요약. activity_id로 중복을 방지한다.';
COMMENT ON COLUMN garmin_activities.activity_id IS 'Garmin Connect Activity ID';
COMMENT ON COLUMN garmin_activities.start_local IS 'Garmin이 제공한 현지 시작 시각. 시간대 정보 없음';
COMMENT ON COLUMN garmin_activities.start_utc IS 'UTC 기준 활동 시작 시각';
COMMENT ON COLUMN garmin_activities.average_pace_s_per_km IS '평균 속도(m/s)에서 계산한 초/km';
COMMENT ON COLUMN garmin_activities.average_cadence IS '종목별 평균 케이던스';
COMMENT ON COLUMN garmin_activities.raw_json IS '목록 및 상세 API의 원본 JSON';

CREATE TABLE IF NOT EXISTS garmin_laps (
    activity_id BIGINT NOT NULL REFERENCES garmin_activities(activity_id) ON DELETE CASCADE,
    lap_number INTEGER NOT NULL,
    distance_m DOUBLE PRECISION,
    duration_s DOUBLE PRECISION,
    average_pace_s_per_km DOUBLE PRECISION,
    average_pace_s_per_100m DOUBLE PRECISION,
    average_hr DOUBLE PRECISION,
    max_hr DOUBLE PRECISION,
    average_cadence DOUBLE PRECISION,
    elevation_gain_m DOUBLE PRECISION,
    lap_type TEXT,
    raw_json JSONB NOT NULL,
    PRIMARY KEY (activity_id, lap_number)
);
COMMENT ON TABLE garmin_laps IS '활동별 랩. 재수집 시 활동의 기존 랩을 교체한다.';
COMMENT ON COLUMN garmin_laps.lap_number IS '활동 내 1부터 시작하는 랩 번호';
COMMENT ON COLUMN garmin_laps.average_pace_s_per_km IS '랩 평균 속도(m/s)에서 계산한 초/km';
COMMENT ON COLUMN garmin_laps.raw_json IS 'Garmin 랩 원본 JSON';

CREATE TABLE IF NOT EXISTS garmin_samples (
    activity_id BIGINT NOT NULL REFERENCES garmin_activities(activity_id) ON DELETE CASCADE,
    sample_index INTEGER NOT NULL,
    timestamp_utc TIMESTAMPTZ,
    elapsed_s DOUBLE PRECISION,
    heart_rate DOUBLE PRECISION,
    speed_mps DOUBLE PRECISION,
    distance_m DOUBLE PRECISION,
    elevation_m DOUBLE PRECISION,
    cadence DOUBLE PRECISION,
    power DOUBLE PRECISION,
    raw_json JSONB NOT NULL,
    PRIMARY KEY (activity_id, sample_index)
);
COMMENT ON TABLE garmin_samples IS 'Garmin 원본 샘플링 간격을 유지한 활동 시계열';
COMMENT ON COLUMN garmin_samples.sample_index IS '원본 응답에서의 0부터 시작하는 샘플 순서';
COMMENT ON COLUMN garmin_samples.raw_json IS 'descriptor로 해석한 원본 샘플 JSON';

CREATE TABLE IF NOT EXISTS garmin_failed_activities (
    activity_id BIGINT PRIMARY KEY,
    summary_json JSONB NOT NULL,
    last_failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempt_count INTEGER NOT NULL DEFAULT 1
);
COMMENT ON TABLE garmin_failed_activities IS '다음 증분 실행에서 재시도할 실패 활동';
COMMENT ON COLUMN garmin_failed_activities.summary_json IS '재시도에 필요한 활동 목록 원본 JSON';

CREATE TABLE IF NOT EXISTS garmin_sync_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    found_count INTEGER NOT NULL DEFAULT 0,
    saved_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
COMMENT ON TABLE garmin_sync_history IS '수집 실행별 시작, 완료, 건수 및 실패 이력';
COMMENT ON COLUMN garmin_sync_history.status IS 'running, completed, partial 또는 failed';

CREATE TABLE IF NOT EXISTS garmin_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE garmin_schema_migrations IS '적용된 Garmin 저장 스키마 버전';

CREATE TABLE IF NOT EXISTS garmin_date_coverage (
    covered_date DATE PRIMARY KEY,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE garmin_date_coverage IS 'Garmin 날짜 범위를 오류 없이 전부 조회·저장했음을 나타낸다';
