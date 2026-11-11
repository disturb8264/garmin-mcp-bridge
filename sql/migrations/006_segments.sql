CREATE TABLE IF NOT EXISTS garmin_segments (
    segment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    sport_group TEXT NOT NULL CHECK (sport_group IN ('running', 'cycling')),
    start_latitude DOUBLE PRECISION NOT NULL,
    start_longitude DOUBLE PRECISION NOT NULL,
    end_latitude DOUBLE PRECISION NOT NULL,
    end_longitude DOUBLE PRECISION NOT NULL,
    waypoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    radius_m DOUBLE PRECISION NOT NULL CHECK (radius_m BETWEEN 5 AND 200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, sport_group)
);
CREATE TABLE IF NOT EXISTS garmin_segment_scans (
    segment_id BIGINT NOT NULL REFERENCES garmin_segments(segment_id) ON DELETE CASCADE,
    activity_id BIGINT NOT NULL REFERENCES garmin_activities(activity_id) ON DELETE CASCADE,
    activity_collected_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'no_gps', 'too_large')),
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (segment_id, activity_id)
);
CREATE TABLE IF NOT EXISTS garmin_segment_efforts (
    segment_id BIGINT NOT NULL REFERENCES garmin_segments(segment_id) ON DELETE CASCADE,
    activity_id BIGINT NOT NULL REFERENCES garmin_activities(activity_id) ON DELETE CASCADE,
    pass_number INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    distance_m DOUBLE PRECISION NOT NULL,
    duration_s DOUBLE PRECISION NOT NULL,
    distance_basis TEXT NOT NULL,
    average_speed_mps DOUBLE PRECISION NOT NULL,
    average_pace_s_per_km DOUBLE PRECISION NOT NULL,
    average_hr DOUBLE PRECISION,
    average_power DOUBLE PRECISION,
    elevation_gain_m DOUBLE PRECISION,
    sample_count INTEGER NOT NULL,
    PRIMARY KEY (segment_id, activity_id, pass_number)
);
CREATE INDEX IF NOT EXISTS idx_garmin_segment_efforts_rank
    ON garmin_segment_efforts (segment_id, duration_s, activity_id);
CREATE INDEX IF NOT EXISTS idx_garmin_segment_scans_activity
    ON garmin_segment_scans (activity_id);
