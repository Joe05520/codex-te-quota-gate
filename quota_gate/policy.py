"""Pure, conservative quota policy: unknown means inactive."""
from dataclasses import asdict, dataclass
import math
import time


def number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


@dataclass(frozen=True)
class Decision:
    active: bool
    reason: str
    remaining_5h: float | None = None
    remaining_weekly: float | None = None

    def as_dict(self):
        return asdict(self)


def normalize(result, *, now=None, limit_id="codex"):
    """Select one billing bucket; strip credentials and unrelated account fields."""
    now = time.time() if now is None else now
    if not isinstance(result, dict):
        raise ValueError("rate-limit response must be an object")
    if "result" in result:
        result = result["result"]
    if not isinstance(result, dict):
        raise ValueError("invalid RPC result")
    if "rateLimitsByLimitId" in result and result["rateLimitsByLimitId"] is not None:
        buckets = result["rateLimitsByLimitId"]
        bucket = buckets.get(limit_id) if isinstance(buckets, dict) else None
    else:
        bucket = result.get("rateLimits")
        if not isinstance(bucket, dict) or bucket.get("limitId") != limit_id:
            bucket = None
    if not isinstance(bucket, dict):
        raise ValueError("requested billing bucket unavailable")
    windows = []
    for name in ("primary", "secondary"):
        w = bucket.get(name)
        if isinstance(w, dict):
            windows.append({k: w.get(k) for k in
                            ("windowDurationMins", "usedPercent", "resetsAt")})
    return {"schemaVersion": 1, "observedAt": now, "limitId": limit_id,
            "windows": windows}


def decide(snapshot, *, now=None, threshold=15.0, max_age=90.0, limit_id="codex"):
    now = time.time() if now is None else now
    if not number(threshold) or not 0 < threshold <= 100:
        raise ValueError("threshold must be in (0, 100]")
    if not number(max_age) or max_age <= 0:
        raise ValueError("max_age must be positive")
    if (not isinstance(snapshot, dict) or type(snapshot.get("schemaVersion")) is not int
            or snapshot.get("schemaVersion") != 1):
        return Decision(False, "invalid_snapshot")
    if snapshot.get("limitId") != limit_id:
        return Decision(False, "wrong_bucket")
    stamp = snapshot.get("observedAt")
    if not number(stamp) or not number(now) or stamp > now:
        return Decision(False, "invalid_timestamp")
    if now - stamp >= max_age:
        return Decision(False, "stale_snapshot")
    windows = snapshot.get("windows")
    if not isinstance(windows, list):
        return Decision(False, "invalid_windows")
    remaining = {}
    for w in windows:
        if not isinstance(w, dict):
            return Decision(False, "invalid_window")
        duration = w.get("windowDurationMins")
        if not number(duration) or duration <= 0:
            return Decision(False, "invalid_window")
        if duration not in (300, 10080):
            continue
        if duration in remaining:
            return Decision(False, "duplicate_window")
        used, reset = w.get("usedPercent"), w.get("resetsAt")
        if not number(used) or not 0 <= used <= 100 or not number(reset):
            return Decision(False, "invalid_window")
        if reset <= now:
            return Decision(False, "reset_requires_refresh")
        remaining[duration] = 100.0 - used
    if set(remaining) != {300, 10080}:
        return Decision(False, "missing_5h_or_weekly")
    active = min(remaining.values()) < threshold
    return Decision(active, "below_threshold" if active else "quota_sufficient",
                    remaining[300], remaining[10080])
