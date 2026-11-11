CREATE TABLE IF NOT EXISTS garmin_date_coverage (
    covered_date DATE PRIMARY KEY,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE garmin_date_coverage IS 'Garmin 날짜 범위를 오류 없이 전부 조회·저장했음을 나타낸다';
