"""Read-only Garmin Connect access."""

import logging
import sys
import time

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from app.config import Config


LOG = logging.getLogger(__name__)


class MFARequired(Exception):
    """Interactive MFA is required but unavailable."""


class GarminAuthError(RuntimeError):
    """Authentication or cached token was rejected."""


class GarminRateLimitError(RuntimeError):
    """Garmin requests were rate limited."""


class GarminConnectionError(RuntimeError):
    """Garmin could not be reached."""


def _prompt_mfa() -> str:
    if not sys.stdin.isatty():
        raise MFARequired("MFA code required. Run interactively once to authenticate.")
    return input("Garmin MFA code: ").strip()


def _retry(call, *args, **kwargs):
    for attempt in range(3):
        try:
            return call(*args, **kwargs)
        except GarminConnectTooManyRequestsError:
            if attempt == 2:
                raise
            LOG.warning("Garmin rate limit; retrying request (%s/2)", attempt + 1)
        except GarminConnectConnectionError as exc:
            # The library wraps both network failures and HTTP API errors.
            message = str(exc)
            retryable = not any(f"{code}" in message for code in ("400", "401", "403", "404"))
            if not retryable or attempt == 2:
                raise
            LOG.warning("Transient Garmin connection error; retrying (%s/2)", attempt + 1)
        time.sleep(2 ** attempt)


class GarminReader:
    def __init__(self, config: Config):
        self.config = config
        self.client = Garmin(config.email or None, config.password or None, prompt_mfa=_prompt_mfa)

    def login(self) -> None:
        if not self.config.token_exists and not (self.config.email and self.config.password):
            raise ValueError("Set GARMIN_EMAIL and GARMIN_PASSWORD in .env for first login")
        self.config.token_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            # The library already tries several login strategies. Repeating the
            # whole flow on a DNS outage can trigger avoidable rate limits.
            self.client.login(str(self.config.token_dir))
        except GarminConnectAuthenticationError as exc:
            raise GarminAuthError("Garmin authentication failed. Check credentials or renew the token interactively.") from exc
        except GarminConnectTooManyRequestsError as exc:
            raise GarminRateLimitError("Garmin rate limit reached. Retry later.") from exc
        except GarminConnectConnectionError as exc:
            raise GarminConnectionError("Garmin connection failed. Check network and DNS, then retry.") from exc
        LOG.info("Garmin authentication succeeded")

    def recent(self, limit: int) -> list[dict]:
        return _retry(self.client.get_activities, start=0, limit=limit)

    def date_range(self, start: str, end: str) -> list[dict]:
        return _retry(self.client.get_activities_by_date, start, end)

    def activity_types(self) -> list[dict]:
        return _retry(self.client.get_activity_types)

    def activity(self, activity_id: int) -> dict:
        return _retry(self.client.get_activity, activity_id)

    def details(self, activity_id: int) -> dict:
        try:
            return _retry(self.client.get_activity_details, activity_id, maxchart=100000)
        except GarminConnectNotFoundError:
            LOG.info("No time series details for activity %s", activity_id)
            return {}
        except GarminConnectConnectionError as exc:
            if "404" not in str(exc):
                raise
            LOG.info("No time series details for activity %s", activity_id)
            return {}

    def laps(self, activity_id: int):
        try:
            return _retry(self.client.get_activity_laps, activity_id)
        except GarminConnectNotFoundError:
            LOG.info("No laps for activity %s", activity_id)
            return {}
        except GarminConnectConnectionError as exc:
            if "404" not in str(exc):
                raise
            LOG.info("No laps for activity %s", activity_id)
            return {}

    def heart_rate_zones(self, activity_id: int):
        try:
            return _retry(self.client.get_activity_hr_in_timezones, activity_id)
        except GarminConnectNotFoundError:
            return None
        except GarminConnectConnectionError as exc:
            if "404" not in str(exc):
                raise
            return None
