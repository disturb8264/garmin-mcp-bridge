"""Map observed Garmin response keys to database rows."""

from datetime import datetime, timezone

def pick(data: dict, *keys):
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def pace_seconds(speed_mps, meters: int):
    if not isinstance(speed_mps, (int, float)) or speed_mps <= 0:
        return None
    return meters / speed_mps


def pace_seconds_per_km(speed_mps):
    return pace_seconds(speed_mps, 1000)


SPORT_ROOTS = {"running": "running", "cycling": "cycling",
               "swimming": "swimming", "multi_sport": "multisport"}


def sport_groups(activity_types: list[dict]) -> dict[str, str]:
    """Resolve Garmin's type hierarchy so newly added subtypes inherit their sport."""
    by_id = {entry.get("typeId"): entry for entry in activity_types}
    groups = dict(SPORT_ROOTS)
    for entry in activity_types:
        key = entry.get("typeKey")
        current = entry
        seen = set()
        while current and current.get("typeId") not in seen:
            if current.get("typeKey") in SPORT_ROOTS:
                groups[key] = SPORT_ROOTS[current["typeKey"]]
                break
            seen.add(current.get("typeId"))
            current = by_id.get(current.get("parentTypeId"))
    return groups


def classify_activity(summary: dict, groups: dict[str, str]) -> str | None:
    activity_type = summary.get("activityType") or summary.get("activityTypeDTO") or {}
    key = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
    return groups.get(key)


def parse_dt(value, assume_utc: bool = False):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    if isinstance(value, datetime):
        return value
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if assume_utc and result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result


def activity_row(summary: dict, activity: dict, zones, details: dict | None = None,
                 sport_group: str = "running") -> dict:
    dto = activity.get("summaryDTO") or {}
    combined = {**summary, **dto}
    activity_type = activity.get("activityTypeDTO") or summary.get("activityType") or {}
    return {
        "activity_id": int(summary["activityId"]),
        "name": pick(activity, "activityName") or pick(summary, "activityName"),
        "activity_type": activity_type.get("typeKey") if isinstance(activity_type, dict) else None,
        "sport_group": sport_group,
        "start_local": parse_dt(pick(combined, "startTimeLocal")),
        "start_utc": parse_dt(pick(combined, "startTimeGMT"), assume_utc=True),
        "distance_m": pick(combined, "distance"),
        "duration_s": pick(combined, "duration"),
        "moving_duration_s": pick(combined, "movingDuration"),
        "average_pace_s_per_km": pace_seconds_per_km(pick(combined, "averageSpeed")) if sport_group == "running" else None,
        "average_pace_s_per_100m": pace_seconds(pick(combined, "averageSpeed"), 100) if sport_group == "swimming" else None,
        "average_hr": pick(combined, "averageHR"),
        "max_hr": pick(combined, "maxHR"),
        "average_cadence": pick(combined, "averageRunCadence", "averageCadence", "averageBikeCadence"),
        "average_stride_length": pick(combined, "strideLength") if sport_group == "running" else None,
        "average_power": pick(combined, "avgPower", "averagePower"),
        "elevation_gain_m": pick(combined, "elevationGain"),
        "elevation_loss_m": pick(combined, "elevationLoss"),
        "average_speed_mps": pick(combined, "averageSpeed"),
        "max_speed_mps": pick(combined, "maxSpeed"),
        "calories": pick(combined, "calories"),
        "aerobic_te": pick(combined, "aerobicTrainingEffect"),
        "anaerobic_te": pick(combined, "anaerobicTrainingEffect"),
        "hr_zones": zones,
        "raw_json": {"listing": summary, "activity": activity, "details": details},
    }


def lap_rows(activity_id: int, response, sport_group: str = "running") -> list[dict]:
    laps = response.get("lapDTOs", []) if isinstance(response, dict) else response or []
    result = []
    for index, lap in enumerate(laps, 1):
        lap_type = pick(lap, "lapType", "lapTrigger")
        if isinstance(lap_type, dict):
            lap_type = pick(lap_type, "typeKey", "key")
        result.append({
            "activity_id": activity_id,
            "lap_number": index,
            "distance_m": pick(lap, "distance"),
            "duration_s": pick(lap, "duration"),
            "average_pace_s_per_km": pace_seconds_per_km(pick(lap, "averageSpeed")) if sport_group == "running" else None,
            "average_pace_s_per_100m": pace_seconds(pick(lap, "averageSpeed"), 100) if sport_group == "swimming" else None,
            "average_hr": pick(lap, "averageHR"),
            "max_hr": pick(lap, "maxHR"),
            "average_cadence": pick(lap, "averageRunCadence", "averageCadence", "averageBikeCadence"),
            "elevation_gain_m": pick(lap, "elevationGain"),
            "lap_type": lap_type,
            "raw_json": lap,
        })
    return result


def sample_rows(activity_id: int, details: dict) -> list[dict]:
    if not isinstance(details, dict) or not details.get("activityDetailMetrics"):
        return []
    from garminconnect import parse_activity_detail_metrics

    rows = []
    for index, sample in enumerate(parse_activity_detail_metrics(details)):
        timestamp = sample.get("directTimestamp")
        rows.append({
            "activity_id": activity_id,
            "sample_index": index,
            "timestamp_utc": parse_dt(timestamp) if timestamp is not None else None,
            "elapsed_s": pick(sample, "sumElapsedDuration", "sumDuration"),
            "heart_rate": sample.get("directHeartRate"),
            "speed_mps": sample.get("directSpeed"),
            "distance_m": sample.get("sumDistance"),
            "elevation_m": sample.get("directElevation"),
            # Running cadence is the doubled channel (steps/min), not the
            # stride-rate directRunCadence channel.
            "cadence": pick(sample, "directDoubleCadence", "directBikeCadence"),
            "power": sample.get("directPower"),
            "raw_json": sample,
        })
    return rows
