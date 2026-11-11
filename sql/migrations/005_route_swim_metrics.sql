-- Additive fields. Existing samples and activity rows are preserved.
ALTER TABLE garmin_samples ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE garmin_samples ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
ALTER TABLE garmin_activities ADD COLUMN IF NOT EXISTS pool_length_m DOUBLE PRECISION;
ALTER TABLE garmin_activities ADD COLUMN IF NOT EXISTS average_swolf DOUBLE PRECISION;
ALTER TABLE garmin_activities ADD COLUMN IF NOT EXISTS total_strokes DOUBLE PRECISION;
ALTER TABLE garmin_laps ADD COLUMN IF NOT EXISTS swolf DOUBLE PRECISION;
ALTER TABLE garmin_laps ADD COLUMN IF NOT EXISTS stroke_count DOUBLE PRECISION;
ALTER TABLE garmin_laps ADD COLUMN IF NOT EXISTS stroke_type TEXT;
