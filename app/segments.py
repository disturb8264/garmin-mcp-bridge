"""GPS-only, ordered checkpoint matching for user-defined route segments."""

from datetime import datetime
from math import asin, cos, radians, sin, sqrt


EARTH_RADIUS_M = 6371000.0
MAX_GAP_SECONDS = 120.0
MAX_SPEED_MPS = 50.0


def haversine_m(lat1, lon1, lat2, lon2):
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(min(1, sqrt(a)))


def _valid_point(point):
    lat, lon, stamp = point.get("latitude"), point.get("longitude"), point.get("timestamp_utc")
    return (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and -90 <= lat <= 90 and -180 <= lon <= 180 and isinstance(stamp, datetime))


def _inside(point, checkpoint, radius_m):
    return haversine_m(point["latitude"], point["longitude"],
                       checkpoint["latitude"], checkpoint["longitude"]) <= radius_m


def _effort(points, start_index, end_index):
    selected = points[start_index:end_index + 1]
    duration = (selected[-1]["timestamp_utc"] - selected[0]["timestamp_utc"]).total_seconds()
    if duration <= 0:
        return None
    start_distance, end_distance = selected[0].get("distance_m"), selected[-1].get("distance_m")
    gps_distance = sum(haversine_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
                       for a, b in zip(selected, selected[1:]))
    device_distance = end_distance - start_distance if isinstance(start_distance, (int, float)) and isinstance(end_distance, (int, float)) else None
    if device_distance is not None and gps_distance > 0 and 0.5 <= device_distance / gps_distance <= 2:
        distance = device_distance
        distance_basis = "device_cumulative_distance"
    else:
        distance = gps_distance
        distance_basis = "gps_point_sum"
    if distance <= 0:
        return None
    def mean(key):
        values = [point[key] for point in selected if isinstance(point.get(key), (int, float))]
        return sum(values) / len(values) if values else None
    gain = 0.0
    for a, b in zip(selected, selected[1:]):
        if isinstance(a.get("elevation_m"), (int, float)) and isinstance(b.get("elevation_m"), (int, float)):
            gain += max(0, b["elevation_m"] - a["elevation_m"])
    return {
        "started_at": selected[0]["timestamp_utc"], "ended_at": selected[-1]["timestamp_utc"],
        "duration_s": duration, "distance_m": distance, "distance_basis": distance_basis,
        "average_speed_mps": distance / duration,
        "average_pace_s_per_km": duration * 1000 / distance,
        "average_hr": mean("heart_rate"), "average_power": mean("power"),
        "elevation_gain_m": gain, "sample_count": len(selected),
    }


def match_passes(points: list[dict], checkpoints: list[dict], radius_m: float) -> list[dict]:
    """Require an observed outside-to-inside start, ordered checkpoints, and end."""
    if len(checkpoints) < 2 or not 5 <= radius_m <= 200:
        raise ValueError("Segment requires start/end checkpoints and radius 5..200 m")
    passes = []
    previous = None
    start_index = None
    next_checkpoint = 1
    for index, point in enumerate(points):
        if not _valid_point(point):
            previous = None
            start_index = None
            continue
        if previous is None:
            previous = point
            continue
        elapsed = (point["timestamp_utc"] - previous["timestamp_utc"]).total_seconds()
        jump = haversine_m(previous["latitude"], previous["longitude"],
                           point["latitude"], point["longitude"])
        if elapsed <= 0 or elapsed > MAX_GAP_SECONDS or jump / elapsed > MAX_SPEED_MPS:
            previous = point
            start_index = None
            next_checkpoint = 1
            continue
        start_entered = not _inside(previous, checkpoints[0], radius_m) and _inside(point, checkpoints[0], radius_m)
        if start_entered:
            start_index = index
            next_checkpoint = 1
        elif start_index is not None:
            target = checkpoints[next_checkpoint]
            entered = not _inside(previous, target, radius_m) and _inside(point, target, radius_m)
            if entered:
                next_checkpoint += 1
                if next_checkpoint == len(checkpoints):
                    effort = _effort(points, start_index, index)
                    if effort is not None:
                        effort["pass_number"] = len(passes) + 1
                        passes.append(effort)
                    start_index = None
                    next_checkpoint = 1
        previous = point
    return passes
