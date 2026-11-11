-- Existing summaries are queried by sport/date and by ranked distance or duration.
-- No activity rows are changed. Applied on the next normal schema ensure.
CREATE INDEX IF NOT EXISTS idx_garmin_activities_sport_start_local
    ON garmin_activities (sport_group, start_local, activity_id);
CREATE INDEX IF NOT EXISTS idx_garmin_activities_start_local
    ON garmin_activities (start_local, activity_id);
CREATE INDEX IF NOT EXISTS idx_garmin_activities_distance
    ON garmin_activities (distance_m DESC, activity_id DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_activities_duration
    ON garmin_activities (duration_s DESC, activity_id DESC);
