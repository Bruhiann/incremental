"""Atomic local save/load with a backup and a never-wipe policy.

Write order: serialize in memory -> temp file -> fsync -> re-read and parse to
verify -> rotate current main to backup -> os.replace(tmp, main).  A crash at any
point leaves either the old main or a verified new one.

There is no offline progress anywhere in this module: elapsed real time between
sessions is recorded for statistics only and never credited as production.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from . import gamedata as G
from .state import GameState, new_game

SAVE_NAME = "savegame.json"
BACKUP_NAME = "savegame_backup.json"
TEMP_NAME = "savegame.tmp"


def save_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    d = root / G.GAME_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_path() -> Path:
    return save_dir() / SAVE_NAME


def backup_path() -> Path:
    return save_dir() / BACKUP_NAME


# ---------------------------------------------------------------------------
# Migrations: version -> function that upgrades the dict in place
# ---------------------------------------------------------------------------

MIGRATIONS: dict[int, callable] = {}


def _migrate(d: dict) -> dict:
    v = int(d.get("version") or 1)
    while v < G.SAVE_VERSION:
        fn = MIGRATIONS.get(v)
        if fn is None:
            break
        d = fn(d) or d
        v += 1
        d["version"] = v
    return d


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save(state: GameState) -> bool:
    """Returns True if a verified save landed on disk."""
    try:
        state.stats["last_played"] = time.time()
        payload = json.dumps(state.to_dict(), separators=(",", ":"))
    except (TypeError, ValueError, RecursionError):
        # Serialization failed: do not touch the good save on disk.
        return False

    d = save_dir()
    tmp, main, backup = d / TEMP_NAME, d / SAVE_NAME, d / BACKUP_NAME
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "r", encoding="utf-8") as fh:
            json.load(fh)              # verify it parses before trusting it
        if main.exists():
            shutil.copy2(main, backup)
        os.replace(tmp, main)
        return True
    except (OSError, ValueError):
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _read(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def load() -> tuple[GameState, str]:
    """Returns (state, status) where status is 'loaded' | 'backup' | 'new'.

    Never wipes: a corrupt main falls back to the backup, and a corrupt backup
    falls back to a fresh game while both files are left untouched on disk.
    """
    data = _read(save_path())
    if data is not None:
        try:
            return GameState.from_dict(_migrate(data)), "loaded"
        except Exception:
            pass

    data = _read(backup_path())
    if data is not None:
        try:
            return GameState.from_dict(_migrate(data)), "backup"
        except Exception:
            pass

    return new_game(), "new"


def delete_save() -> None:
    """Only ever called behind an explicit typed confirmation in the UI."""
    for name in (SAVE_NAME, BACKUP_NAME, TEMP_NAME):
        try:
            (save_dir() / name).unlink(missing_ok=True)
        except OSError:
            pass


def export_text(state: GameState) -> str:
    import base64
    raw = json.dumps(state.to_dict(), separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def import_text(blob: str) -> GameState | None:
    import base64
    try:
        raw = base64.b64decode(blob.strip().encode("ascii"), validate=True)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return GameState.from_dict(_migrate(data))
    except Exception:
        return None
