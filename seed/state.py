"""GameState: the single mutable object that holds all game data.

Reset behaviour is declared once, in RESET_SCOPE, and `engine.prestige` reads that
table instead of hand-clearing fields.  Hand-clearing is exactly how "a value that
should have persisted got wiped" bugs happen, and it is untestable; a table is not.
"""

from __future__ import annotations

import random
import time
import zlib
from typing import Any

from . import gamedata as G
from .bignum import N, Num, ZERO

# Which prestige layer wipes which field.
RESET_SCOPE: dict[str, str] = {
    "res": G.RUN,
    "run_life": G.RUN,
    "gens": G.RUN,
    "bought": G.RUN,
    "unlocked": G.RUN,
    "upgrades": G.RUN,
    "events": G.RUN,
    "probes": G.RUN,
    "run_start": G.RUN,
    "run_peak_alloy_rate": G.RUN,
    "research": G.LAYER,
    # NOTE: `auto` is deliberately PERMANENT. It holds player preferences, not
    # progress -- the capability itself is gated by flags from the Seed Grid and
    # Research, so a toggle left on while its unlock is gone simply does nothing.
    # Wiping preferences on Convergence silently switched every automation off
    # while the UI still showed the boxes ticked.
    "p1_sp": G.LAYER,
    "p1_levels": G.LAYER,
    "p1_sp_life": G.LAYER,     # drives the Convergence bar, so it resets with it
    "doctrines": G.LAYER,      # re-picked from scratch every Convergence
    # everything not listed is PERMANENT
}

_NUM_DICTS = ("res", "run_life", "total_life", "gens", "bought")
_SET_FIELDS = ("upgrades", "research", "milestones", "achievements",
               "perm_flags", "unlocked")


def _default_stats() -> dict[str, Any]:
    return {
        "playtime": 0.0,
        "sessions": 0,
        "gens_bought": 0,
        "upgrades_bought": 0,
        "research_bought": 0,
        "dispersals": 0,
        "probes_sent": 0,
        "artifacts_found": 0,
        "artifacts_by_rarity": {},
        "anomalies_seen": 0,
        "best_sp_gain": "0",
        "best_alloy_rate": "0",
        "best_run_alloy": "0",
        "fastest_million_alloy": 0.0,
        "last_played": 0.0,
    }


def _default_settings() -> dict[str, Any]:
    return {
        "buy_amount": "1",
        "confirm_prestige": True,
        "scientific": False,
        "autosave": True,
    }


def _default_auto() -> dict[str, Any]:
    return {
        "enabled": False,
        "gens": {},          # gen id -> bool
        "reserve": {},       # resource id -> absolute amount auto-buy may not touch
        "research": False,
        "upgrades": False,
        "relics": False,
        "seed": False,
        "expedition": False,
        "balance": False,
        "prestige_enabled": False,
        "prestige_threshold": 2.0,
    }


class GameState:
    def __init__(self):
        self.version: int = G.SAVE_VERSION
        self.res: dict[str, Num] = {r.id: ZERO for r in G.RESOURCES}
        self.run_life: dict[str, Num] = {r.id: ZERO for r in G.RESOURCES}
        self.total_life: dict[str, Num] = {r.id: ZERO for r in G.RESOURCES}
        # `gens` is total units (drives production); `bought` is units actually
        # purchased (drives cost and the per-10 bonus).  Splitting them is what
        # stops free units from replication causing a runaway multiplier.
        self.gens: dict[str, Num] = {g.id: ZERO for g in G.GENERATORS}
        self.bought: dict[str, Num] = {g.id: ZERO for g in G.GENERATORS}
        self.unlocked: set[str] = set()

        self.upgrades: set[str] = set()
        self.research: set[str] = set()
        self.milestones: set[str] = set()
        self.achievements: set[str] = set()
        self.perm_flags: set[str] = set()

        self.artifacts: list[dict] = []
        self.equipped: list[str] = []

        self.events: list[dict] = []
        self.probes: list[dict] = []

        self.auto: dict[str, Any] = _default_auto()

        self.p1_sp: Num = ZERO
        self.p1_sp_life: Num = ZERO
        self.p1_levels: dict[str, int] = {}
        self.p1_count: int = 0
        # -- Convergence (layer 2) --------------------------------------
        self.p2_coh: Num = ZERO
        self.p2_coh_life: Num = ZERO
        self.p2_levels: dict[str, int] = {}
        self.p2_count: int = 0
        self.doctrines: dict[int, str] = {}     # row -> chosen doctrine id

        # Later layers are declared now so saves and resets already know them.
        self.p3: dict[str, Any] = {"currency": "0", "count": 0, "unlocked": False}
        self.p4: dict[str, Any] = {"currency": "0", "count": 0, "unlocked": False}
        self.p5: dict[str, Any] = {"currency": "0", "count": 0, "unlocked": False}

        self.stats: dict[str, Any] = _default_stats()
        self.settings: dict[str, Any] = _default_settings()

        self.rng_seed: int = 0
        self.pity: int = 0
        self.next_event_in: float = 45.0
        self.run_start: float = 0.0
        self.run_peak_alloy_rate: Num = ZERO

        # ---- derived, never saved -------------------------------------
        self.flags: dict[str, bool] = {}
        self.mults: dict[str, Num] = {}
        self.breakdown: dict[str, list[tuple[str, float]]] = {}
        self.rates: dict[str, Num] = {}
        self.throttle: float = 1.0
        self.upkeep_eff: dict[str, float] = {}
        self.energy_supply: Num = ZERO
        self.energy_demand: Num = ZERO
        self.notices: list[tuple[str, str]] = []
        self.dirty: bool = True

    # -- helpers ---------------------------------------------------------
    def gen(self, gid: str) -> Num:
        return self.gens.get(gid, ZERO)

    def has_flag(self, name: str) -> bool:
        return bool(self.flags.get(name)) or name in self.perm_flags

    def notice(self, kind: str, text: str) -> None:
        self.notices.append((kind, text))

    def run_time(self) -> float:
        return max(0.0, time.time() - self.run_start) if self.run_start else 0.0

    # -- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "version": G.SAVE_VERSION,
            "artifacts": self.artifacts,
            "equipped": self.equipped,
            "events": self.events,
            "probes": self.probes,
            "auto": self.auto,
            "p1_sp": self.p1_sp.to_json(),
            "p1_sp_life": self.p1_sp_life.to_json(),
            "p1_levels": self.p1_levels,
            "p1_count": self.p1_count,
            "p2_coh": self.p2_coh.to_json(),
            "p2_coh_life": self.p2_coh_life.to_json(),
            "p2_levels": self.p2_levels,
            "p2_count": self.p2_count,
            "doctrines": {str(k): v for k, v in self.doctrines.items()},
            "p3": self.p3, "p4": self.p4, "p5": self.p5,
            "stats": self.stats,
            "settings": self.settings,
            "rng_seed": self.rng_seed,
            "pity": self.pity,
            "next_event_in": self.next_event_in,
            "run_elapsed": self.run_time(),
            "run_peak_alloy_rate": self.run_peak_alloy_rate.to_json(),
        }
        for name in _NUM_DICTS:
            d[name] = {k: v.to_json() for k, v in getattr(self, name).items()}
        for name in _SET_FIELDS:
            d[name] = sorted(getattr(self, name))
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        s = cls()
        if not isinstance(d, dict):
            return s
        for name in _NUM_DICTS:
            raw = d.get(name) or {}
            target = getattr(s, name)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k in target:          # silently drop content removed since
                        target[k] = Num.from_json(v)
        for name in _SET_FIELDS:
            raw = d.get(name) or []
            if isinstance(raw, list):
                setattr(s, name, {str(x) for x in raw})

        s.artifacts = [a for a in (d.get("artifacts") or []) if isinstance(a, dict)]
        known = {a.get("id") for a in s.artifacts}
        s.equipped = [x for x in (d.get("equipped") or []) if x in known]
        s.events = [e for e in (d.get("events") or []) if isinstance(e, dict)]
        s.probes = [p for p in (d.get("probes") or []) if isinstance(p, dict)]

        auto = _default_auto()
        if isinstance(d.get("auto"), dict):
            auto.update(d["auto"])
        s.auto = auto

        s.p1_sp = Num.from_json(d.get("p1_sp"))
        s.p1_sp_life = Num.from_json(d.get("p1_sp_life"))
        s.p1_levels = {k: int(v) for k, v in (d.get("p1_levels") or {}).items()
                       if k in G.SEED_BY_ID}
        s.p1_count = int(d.get("p1_count") or 0)
        s.p2_coh = Num.from_json(d.get("p2_coh"))
        s.p2_coh_life = Num.from_json(d.get("p2_coh_life"))
        s.p2_levels = {k: int(v) for k, v in (d.get("p2_levels") or {}).items()
                       if k in G.COH_BY_ID}
        s.p2_count = int(d.get("p2_count") or 0)
        s.doctrines = {int(k): v for k, v in (d.get("doctrines") or {}).items()
                       if v in G.DOCTRINE_BY_ID}
        for layer in ("p3", "p4", "p5"):
            if isinstance(d.get(layer), dict):
                getattr(s, layer).update(d[layer])

        stats = _default_stats()
        if isinstance(d.get("stats"), dict):
            stats.update(d["stats"])
        s.stats = stats
        settings = _default_settings()
        if isinstance(d.get("settings"), dict):
            settings.update(d["settings"])
        s.settings = settings

        s.rng_seed = int(d.get("rng_seed") or 0)
        s.pity = int(d.get("pity") or 0)
        s.next_event_in = float(d.get("next_event_in") or 45.0)
        s.run_peak_alloy_rate = Num.from_json(d.get("run_peak_alloy_rate"))
        # Elapsed run time is restored as a duration, never as wall-clock credit:
        # there is no offline progress in this game.
        s.run_start = time.time() - float(d.get("run_elapsed") or 0.0)
        return s


def seed_from_text(text: str = "") -> int:
    """Turn a player-supplied world seed into an RNG seed.

    Blank means "give me my own": every download gets a different world.  A
    number is used as given, and any other text is hashed stably, so two people
    who type the same words get the same luck.
    """
    text = (text or "").strip()
    if not text:
        return random.randrange(1, 2**31)
    if text.isdigit():
        return int(text) % (2**31) or 1
    return zlib.crc32(text.encode("utf-8")) % (2**31) or 1


def new_game(seed_text: str = "") -> GameState:
    s = GameState()
    s.run_start = time.time()
    s.res["ore"] = N(G.START_ORE)
    s.rng_seed = seed_from_text(seed_text)
    return s
