ALTER TABLE garmin_activities ADD COLUMN IF NOT EXISTS sport_group TEXT;
ALTER TABLE garmin_activities ADD COLUMN IF NOT EXISTS average_pace_s_per_100m DOUBLE PRECISION;
ALTER TABLE garmin_laps ADD COLUMN IF NOT EXISTS average_pace_s_per_100m DOUBLE PRECISION;
UPDATE garmin_activities SET sport_group = 'running' WHERE sport_group IS NULL;
COMMENT ON COLUMN garmin_activities.sport_group IS 'running, cycling, swimming 또는 multisport';
COMMENT ON COLUMN garmin_activities.average_pace_s_per_100m IS '수영 평균 속도(m/s)에서 계산한 초/100m';
COMMENT ON COLUMN garmin_laps.average_pace_s_per_100m IS '수영 랩 평균 속도(m/s)에서 계산한 초/100m';
