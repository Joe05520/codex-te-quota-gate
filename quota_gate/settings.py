"""Shared GUI/CLI/hook settings, with canonical project-directory exclusions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .policy import Decision, decide, number
from .storage import read_snapshot

DEFAULTS = {"schemaVersion": 1, "enabled": True, "threshold_5h": 15,
            "threshold_weekly": 15, "projects": []}


def canonical_path(value):
    if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value:
        raise ValueError("project path must be a nonempty absolute path")
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("project path must be absolute")
        return path.resolve()
    except RuntimeError:
        raise ValueError("project path could not be resolved") from None


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError("settings fields must match schema version 1")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise ValueError("unsupported settings schema")
    if type(value["enabled"]) is not bool:
        raise ValueError("enabled must be boolean")
    for key in ("threshold_5h", "threshold_weekly"):
        if not number(value[key]) or not 0 <= value[key] <= 100:
            raise ValueError("thresholds must be numbers from 0 to 100")
    projects = value["projects"]
    if not isinstance(projects, list) or len(projects) > 200:
        raise ValueError("projects must be a list of at most 200 entries")
    seen = set()
    clean = deepcopy(value)
    for item in clean["projects"]:
        if not isinstance(item, dict) or set(item) != {"name", "path", "excluded"}:
            raise ValueError("project entries need name, path, excluded")
        if not isinstance(item["name"], str) or not item["name"].strip() or len(item["name"]) > 80:
            raise ValueError("project name must contain 1 to 80 characters")
        if type(item["excluded"]) is not bool:
            raise ValueError("excluded must be boolean")
        path = str(canonical_path(item["path"]))
        if path in seen:
            raise ValueError("duplicate project path")
        seen.add(path)
        item.update(path=path, name=item["name"].strip())
    return clean


def read_settings(path=None):
    return deepcopy(DEFAULTS) if path is None else validate_settings(read_snapshot(path))


def revision(settings):
    raw = json.dumps(settings, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def project_block(settings, cwd):
    if not settings["enabled"]:
        return "disabled_by_settings"
    if not cwd:
        return "project_unknown" if any(p["excluded"] for p in settings["projects"]) else None
    current = canonical_path(cwd)
    for entry in settings["projects"]:
        if entry["excluded"] and current.is_relative_to(canonical_path(entry["path"])):
            return "project_excluded"
    return None


def configured_decision(snapshot, settings, *, cwd=None, now=None, max_age=90):
    settings = validate_settings(settings)
    reason = project_block(settings, cwd)
    if reason:
        return Decision(False, reason)
    return decide(snapshot, now=now, max_age=max_age,
                  threshold_5h=settings["threshold_5h"],
                  threshold_weekly=settings["threshold_weekly"])
