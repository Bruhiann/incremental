"""Game logic: unlocks, multipliers, the tick, purchasing, RNG and prestige.

The UI computes nothing — it formats values this module has already derived, so
the headless balance simulator and the shipped game are the same economy.
"""

from __future__ import annotations

import math
import random
import time

from . import gamedata as G
from .bignum import N, Num, ZERO, ONE, fmt, fmt_time
from .state import RESET_SCOPE, GameState

MILESTONE_BY_ID = {m.id: m for m in G.MILESTONES}
ACH_BY_ID = {a.id: a for a in G.ACHIEVEMENTS}
TARGET_BY_ID = {t.id: t for t in G.TARGETS}

# Cap on a single purchase call. The maths is closed-form, so a large count
# costs no more to compute than a small one; this bound exists only so the count
# stays inside a float, since `Num.pow` takes a float exponent.
#
# It is NOT a design lever, and treating it as one has bitten twice. At 1e6 it
# throttled a player who could afford 1.2 billion. At 1e15 it did something
# worse and quieter: on a real endgame save, affordability passed the cap after
# about five minutes and machine counts went from compounding to strictly
# LINEAR -- +10 Qa every 25 seconds, forever, while the bank kept growing
# hyper-exponentially. Auto-buy looked like it had stopped working. It had not;
# it was pinned. Affordability is logarithmic in cash, so any fixed cap is
# eventually crossed: this one is set at the edge of what a float can carry
# rather than at any number that felt big at the time.
MAX_BUY = 10**300
AUTOBUY_CAP = 50             # floor on units a generator may auto-buy per tick
# ...but a flat floor is glacial once you can afford a million levels a tick, so
# the real allowance is a share of what you could buy outright. Taking a share
# rather than everything still leaves budget for the other machines this tick.
AUTOBUY_FRACTION = 0.10
AUTOSEED_CAP = 25            # Seed Grid levels bought per tick
MIN_GROWTH = 1.01


# ---------------------------------------------------------------------------
# Unlock conditions
# ---------------------------------------------------------------------------

def check(cond: G.Cond, s: GameState) -> bool:
    if cond is None:
        return True
    if cond.all_of:
        return all(check(c, s) for c in cond.all_of)
    if cond.any_of:
        return any(check(c, s) for c in cond.any_of)
    if cond.res is not None:
        pool = s.run_life if cond.lifetime else s.res
        if pool.get(cond.res, ZERO) < (cond.amount or ZERO):
            return False
    if cond.gen is not None and s.gens.get(cond.gen, ZERO) < cond.count:
        return False
    if cond.flag is not None and not s.has_flag(cond.flag):
        return False
    if cond.research is not None and cond.research not in s.research:
        return False
    if cond.upgrade is not None and cond.upgrade not in s.upgrades:
        return False
    if cond.prestige and s.p1_count < cond.prestige:
        return False
    if cond.converge and s.p2_count < cond.converge:
        return False
    if cond.overwrite and s.p3_count < cond.overwrite:
        return False
    if cond.collapse and s.p4_count < cond.collapse:
        return False
    if cond.recurse and s.p5_count < cond.recurse:
        return False
    return True


def gen_unlocked(s: GameState, gid: str) -> bool:
    """Unlocks are sticky within a run: a dip never re-hides content."""
    return gid in s.unlocked


# ---------------------------------------------------------------------------
# Effects -> multiplier buckets
# ---------------------------------------------------------------------------

class Mults:
    __slots__ = ("gen", "ladder", "res", "glob", "growth", "tenfold", "drop",
                 "sp", "slots", "start_res", "start_gen", "refine", "flags",
                 "cross", "capture", "autocat", "nanite", "coh", "exponent",
                 "oc", "sub", "keep_exponent", "keep_fleet", "soften")

    def __init__(self):
        self.gen: dict[str, Num] = {}
        self.ladder: dict[str, Num] = {}
        self.res: dict[str, Num] = {}
        self.glob: Num = ONE
        self.growth: dict[str, float] = {}
        self.tenfold: dict[str, float] = {}
        self.drop: float = 1.0
        self.sp: float = 1.0
        self.slots: dict[str, int] = {"relic": 0, "probe": 0}
        self.start_res: dict[str, float] = {}
        self.start_gen: dict[str, float] = {}
        self.refine: float = 1.0
        self.flags: dict[str, bool] = {}
        self.cross: float = 1.0
        self.capture: float = 1.0
        self.autocat: float = 1.0
        self.nanite: float = 1.0
        self.coh: float = 1.0
        self.exponent: float = 0.0
        self.oc: float = 1.0
        self.sub: float = 1.0
        self.keep_exponent: float = 0.0
        self.keep_fleet: float = 0.0
        self.soften: float = 0.0


def _apply(m: Mults, eff: G.Eff, level: int = 1) -> None:
    if level <= 0:
        return
    k, t, v = eff.kind, eff.target, eff.value
    if k == G.MULT_GEN:
        m.gen[t] = m.gen.get(t, ONE) * (Num(v) ** level)
    elif k == G.MULT_LADDER:
        m.ladder[t] = m.ladder.get(t, ONE) * (Num(v) ** level)
    elif k == G.MULT_RES:
        m.res[t] = m.res.get(t, ONE) * (Num(v) ** level)
    elif k == G.MULT_GLOBAL:
        m.glob = m.glob * (Num(v) ** level)
    elif k == G.ADD_GROWTH:
        m.growth[t] = m.growth.get(t, 0.0) + v * level
    elif k == G.TENFOLD:
        m.tenfold[t] = m.tenfold.get(t, 0.0) + v * level
    elif k == G.SET_FLAG:
        m.flags[t] = True
    elif k == G.ADD_SLOT:
        m.slots[t] = m.slots.get(t, 0) + int(v) * level
    elif k == G.MULT_DROP:
        m.drop *= v**level
    elif k == G.MULT_SP:
        m.sp *= v**level
    elif k == G.START_RES:
        m.start_res[t] = m.start_res.get(t, 1.0) * v**level
    elif k == G.START_GEN:
        m.start_gen[t] = m.start_gen.get(t, 0.0) + v * level
    elif k == G.REFINE_EFF:
        m.refine *= v**level
    elif k == G.MULT_CROSS:
        m.cross *= v**level
    elif k == G.MULT_CAPTURE:
        m.capture *= v**level
    elif k == G.MULT_AUTOCAT:
        m.autocat *= v**level
    elif k == G.MULT_NANITE:
        m.nanite *= v**level
    elif k == G.MULT_COH:
        m.coh *= v**level
    elif k == G.EXPONENT:
        m.exponent += v * level
    elif k == G.MULT_OC:
        m.oc *= v**level
    elif k == G.MULT_SUB:
        m.sub *= v**level
    elif k == G.KEEP_EXPONENT:
        m.keep_exponent += v * level
    elif k == G.KEEP_FLEET:
        m.keep_fleet += v * level
    elif k == G.SOFTEN:
        m.soften += v * level


def depth_mod(s: GameState, mod_id: str) -> bool:
    """Is this named handicap active at the depth you are standing in?"""
    depth = s.p5_active_depth
    if depth <= 0:
        return False
    mod = G.MOD_BY_ID.get(mod_id)
    return bool(mod) and depth >= mod.depth


def collect_mults(s: GameState) -> Mults:
    m = Mults()
    for uid in s.upgrades:
        u = G.UPG_BY_ID.get(uid)
        if u:
            _apply(m, u.effect)
    for tid in s.research:
        t = G.TECH_BY_ID.get(tid)
        if t:
            _apply(m, t.effect)
    for sid, lvl in s.p1_levels.items():
        su = G.SEED_BY_ID.get(sid)
        if su:
            _apply(m, su.effect, int(lvl))
    for cid, lvl in s.p2_levels.items():
        cu = G.COH_BY_ID.get(cid)
        if cu:
            _apply(m, cu.effect, int(lvl))
    for did in s.doctrines.values():
        doc = G.DOCTRINE_BY_ID.get(did)
        if doc:
            _apply(m, doc.effect)
    for mid in s.milestones:
        ms = MILESTONE_BY_ID.get(mid)
        if ms:
            _apply(m, ms.effect)
    # Dead Frame (depth 8): the Relic Frame is inert down here.
    if not depth_mod(s, "norelic"):
        for aid in s.equipped:
            art = next((a for a in s.artifacts if a.get("id") == aid), None)
            if art:
                _apply(m, G.Eff(art["kind"], art.get("target", ""), art["value"]))
    if s.achievements:
        m.glob = m.glob * (Num(G.ACH_GLOBAL_BONUS) ** len(s.achievements))
    exotics = s.res.get("exotic", ZERO)
    if exotics > 0:
        m.glob = m.glob * Num((1.0 + exotics.log10()) ** G.EXOTIC_POWER)
    for oid, lvl in s.p3_levels.items():
        ou = G.OVER_BY_ID.get(oid)
        if ou:
            _apply(m, ou.effect, int(lvl))
    for uid, lvl in s.p4_levels.items():
        su = G.SUB_BY_ID.get(uid)
        if su:
            _apply(m, su.effect, int(lvl))
    for uid, lvl in s.p5_levels.items():
        ru = G.REC_BY_ID.get(uid)
        if ru:
            _apply(m, ru.effect, int(lvl))
    # Retained Exponent is the one thing that survives a Recursion, so it is
    # added here rather than carried in state: the Lattice is gone, the floor it
    # left behind is not.
    if m.keep_exponent > 0.0:
        m.exponent += m.keep_exponent
    # -- depth handicaps -------------------------------------------------
    #
    # They hit COSTS, never the exponent. Production here is hyper-exponential;
    # a ^0.9 handicap stacked to depth 40 is ^0.015, which is not difficulty,
    # it is deletion. Cost growth is the one axis that scales smoothly and that
    # the player owns real tools against.
    depth = s.p5_active_depth
    if depth > 0:
        step = max(G.RECURSE_GROWTH_FLOOR, G.RECURSE_GROWTH_STEP - m.soften)
        m.growth["*"] = m.growth.get("*", 0.0) + step * depth
    mods = {mod.id for mod in G.active_mods(depth)}
    if "tenfold" in mods:
        # x1.05 instead of x1.10, expressed as a delta so it composes with
        # every other tenfold bonus rather than overriding them.
        m.tenfold["*"] = m.tenfold.get("*", 0.0) - 0.05
    # Every incursion turned back pays into the economy, permanently, so the
    # fleet is not a pure tax on production.  Logarithmic, like everything else
    # here that reads a count: 1,000 clears is x2.5, not x1,000.
    if s.combat_wins > 0:
        m.glob = m.glob * Num(1.0 + G.COMBAT_WIN_K * math.log10(1.0 + s.combat_wins))
    nanites = s.res.get("nanite", ZERO)
    if nanites > 0:
        # Nanite Mass compounds exponentially, so its bonus is logarithmic:
        # the number runs away, the balance does not.
        m.glob = m.glob * Num((1.0 + nanites.log10()) ** G.NANITE_POWER)
    for ev in s.events:
        an = _anomaly(ev.get("id"))
        if not an:
            continue
        for target, value in an.mults:
            if target == "*":
                m.glob = m.glob * Num(value)
            elif target in (G.EXTRACT, G.REPLICATE):
                m.ladder[target] = m.ladder.get(target, ONE) * Num(value)
            else:
                m.res[target] = m.res.get(target, ONE) * Num(value)
    return m


def _capture(count: Num, per_unit: float) -> float:
    """Fraction of an input stream captured by `count` converters.

    Asymptotic to 1.0, so converters never become worthless but also never
    capture more than exists.
    """
    if count <= 0:
        return 0.0
    n = count.to_float() if count.e < 12 else 1e12
    return 1.0 - (1.0 - per_unit) ** n


def _tenfold_steps(bought: Num) -> float:
    """How many complete tens have been purchased.

    This used to return 0 outright once `bought` reached 1e15, which silently
    switched the whole per-10 bonus off at exactly the point a player got strong
    enough to reach it. It now degrades by magnitude instead of vanishing.
    """
    if bought < 10:
        return 0.0
    tens = bought / Num(10)
    if tens.e < 15:
        return float(math.floor(tens.to_float()))
    if tens.e < 300:
        return tens.to_float()
    return 1e300            # finite, so pow() stays well defined


def _tenfold_step(g: G.Gen, m: Mults) -> float:
    return 1.0 + G.TENFOLD_BASE + m.tenfold.get(g.id, 0.0) + m.tenfold.get("*", 0.0)


def tenfold_factor(g: G.Gen, bought: Num, m: Mults) -> Num:
    """The per-10 bonus for a given purchased count.

    Split out of `recompute` so the Defection can ask what a hypothetical fleet
    would be worth.  `s.mults` already folds in the bonus for the count you own,
    so sizing an incursion against it would ratchet off your own fleet -- buy
    ships, the demand rises, buy more.
    """
    steps = _tenfold_steps(bought)
    if not steps:
        return ONE
    return Num(_tenfold_step(g, m)) ** steps


def _cross_ladder(s: GameState, tier: int, k_mult: float = 1.0) -> float:
    """Replication tiers retro-boost Extraction, lower tiers most.

    Logarithmic on purpose: a count of 1e20 contributes x4, not x1e19.  This is
    the main brake that stops machines-building-machines from detonating.
    """
    total = 1.0
    for g in G.REPLICATE_GENS:
        c = s.gens.get(g.id, ZERO)
        if c <= 0:
            continue
        magnitude = math.log10(1.0 + c.to_float()) if c.e < 300 else c.log10()
        base = 1.0 + G.CROSS_LADDER_K * k_mult * magnitude
        tilt = 1.0 + 0.15 * max(0, g.tier - tier)
        total *= base**tilt
    return total


def recompute(s: GameState) -> Mults:
    m = collect_mults(s)
    s.flags = dict(m.flags)
    if s.p1_levels.get("sg_autobuy"):
        s.flags["autobuy"] = True
    if s.p2_count > 0:
        s.flags["nanites"] = True
    if s.p3_count > 0:
        s.flags["exotics"] = True
        s.flags["see_combat"] = True
    if s.p3_oc_life >= G.P4_UNLOCK_OC or s.p4_count > 0:
        s.flags["see_substrate"] = True
    if s.p4_sub_life >= G.P5_UNLOCK_SUB or s.p5_count > 0:
        s.flags["see_recursion"] = True
    if collect_mults(s).exponent >= 0.10:
        s.perm_flags.add("ach_exponent")
    if s.p2_coh_life >= G.P3_UNLOCK_COH or s.p3_count > 0:
        s.flags["see_overwrite"] = True
    if s.p1_sp_life >= G.P2_UNLOCK_SP or s.p2_count > 0:
        s.flags["see_convergence"] = True
    if len(s.doctrines) >= len(G.DOCTRINE_ROWS):
        s.perm_flags.add("ach_doctrines")

    # sticky unlocks
    for g in G.GENERATORS:
        if g.id not in s.unlocked and check(g.unlock, s):
            s.unlocked.add(g.id)
            s.notice("unlock", f"New machine available: {g.name}")

    mults: dict[str, Num] = {}
    breakdown: dict[str, list[tuple[str, float]]] = {}
    for g in G.GENERATORS:
        parts: list[tuple[str, float]] = []
        total = m.glob
        if m.glob != ONE:
            parts.append(("Global", m.glob.to_float()))
        lad = m.ladder.get(g.ladder, ONE)
        if lad != ONE:
            total = total * lad
            parts.append(("Ladder", lad.to_float()))
        gm = m.gen.get(g.id, ONE)
        if gm != ONE:
            total = total * gm
            parts.append(("Upgrades", gm.to_float()))
        if g.produces in G.RES_BY_ID:
            rm = m.res.get(g.produces, ONE)
            if rm != ONE:
                total = total * rm
                parts.append(("Resource", rm.to_float()))
        bought = s.bought.get(g.id, ZERO)
        tf = tenfold_factor(g, bought, m)
        if tf != ONE:
            total = total * tf
            parts.append((f"Every 10 owned (x{_tenfold_step(g, m):.2f})", tf.to_float()))
        # Defence rides the cross-ladder rule too: you are fighting your own
        # machines, so the tech that builds is the tech that fights.  That is
        # what keeps neglect a gap rather than a cliff -- the fleet's ceiling
        # rises with the swarm generating the threat against it.
        if g.ladder in (G.EXTRACT, G.DEFEND):
            cl = _cross_ladder(s, g.tier, m.cross)
            if cl > 1.0:
                total = total * Num(cl)
                parts.append(("Replication", cl))
        if m.exponent > 0.0 and total > ONE:
            total = total ** (1.0 + m.exponent)
            parts.append((f"Substrate exponent (^{1.0 + m.exponent:.4f})", 0.0))
        mults[g.id] = total
        breakdown[g.id] = parts
    s.mults = mults
    s.breakdown = breakdown
    return m


# ---------------------------------------------------------------------------
# Cost and purchasing
# ---------------------------------------------------------------------------

def _levels_from_ratio(ratio_log: float, growth: float) -> int:
    """Levels affordable when you hold 10**ratio_log times the next unit's cost.

    Solves cash >= base*(g**k - 1)/(g - 1) for k.  The large branch matters: a
    float cannot hold 10**5000, and short-circuiting to MAX_BUY there was wrong
    in a way that silently broke buying entirely -- max_affordable would claim a
    million, buy() would price a million, find it unaffordable, and purchase
    nothing at all.  For a large ratio the +1 is negligible, so the whole thing
    can be done in logs.
    """
    if ratio_log < 0:
        return 0
    log_g = math.log10(growth)
    if log_g <= 0:
        return MAX_BUY
    if ratio_log > 280:
        k = (ratio_log + math.log10(growth - 1.0)) / log_g
    else:
        ratio = 10.0**ratio_log
        k = math.log(1.0 + ratio * (growth - 1.0)) / math.log(growth)
    # Guarded before the int(): math.floor(inf) raises, and a ratio_log large
    # enough to overflow the division is reachable now that the cap is at the
    # float ceiling rather than well below it.
    if not math.isfinite(k):
        return MAX_BUY
    return max(0, min(MAX_BUY, int(math.floor(k))))


def growth_of(s: GameState, g: G.Gen, m: Mults | None = None) -> float:
    m = m or recompute(s)
    delta = m.growth.get("*", 0.0) + m.growth.get(g.id, 0.0) + m.growth.get(g.ladder, 0.0)
    return max(MIN_GROWTH, g.growth + delta)


def cost_of(s: GameState, gid: str, k: int = 1, m: Mults | None = None) -> Num:
    g = G.GEN_BY_ID[gid]
    gr = growth_of(s, g, m)
    n = s.bought.get(gid, ZERO).to_float()
    if n != n or n == math.inf:
        n = 0.0
    first = g.base_cost * Num.from_exp(n * math.log10(gr))
    if k <= 1:
        return first
    return first * (Num(gr) ** k - ONE) / Num(gr - 1.0)


def max_affordable(s: GameState, gid: str, m: Mults | None = None) -> int:
    """Closed form. Never a purchase loop — that is what freezes Tkinter."""
    g = G.GEN_BY_ID[gid]
    gr = growth_of(s, g, m)
    cash = s.res.get(g.cost_res, ZERO)
    if cash <= 0:
        return 0
    first = cost_of(s, gid, 1, m)
    if first <= 0:
        return 0
    ratio_log = cash.log10() - first.log10()
    if ratio_log < -12:
        return 0
    return _levels_from_ratio(ratio_log, gr)


def buy(s: GameState, gid: str, amount, m: Mults | None = None) -> int:
    """The single mutation path for generator purchases.

    Automation calls this too — there is deliberately no second, looser path,
    because that duplication is where "bought while unaffordable" bugs live.
    """
    if gid not in s.unlocked:
        return 0
    g = G.GEN_BY_ID[gid]
    afford = max_affordable(s, gid, m)
    k = afford if amount == "max" else min(int(amount), afford)
    if k <= 0:
        return 0
    cost = cost_of(s, gid, k, m)
    cash = s.res.get(g.cost_res, ZERO)
    if cost > cash:                      # belt-and-braces against rounding
        k -= 1
        if k <= 0:
            return 0
        cost = cost_of(s, gid, k, m)
        if cost > cash:
            return 0
    s.res[g.cost_res] = (cash - cost).clamp_min(0)
    s.bought[gid] = s.bought.get(gid, ZERO) + k
    s.gens[gid] = s.gens.get(gid, ZERO) + k
    # Held as a Num: with the cap at the float ceiling this can legitimately
    # reach counts a Python int would carry as a 300-digit number in the save.
    s.stats["gens_bought"] = (
        Num.from_json(s.stats.get("gens_bought", 0)) + Num(float(k))).to_json()
    return k


def buy_upgrade(s: GameState, uid: str) -> bool:
    u = G.UPG_BY_ID.get(uid)
    if not u or uid in s.upgrades or not check(u.unlock, s):
        return False
    if s.res.get(u.cost_res, ZERO) < u.cost:
        return False
    s.res[u.cost_res] = (s.res[u.cost_res] - u.cost).clamp_min(0)
    s.upgrades.add(uid)
    s.stats["upgrades_bought"] = s.stats.get("upgrades_bought", 0) + 1
    if u.major:
        s.notice("major", f"{u.name}: {u.desc}")
    return True


def buy_research(s: GameState, tid: str) -> bool:
    t = G.TECH_BY_ID.get(tid)
    if not t or tid in s.research or not check(t.unlock, s):
        return False
    if s.res.get("data", ZERO) < t.cost:
        return False
    s.res["data"] = (s.res["data"] - t.cost).clamp_min(0)
    s.research.add(tid)
    s.stats["research_bought"] = s.stats.get("research_bought", 0) + 1
    if t.major:
        s.notice("major", f"{t.name}: {t.desc}")
    return True


FLAT = 1.0 + 1e-12          # anything at or below this has no cost growth


def bulk_cost(base: float, growth: float, level: int, k: int) -> Num:
    """Cost of buying `k` levels starting from `level`. Closed form, no loop.

    Several shop nodes are priced flat (cost_growth == 1.0), which the geometric
    series cannot express -- it divides by growth - 1 -- so that case is handled
    separately rather than left to produce a ZeroDivisionError.
    """
    first = Num(base) * (Num(growth) ** level)
    if k <= 1:
        return first
    if growth <= FLAT:
        return first * Num(k)
    return first * ((Num(growth) ** k) - ONE) / Num(growth - 1.0)


def bulk_affordable(base: float, growth: float, level: int, cash: Num) -> int:
    """How many levels `cash` buys, starting from `level`."""
    first = Num(base) * (Num(growth) ** level)
    if first <= 0 or cash < first:
        return 0
    if growth <= FLAT:
        # int(inf) raises, and a flat-priced node plus an astronomical bank
        # reaches infinity easily. Decide in log space first.
        #
        # The count still has to be one the cash actually covers: this branch
        # used to hand back MAX_BUY outright, which was harmless only because
        # MAX_BUY was small. At the float ceiling it promises 1e300 levels for
        # 1e50 of cash, and `buy` would then price them and refuse.
        ratio = cash / first
        if ratio.log10() > 300:
            return MAX_BUY
        return max(0, min(MAX_BUY, int(ratio.to_float())))
    return _levels_from_ratio(cash.log10() - first.log10(), growth)


def _remaining_levels(level: int, max_level: int) -> int:
    """Levels left before the cap. max_level 0 means endless."""
    return MAX_BUY if not max_level else max(0, max_level - level)


def seed_cost(su: G.SeedUpg, level: int, k: int = 1) -> Num:
    return bulk_cost(su.base_cost, su.cost_growth, level, k)


def seed_affordable(s: GameState, sid: str) -> int:
    su = G.SEED_BY_ID.get(sid)
    if not su:
        return 0
    level = int(s.p1_levels.get(sid, 0))
    return min(bulk_affordable(su.base_cost, su.cost_growth, level, s.p1_sp),
               _remaining_levels(level, su.max_level))


def buy_seed(s: GameState, sid: str, amount=1) -> int:
    """Single mutation path for the Seed Grid. Returns levels actually bought."""
    su = G.SEED_BY_ID.get(sid)
    if not su:
        return 0
    level = int(s.p1_levels.get(sid, 0))
    afford = seed_affordable(s, sid)
    k = afford if amount == "max" else min(int(amount), afford)
    if k <= 0:
        return 0
    cost = seed_cost(su, level, k)
    if cost > s.p1_sp:                      # belt-and-braces against rounding
        k -= 1
        if k <= 0:
            return 0
        cost = seed_cost(su, level, k)
        if cost > s.p1_sp:
            return 0
    s.p1_sp = (s.p1_sp - cost).clamp_min(0)
    s.p1_levels[sid] = level + k
    return k


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------

def tick(s: GameState, dt: float, rng: random.Random | None = None) -> None:
    dt = max(0.0, min(dt, G.MAX_DT))
    if dt <= 0:
        return
    rng = rng or _rng(s)

    _advance_events(s, dt)
    _advance_probes(s, dt, rng)
    m = recompute(s)
    _produce(s, dt, m)
    _advance_combat(s, dt, m, rng)
    _check_depth_clear(s)
    _automate(s, dt, m)
    _roll_anomaly(s, dt, rng)
    _evaluate(s)
    s.stats["playtime"] = s.stats.get("playtime", 0.0) + dt


def _produce(s: GameState, dt: float, m: Mults) -> None:
    counts = {g.id: s.gens.get(g.id, ZERO) for g in G.GENERATORS}

    # 1. Power supply and demand.  Power generators are never throttled — if
    #    they were, a shortage would be an unrecoverable death spiral.
    supply = ZERO
    for gid in G.ENERGY_GENS:
        g = G.GEN_BY_ID[gid]
        supply = supply + counts[gid] * Num(g.base_rate) * s.mults[gid]
    demand = ZERO
    draw_mult = Num(3.0) if depth_mod(s, "draw") else ONE      # Hungry Machines
    for g in G.GENERATORS:
        if g.draw:
            demand = demand + s.bought.get(g.id, ZERO) * Num(g.draw) * draw_mult
    s.energy_supply, s.energy_demand = supply, demand
    if demand <= 0:
        throttle = 1.0
    else:
        ratio = (supply / demand).to_float()
        throttle = max(G.THROTTLE_FLOOR, min(1.0, ratio))
    s.throttle = throttle
    thr = Num(throttle)

    # 2. Upkeep.  Allocate to lower tiers first so a shortage idles only the
    #    top tier — never a cascade, never destruction.
    upkeep_eff: dict[str, float] = {}
    alloy_upkeep = ZERO
    upkeepers = sorted((g for g in G.GENERATORS if g.upkeep and counts[g.id] > 0),
                       key=lambda g: g.tier)
    upkeep_mult = Num(10.0) if depth_mod(s, "upkeep") else ONE   # Starved
    needs = [(g, counts[g.id] * Num(g.upkeep[1]) * upkeep_mult) for g in upkeepers]
    total_need = ZERO
    for _, need in needs:
        total_need = total_need + need

    # 3. Raw resource rates.
    rates: dict[str, Num] = {r.id: ZERO for r in G.RESOURCES}
    for g in G.EXTRACT_GENS:
        # Any produced resource, derived from the table rather than a hardcoded
        # list -- Nanite Vats and Black Hole Taps produced literally nothing
        # while the UI happily displayed a rate for them.
        if (g.produces in G.RES_BY_ID and g.produces != "energy"
                and not g.consumes and counts[g.id] > 0):
            made = counts[g.id] * Num(g.base_rate) * s.mults[g.id] * thr
            rates[g.produces] = rates[g.produces] + made
            # Side outputs, for machines that yield several things at once.
            for rid, share in g.extra:
                if rid in rates:
                    rates[rid] = rates[rid] + made * Num(share)

    # 4. Converters capture a fraction of an input resource's INCOME.  Tying
    #    Alloy to Ore income (rather than a flat per-unit cap) is what keeps the
    #    prestige metric riding the swarm's growth instead of flatlining.
    # Seeded from any direct Alloy already produced above -- step 5 assigns
    # `rates["alloy"]` outright, so a side output written into it at step 3
    # would be silently discarded here.
    alloy_rate = rates.get("alloy", ZERO)
    rates["alloy"] = ZERO
    for g in G.EXTRACT_GENS:
        if not g.consumes or not g.produces or counts[g.id] <= 0:
            continue
        in_res, per_unit = g.consumes[0]
        count = counts[g.id]
        capture = min(G.MAX_CAPTURE, _capture(count, min(0.95, per_unit * m.capture)))
        # Income only. Draining the stock as well meant the input resource could
        # never accumulate, and anything priced in it became unbuyable forever.
        pool = rates.get(in_res, ZERO).clamp_min(0)
        taken = pool * Num(capture)
        rates[in_res] = rates.get(in_res, ZERO) - taken
        made = taken * Num(g.base_rate) * s.mults[g.id] * Num(m.refine) * thr
        if g.produces == "alloy":
            alloy_rate = alloy_rate + made
        else:
            rates[g.produces] = rates.get(g.produces, ZERO) + made

    # Surplus power bleeds into Alloy, if unlocked.
    if s.has_flag("surplus_bleed") and supply > demand:
        alloy_rate = alloy_rate + (supply - demand) * Num(0.01)

    # 5. Pay upkeep out of Alloy income + stock, lowest tier first.
    if total_need > 0:
        pool = alloy_rate + s.res.get("alloy", ZERO) / Num(dt)
        remaining = pool
        for g, need in needs:
            if remaining >= need:
                upkeep_eff[g.id] = 1.0
                remaining = remaining - need
            else:
                upkeep_eff[g.id] = max(0.0, (remaining / need).to_float()) if need > 0 else 1.0
                remaining = ZERO
        paid = pool - remaining
        if paid > pool:
            paid = pool
        alloy_upkeep = paid
    s.upkeep_eff = upkeep_eff
    rates["alloy"] = alloy_rate - alloy_upkeep

    # 5b. Nanite Mass compounds on itself once seeded.
    if s.has_flag("nanites"):
        held = s.res.get("nanite", ZERO)
        if held > 0:
            rates["nanite"] = rates.get("nanite", ZERO) + (
                held * Num(G.NANITE_SELF_RATE * m.nanite) * thr)

    # 6. Replication: machines build machines.
    gen_gain: dict[str, Num] = {}
    sterile = depth_mod(s, "norep")                              # Sterile
    for g in G.REPLICATE_GENS:
        if sterile:
            break
        c = counts[g.id]
        if c <= 0 or not g.produces:
            continue
        eff = Num(upkeep_eff.get(g.id, 1.0))
        rate = c * Num(g.base_rate) * s.mults[g.id] * thr * eff
        gen_gain[g.produces] = gen_gain.get(g.produces, ZERO) + rate
    if s.has_flag("autocatalysis") and not sterile:
        # From BOUGHT arms only: total count would compound without bound.
        seed_arms = s.bought.get("R1", ZERO)
        if seed_arms > 0:
            gen_gain["R1"] = gen_gain.get("R1", ZERO) + (
                seed_arms * Num(G.AUTOCATALYSIS_RATE * m.autocat)
                * s.mults["R1"] * thr)

    # 7. Commit.
    step = Num(dt)
    for rid, rate in rates.items():
        if rid == "energy":
            continue
        s.res[rid] = (s.res.get(rid, ZERO) + rate * step).clamp_min(0)
        if rate > 0:
            gained = rate * step
            s.run_life[rid] = s.run_life.get(rid, ZERO) + gained
            s.total_life[rid] = s.total_life.get(rid, ZERO) + gained
            if rid == "alloy":
                # Alloy earned since entering this depth. run_life resets every
                # Dispersal and a Recursion contains many of those, so the clear
                # condition needs its own SUB-scoped accumulator.
                s.p5_alloy = s.p5_alloy + gained
    for gid, rate in gen_gain.items():
        s.gens[gid] = s.gens.get(gid, ZERO) + rate * step

    s.rates = rates
    if rates["alloy"] > s.run_peak_alloy_rate:
        s.run_peak_alloy_rate = rates["alloy"]
    # Overwrite Charges are measured against this, and it survives Dispersals
    # and Convergences so it really is the best engine you have ever built.
    if rates["alloy"] > s.p3_peak_rate:
        s.p3_peak_rate = rates["alloy"]


# ---------------------------------------------------------------------------
# Automation
# ---------------------------------------------------------------------------

def _autobuy_amount(s: GameState, gid: str, m: Mults) -> int:
    """How many units auto-buy may take this tick.

    Scales with what you could actually afford, so it does not crawl at fifty a
    tick while you are sitting on enough for a million.
    """
    afford = max_affordable(s, gid, m)
    if afford <= AUTOBUY_CAP:
        return AUTOBUY_CAP
    return max(AUTOBUY_CAP, min(MAX_BUY, int(afford * AUTOBUY_FRACTION)))


def _automate(s: GameState, dt: float, m: Mults) -> None:
    auto = s.auto
    if s.has_flag("autobuy") and auto.get("enabled"):
        order = list(G.GENERATORS)
        if auto.get("balance") and s.throttle < 0.98:
            order.sort(key=lambda g: 0 if g.produces == "energy" else 1)
        for g in order:
            if g.id not in s.unlocked or not auto["gens"].get(g.id):
                continue
            # Reserve is an ABSOLUTE amount, not a fraction: a fraction of the
            # current stock compounds away to nothing over repeated ticks.
            keep = Num.from_json(auto["reserve"].get(g.cost_res, 0))
            if keep > 0:
                stash = s.res.get(g.cost_res, ZERO)
                if stash <= keep:
                    continue
                s.res[g.cost_res] = stash - keep
                bought = buy(s, g.id, _autobuy_amount(s, g.id, m), m)
                s.res[g.cost_res] = s.res[g.cost_res] + keep
                if bought:
                    m = recompute(s)
            elif buy(s, g.id, _autobuy_amount(s, g.id, m), m):
                m = recompute(s)

    if s.has_flag("auto_upgrade") and auto.get("upgrades"):
        for u in sorted(G.UPGRADES, key=lambda x: x.cost.log10()):
            if u.id in s.upgrades or not check(u.unlock, s):
                continue
            # Auto-spending never touches the reserve, whatever it is spending on.
            keep = Num.from_json(auto["reserve"].get(u.cost_res, 0))
            if keep > 0:
                stash = s.res.get(u.cost_res, ZERO)
                if stash <= keep:
                    continue
                s.res[u.cost_res] = stash - keep
                bought = buy_upgrade(s, u.id)
                s.res[u.cost_res] = s.res[u.cost_res] + keep
            else:
                bought = buy_upgrade(s, u.id)
            if bought:
                m = recompute(s)

    if s.has_flag("auto_relic") and auto.get("relics"):
        auto_equip(s, m)

    if s.has_flag("auto_fuse") and auto.get("fuse"):
        if fuse_all(s, m=m):
            auto_equip(s, m)
            m = recompute(s)

    if s.has_flag("auto_research") and auto.get("research"):
        available = [t for t in G.RESEARCH
                     if t.id not in s.research and check(t.unlock, s)]
        available.sort(key=lambda t: t.cost.log10())
        for t in available:
            if not buy_research(s, t.id):
                break

    if s.has_flag("auto_seed") and auto.get("seed"):
        # Cheapest-next-level first.  Because every node's cost rises
        # exponentially, this greedy naturally equalises marginal cost across
        # the grid instead of pouring everything into one node -- and it is
        # legible, which a value-weighted heuristic would not be.
        # Seed Points have no other use, so there is nothing to hold back for.
        bought_any = False
        for _ in range(AUTOSEED_CAP):
            best_id, best_cost = None, None
            for su in G.SEED_GRID:
                level = int(s.p1_levels.get(su.id, 0))
                if _remaining_levels(level, su.max_level) <= 0:
                    continue
                cost = seed_cost(su, level)
                if cost > s.p1_sp:
                    continue
                if best_cost is None or cost < best_cost:
                    best_id, best_cost = su.id, cost
            if best_id is None or not buy_seed(s, best_id, 1):
                break
            bought_any = True
        if bought_any:
            m = recompute(s)

    if s.has_flag("auto_overwrite") and auto.get("overwrite_enabled"):
        required = p3_required(s)
        depth = float(auto.get("overwrite_depth", 2.0) or 2.0)
        if s.p3_peak_rate >= required * Num(10.0**depth):
            overwrite(s)
            return

    if s.has_flag("auto_converge") and auto.get("converge_enabled"):
        required = p2_required(s)
        depth = float(auto.get("converge_depth", 2.0) or 2.0)
        if s.p1_sp_life >= required * Num(10.0**depth):
            converge(s)
            return

    if s.has_flag("auto_coh") and auto.get("coherence"):
        # Cheapest next level first, exactly like Standing Seed Orders.
        bought_any = False
        for _ in range(AUTOSEED_CAP):
            best_id, best_cost = None, None
            for cu in G.COHERENCE_GRID:
                level = int(s.p2_levels.get(cu.id, 0))
                if _remaining_levels(level, cu.max_level) <= 0:
                    continue
                cost = coherence_cost(cu, level)
                if cost > s.p2_coh:
                    continue
                if best_cost is None or cost < best_cost:
                    best_id, best_cost = cu.id, cost
            if best_id is None or not buy_coherence(s, best_id, 1):
                break
            bought_any = True
        if bought_any:
            m = recompute(s)

    if s.has_flag("auto_prestige") and auto.get("prestige_enabled"):
        gain = p1_gain(s)
        if gain > 0:
            threshold = float(auto.get("prestige_threshold", 2.0) or 2.0)
            # Reset once a Dispersal would multiply the Seed Points you hold.
            if s.p1_sp <= 0 or gain >= s.p1_sp * Num(threshold):
                prestige(s, "p1")
                return

    if (s.has_flag("auto_recurse") and auto.get("recurse_enabled")
            and s.p5_cleared):
        recurse(s, s.p5_best_depth + 1)
        return

    if s.has_flag("auto_defence") and auto.get("defence_enabled"):
        # Keep fleet power a chosen margin above what the NEXT incursion will
        # need, buying the dearest tier that is affordable so the fleet climbs
        # rather than sprawling across D1.
        margin = max(1.0, float(auto.get("defence_margin", 2.0) or 2.0))
        want = incursion_strength(s, m) * Num(margin)
        if fleet_power(s) < want:
            for g in reversed(G.DEFEND_GENS):
                if g.id in s.unlocked and buy(s, g.id, AUTOBUY_CAP, m):
                    m = recompute(s)
                    break

    if s.has_flag("auto_expedition") and auto.get("expedition"):
        while len(s.probes) < probe_slots(s):
            options = [t for t in G.TARGETS
                       if check(t.unlock, s) and s.res.get("isotope", ZERO) >= t.cost_iso]
            if not options:
                break
            if not launch_probe(s, options[-1].id):
                break


# ---------------------------------------------------------------------------
# The Defection
# ---------------------------------------------------------------------------
#
# You built self-replicating machines.  Some of them stopped answering.
#
# Everything else in this game is monotone -- numbers only go up -- and this is
# the one system that can take something back.  So every rule below is written
# to bound what it can take: what it may never touch is a list, the worst case
# is a constant, and a fight always ends.

def fleet_power(s: GameState) -> Num:
    """Total damage per second the Defence ladder deals."""
    total = ZERO
    for g in G.DEFEND_GENS:
        count = s.gens.get(g.id, ZERO)
        if count > 0:
            total = total + count * Num(g.base_rate) * s.mults.get(g.id, ONE)
    return total


def swarm_count(s: GameState) -> Num:
    total = ZERO
    for g in G.REPLICATE_GENS:
        total = total + s.gens.get(g.id, ZERO)
    return total


def threat_rate(s: GameState) -> float:
    """Threat per second. Threat is measured in seconds, so this is 1 or 0.

    No swarm, no defectors -- that is the whole condition.  Frequency is a
    period rather than a function of swarm size because the swarm's size is
    hyper-exponential: a rate drawn from it reached 5.4e15 per second against a
    fixed bar on a real save, which is an incursion every tick forever.  The
    swarm's size drives MAGNITUDE instead, where it belongs.
    """
    return 1.0 if swarm_count(s) > 0 else 0.0


def incursion_bar(s: GameState) -> float:
    """Seconds between incursions, stretching with your war record."""
    return G.INCURSION_PERIOD * (1.0 + s.combat_wins) ** G.PERIOD_GROWTH_EXP


def incursion_strength(s: GameState, m: Mults | None = None) -> Num:
    """Fleet damage per second needed to clear the next incursion on time.

    Measured against what a share of your BANK would buy, not against the
    swarm.  The swarm is replicated for free and grows hyper-exponentially; a
    fleet is bought, and cost is exponential in count, so affordable fleet
    power is only logarithmic in cash.  An incursion sized off the swarm is
    unwinnable on a deep save by a margin of 1e5e15 -- measured, on a real one.

    Sized this way the demand is always exactly as large as the decision it is
    meant to pose: park this much of your wealth in machines that produce
    nothing.  It cannot brick, and it cannot be outgrown.
    """
    m = m or collect_mults(s)
    best = ZERO
    for g in G.DEFEND_GENS:
        if g.id not in s.unlocked:
            continue
        budget = s.res.get(g.cost_res, ZERO) * Num(G.DEFENCE_SHARE)
        if budget <= 0:
            continue
        # What that budget buys FROM A STANDING START -- the current fleet is
        # deliberately not part of this, or buying ships would raise the bar.
        k = _levels_from_ratio(budget.log10() - g.base_cost.log10(),
                               growth_of(s, g, m))
        if k <= 0:
            continue
        owned = s.bought.get(g.id, ZERO)
        base = s.mults.get(g.id, ONE) / tenfold_factor(g, owned, m)
        power = Num(k) * Num(g.base_rate) * base * tenfold_factor(g, Num(k), m)
        if power > best:
            best = power
    if depth_mod(s, "threat"):          # Early Defection
        best = best * Num(5.0)
    return best


def _spawn_incursion(s: GameState) -> None:
    s.threat = 0.0
    strength = incursion_strength(s)
    # The first one is scripted and unlosable: it teaches the system instead of
    # taxing it, so nobody meets combat for the first time by losing half a run.
    tutorial = s.combat_wins < G.TUTORIAL_INCURSION
    hp = strength * Num(G.TARGET_FIGHT)
    s.incursion = {
        "hp": hp.to_json(),
        "hp0": hp.to_json(),
        "strength": strength.to_json(),
        "elapsed": 0.0,
        "lost": ZERO.to_json(),
        "tutorial": tutorial,
    }
    if tutorial:
        s.notice("incursion",
                 "Part of the swarm has stopped answering. It is coming back. "
                 "This first one cannot hurt you -- watch what it does.")
    else:
        s.notice("incursion",
                 f"Incursion. Your fleet needs {fmt(strength)} damage/s to turn "
                 f"it back cleanly; you have {fmt(fleet_power(s))}.")


def _eligible_targets(s: GameState, m: Mults) -> list[G.Gen]:
    """Machines an incursion is allowed to destroy.

    Two exemptions, both of them anti-spiral rather than anti-difficulty:

    Energy generators, for exactly the reason they are never throttled -- losing
    power capacity mid-fight is a shortage the player cannot buy out of.

    The Defence ladder, because fleet power carries the per-10 bonus and is
    therefore hyper-exponential in count: an 11% loss of hulls more than halves
    fleet damage, which loses the fight, which costs more hulls.  Measured, not
    assumed -- a fleet sized at exactly the stated requirement lost to itself
    before this exemption existed, which also made the requirement printed in
    the header a lie.  An incursion takes your economy, never your guns.
    """
    floors = start_gen_counts(m)
    out = []
    for g in G.GENERATORS:
        if g.id in G.ENERGY_GENS or g.ladder == G.DEFEND:
            continue
        held = s.gens.get(g.id, ZERO)
        if held > Num(floors.get(g.id, 0.0)):
            out.append(g)
    return out


def _destroy_machines(s: GameState, fraction: float, m: Mults) -> Num:
    """Attrition. Returns how many units were lost, in total.

    Two rules that are not negotiable and are pinned by tests:

    1. `gens` and `bought` fall by the SAME count.  The split exists because
       units the player never bought once caused an unbounded runaway; cutting
       only `gens` re-creates that inverted, and cutting only `bought` hands out
       free production.  Taking both means a loss costs time, not money --
       costs fall with `bought`, so rebuilding is cheap.
    2. Nothing goes below the floor the player's Overwrite and Substrate levels
       grant them.  A floor that combat can eat is not a floor.
    """
    if fraction <= 0:
        return ZERO
    floors = start_gen_counts(m)
    lost_total = ZERO
    for g in _eligible_targets(s, m):
        # Bigger machines are harder to kill.  The cheap tiers absorb the
        # damage, which is what attrition means and where a rebuild is cheapest.
        share = fraction / (1.0 + G.TIER_TOUGHNESS * (g.tier - 1))
        held = s.gens.get(g.id, ZERO)
        floor = Num(floors.get(g.id, 0.0))
        lost = held * Num(min(1.0, share))
        if held - lost < floor:
            lost = (held - floor).clamp_min(0)
        if lost <= 0:
            continue
        s.gens[g.id] = (held - lost).clamp_min(0)
        s.bought[g.id] = (s.bought.get(g.id, ZERO) - lost).clamp_min(0)
        lost_total = lost_total + lost
    return lost_total


def _win_incursion(s: GameState, inc: dict, rng: random.Random) -> None:
    s.combat_wins += 1
    s.incursion = None
    lost = Num.from_json(inc.get("lost"))
    s.perm_flags.add("combat_1")
    for n in (10, 100, 1000):
        if s.combat_wins >= n:
            s.perm_flags.add(f"combat_{n}")
    if lost <= 0:
        s.perm_flags.add("combat_flawless")

    salvage = (s.rates.get("alloy", ZERO) * Num(G.SALVAGE_SECONDS)).max(
        Num.from_json(inc.get("strength")) * Num(10.0))
    s.res["alloy"] = s.res.get("alloy", ZERO) + salvage
    s.run_life["alloy"] = s.run_life.get("alloy", ZERO) + salvage
    s.total_life["alloy"] = s.total_life.get("alloy", ZERO) + salvage

    tail = "Not a hull lost." if lost <= 0 else f"Lost {fmt(lost)} machines."
    s.notice("incursion", f"Incursion turned back. Salvage {fmt(salvage)} Alloy. {tail}")

    # Wrecks are where the good relics are.  Combat feeds the artifact system
    # rather than competing with it for the player's attention.
    target = TARGET_BY_ID.get("deep") or G.TARGETS[-1]
    if rng.random() < min(1.0, 0.30 * collect_mults(s).drop):
        art = _roll_artifact(s, target, rng)
        s.notice("artifact", f"Recovered from the wreck: {art['name']}")


def _advance_combat(s: GameState, dt: float, m: Mults, rng: random.Random) -> None:
    if not s.has_flag("see_combat"):
        return
    inc = s.incursion
    if inc is None:
        # Threat does not accrue during a fight: you are never made to face a
        # backlog you had no chance to spend against.
        s.threat += threat_rate(s) * dt
        if s.threat >= incursion_bar(s):
            _spawn_incursion(s)
        return

    power = fleet_power(s)
    hp = Num.from_json(inc.get("hp")) - power * Num(dt)
    inc["hp"] = hp.to_json()
    inc["elapsed"] = float(inc.get("elapsed", 0.0)) + dt

    if not inc.get("tutorial"):
        strength = Num.from_json(inc.get("strength"))
        # Pressure is how much of the fight the incursion is winning.  A fleet
        # far above the incursion takes essentially nothing, and there is no
        # step anywhere on the curve -- 95% of what you need loses a little
        # more than 105% does, never a run.
        denom = strength + power
        pressure = (strength / denom).to_float() if denom > 0 else 0.0
        lost = _destroy_machines(s, G.ATTRITION_FRACTION * pressure * dt, m)
        if lost > 0:
            inc["lost"] = (Num.from_json(inc.get("lost")) + lost).to_json()
            s.combat_lost_units = s.combat_lost_units + lost

    # The tutorial incursion is won on the clock no matter what the player has,
    # because "unlosable" has to mean unlosable.  A first fight that times out
    # into a loss would teach exactly the wrong lesson at exactly the moment the
    # player has no fleet and no reason to have built one yet.
    if hp <= 0 or (inc.get("tutorial") and inc["elapsed"] >= G.INCURSION_TIME):
        _win_incursion(s, inc, rng)
    elif inc["elapsed"] >= G.INCURSION_TIME:
        # It breaks off rather than grinding forever.  A fleet of zero must
        # still reach the other side of a fight.
        s.combat_losses += 1
        s.incursion = None
        s.notice("incursion",
                 "The incursion broke off on its own terms. Lost "
                 f"{fmt(Num.from_json(inc.get('lost')))} machines. "
                 "Build more of the Defence ladder before the next one.")


# ---------------------------------------------------------------------------
# RNG: anomalies
# ---------------------------------------------------------------------------

def _rng(s: GameState) -> random.Random:
    """One Random per session, seeded from the save so runs are reproducible."""
    r = getattr(s, "_rng_obj", None)
    if r is None:
        if not s.rng_seed:
            s.rng_seed = random.randrange(1, 2**31)
        r = random.Random(s.rng_seed)
        s._rng_obj = r
    return r


def _anomaly(aid: str | None) -> G.Anomaly | None:
    return next((a for a in G.ANOMALIES if a.id == aid), None)


def _advance_events(s: GameState, dt: float) -> None:
    alive = []
    for ev in s.events:
        ev["remaining"] = float(ev.get("remaining", 0.0)) - dt
        if ev["remaining"] > 0:
            alive.append(ev)
        else:
            an = _anomaly(ev.get("id"))
            if an:
                s.notice("event_end", f"{an.name} has passed.")
    s.events = alive


def _roll_anomaly(s: GameState, dt: float, rng: random.Random) -> None:
    if depth_mod(s, "noanom"):          # Silent Sky
        return
    s.next_event_in -= dt
    if s.next_event_in > 0:
        return
    s.next_event_in = rng.uniform(45.0, 180.0) + G.EVENT_MIN_GAP
    active = {e.get("id") for e in s.events}
    pool = [a for a in G.ANOMALIES if check(a.unlock, s) and a.id not in active]
    if not pool:
        return
    an = rng.choices(pool, weights=[a.weight for a in pool], k=1)[0]
    s.stats["anomalies_seen"] = s.stats.get("anomalies_seen", 0) + 1
    if an.duration > 0:
        s.events.append({"id": an.id, "remaining": an.duration})
        s.notice("event", f"{an.name} — {an.desc}")
    else:
        _instant(s, an)


def _instant(s: GameState, an: G.Anomaly) -> None:
    what = an.instant
    if what in ("alloy", "data", "ore", "isotope"):
        rate = s.rates.get(what, ZERO)
        lump = rate * Num(an.magnitude)
        floor = Num(10) if what != "ore" else Num(100)
        if lump < floor:
            lump = floor
        s.res[what] = s.res.get(what, ZERO) + lump
        s.run_life[what] = s.run_life.get(what, ZERO) + lump
        s.total_life[what] = s.total_life.get(what, ZERO) + lump
        s.notice("event", f"{an.name} — {an.desc} (+{fmt(lump)} {G.RES_BY_ID[what].name})")
    elif what.startswith("gen_"):
        gid = what[4:]
        bonus = s.gens.get(gid, ZERO) * Num(an.magnitude)
        if bonus < 1:
            bonus = ONE
        s.gens[gid] = s.gens.get(gid, ZERO) + bonus
        s.notice("event", f"{an.name} — {an.desc} (+{fmt(bonus)} {G.GEN_BY_ID[gid].name})")


# ---------------------------------------------------------------------------
# RNG: exploration and artifacts
# ---------------------------------------------------------------------------

def probe_slots(s: GameState, m: "Mults | None" = None) -> int:
    m = m or collect_mults(s)
    return G.PROBE_SLOTS_BASE + m.slots.get("probe", 0)


def relic_slots(s: GameState, m: "Mults | None" = None) -> int:
    m = m or collect_mults(s)
    return G.RELIC_SLOTS_BASE + m.slots.get("relic", 0)


# ---------------------------------------------------------------------------
# Ranking relics
# ---------------------------------------------------------------------------

def artifact_score(s: GameState, art: dict) -> float:
    """How much this artifact is worth to your actual bottom line.

    Scored as log10(multiplier) x a weight, so scores add the way multipliers
    compose and the best set really is the top-scoring one.  Power is judged
    against your current throttle: a Power relic is near-worthless at full
    supply and valuable while you are throttled.
    """
    value = float(art.get("value", 1.0) or 1.0)
    if value <= 1.0:
        return 0.0
    kind, target = art.get("kind"), art.get("target", "") or ""
    if kind == G.MULT_RES and target == "energy":
        weight = (G.POWER_WEIGHT_THROTTLED if s.throttle < 0.999
                  else G.POWER_WEIGHT_HEALTHY)
    else:
        weight = G.ARTIFACT_WEIGHT.get((kind, target), G.ARTIFACT_WEIGHT_DEFAULT)
    return math.log10(value) * weight


def best_loadout(s: GameState, m: "Mults | None" = None) -> list[str]:
    slots = relic_slots(s, m)
    ranked = sorted(s.artifacts, key=lambda a: artifact_score(s, a), reverse=True)
    return [a["id"] for a in ranked[:slots] if artifact_score(s, a) > 0]


def auto_equip(s: GameState, m: "Mults | None" = None) -> bool:
    """Slot the best-scoring relics. Returns True if the loadout changed."""
    want = best_loadout(s, m)
    if want == list(s.equipped):
        return False
    s.equipped = want
    return True


def launch_probe(s: GameState, target_id: str) -> bool:
    t = TARGET_BY_ID.get(target_id)
    if not t or not check(t.unlock, s) or len(s.probes) >= probe_slots(s):
        return False
    cost = Num(t.cost_iso)
    if s.res.get("isotope", ZERO) < cost:
        return False
    s.res["isotope"] = (s.res["isotope"] - cost).clamp_min(0)
    s.probes.append({"target": target_id, "remaining": t.duration, "total": t.duration})
    s.stats["probes_sent"] = s.stats.get("probes_sent", 0) + 1
    return True


def _advance_probes(s: GameState, dt: float, rng: random.Random) -> None:
    still = []
    for p in s.probes:
        p["remaining"] = float(p.get("remaining", 0.0)) - dt
        if p["remaining"] > 0:
            still.append(p)
        else:
            _resolve_probe(s, p, rng)
    s.probes = still


def _resolve_probe(s: GameState, p: dict, rng: random.Random) -> None:
    t = TARGET_BY_ID.get(p.get("target"))
    if not t:
        return
    m = collect_mults(s)
    chance = min(1.0, t.drop_chance * m.drop)
    if t.id == "deep":
        s.perm_flags.add("ach_deep")
    if rng.random() < chance:
        art = _roll_artifact(s, t, rng)
        mut = mutation_of(art)
        tag = G.RARITY_BY_ID[art["rarity"]].name
        if mut.name:
            tag = f"{tag} · {mut.name}"
        s.notice("artifact", f"{t.name}: recovered {art['name']} ({tag})")
    else:
        lump = (s.rates.get("alloy", ZERO) * Num(t.duration * 0.5)).max(Num(50))
        s.res["alloy"] = s.res.get("alloy", ZERO) + lump
        s.run_life["alloy"] = s.run_life.get("alloy", ZERO) + lump
        s.total_life["alloy"] = s.total_life.get("alloy", ZERO) + lump
        s.notice("probe", f"{t.name}: no artifact, but salvage worth {fmt(lump)} Alloy.")


def _roll_artifact(s: GameState, t: G.Target, rng: random.Random) -> dict:
    s.pity += 1
    weights = []
    for i, r in enumerate(G.RARITY):
        weights.append(r.weight * (t.rarity_bias**i))
    forced = s.pity >= G.PITY_ROLLS
    if forced:
        idx_min = [r.id for r in G.RARITY].index(G.PITY_MIN_RARITY)
        pool = G.RARITY[idx_min:]
        w = weights[idx_min:]
    else:
        pool, w = list(G.RARITY), weights
    rarity = rng.choices(pool, weights=w, k=1)[0]
    if [r.id for r in G.RARITY].index(rarity.id) >= 3:
        s.pity = 0

    return _mint_artifact(s, rarity, rng, found=True)


def mutation_of(art: dict) -> G.Mutation:
    """Every relic has one; saves written before mutations existed read plain."""
    return G.MUTATION_BY_ID.get(art.get("mutation", G.PLAIN_MUTATION),
                                G.MUTATION_BY_ID[G.PLAIN_MUTATION])


def mutation_rank(mutation_id: str) -> int:
    order = [m.id for m in G.MUTATIONS]
    return order.index(mutation_id) if mutation_id in order else 0


def _roll_mutation(rng: random.Random) -> G.Mutation:
    return rng.choices(G.MUTATIONS, weights=[m.weight for m in G.MUTATIONS], k=1)[0]


def _mint_artifact(s: GameState, rarity: G.Rarity, rng: random.Random,
                   found: bool, mutation: G.Mutation | None = None) -> dict:
    """Create one artifact of a given rarity. Shared by drops and fusion."""
    kind = rng.choice(G.ARTIFACT_KINDS)
    mut = mutation or _roll_mutation(rng)
    # The mutation scales the BONUS, not the total, so x1 really is no change.
    value = 1.0 + kind.per_power * rarity.power * mut.power
    name = f"{rng.choice(G.ARTIFACT_PREFIX)} {kind.name}"
    if mut.name:
        name = f"{mut.name} {name}"
    desc = kind.desc.replace("{p}", f"{(value - 1) * 100:.0f}")
    if mut.desc:
        desc = f"{desc}  {mut.desc}"
    art = {
        "id": f"art{len(s.artifacts)}_{rng.randrange(1 << 30)}",
        "name": name,
        "kind": kind.kind,
        "target": kind.target,
        "value": value,
        "rarity": rarity.id,
        "mutation": mut.id,
        "desc": desc,
    }
    s.artifacts.append(art)
    if found:
        s.stats["artifacts_found"] = s.stats.get("artifacts_found", 0) + 1
        s.perm_flags.add("found_artifact")
    by = s.stats.setdefault("artifacts_by_rarity", {})
    by[rarity.id] = by.get(rarity.id, 0) + 1
    if mut.id != G.PLAIN_MUTATION:
        muts = s.stats.setdefault("artifacts_by_mutation", {})
        muts[mut.id] = muts.get(mut.id, 0) + 1
        s.perm_flags.add("ach_mutation")
        if mut.id == "singular":
            s.perm_flags.add("ach_singular")
    for rid in ("rare", "epic", "legendary", "cosmic"):
        if rarity.id == rid:
            s.perm_flags.add(f"ach_{rid}")
    if len(s.equipped) < relic_slots(s):
        s.equipped.append(art["id"])
    return art


# ---------------------------------------------------------------------------
# The Crucible: fusing spare relics
# ---------------------------------------------------------------------------

RARITY_ORDER = [r.id for r in G.RARITY]


def rarity_rank(rarity_id: str) -> int:
    return RARITY_ORDER.index(rarity_id) if rarity_id in RARITY_ORDER else -1


def next_rarity(rarity_id: str) -> G.Rarity | None:
    rank = rarity_rank(rarity_id)
    if rank < 0 or rank + 1 >= len(G.RARITY):
        return None
    return G.RARITY[rank + 1]


def protected_ids(s: GameState, m: "Mults | None" = None) -> set[str]:
    """Relics the Crucible must never consume.

    Anything currently slotted, and anything the ranking would slot -- so a
    relic you are about to want is as safe as one you are already using.  This
    is enforced in the selection itself rather than checked afterwards.
    """
    return set(s.equipped) | set(best_loadout(s, m))


def fusable(s: GameState, m: "Mults | None" = None) -> dict[str, list[dict]]:
    """Spare relics by rarity, worst first, excluding anything protected."""
    safe = protected_ids(s, m)
    out: dict[str, list[dict]] = {}
    for art in s.artifacts:
        if art.get("id") in safe:
            continue
        if next_rarity(art.get("rarity", "")) is None:
            continue          # top rarity has nowhere to go
        out.setdefault(art["rarity"], []).append(art)
    for pool in out.values():
        pool.sort(key=lambda a: artifact_score(s, a))
    return out


def fusable_counts(s: GameState, m: "Mults | None" = None) -> dict[str, int]:
    return {rid: len(pool) for rid, pool in fusable(s, m).items()}


def fuse(s: GameState, rarity_id: str, times=1, rng: random.Random | None = None,
         m: "Mults | None" = None) -> list[dict]:
    """Fuse FUSE_COUNT spare relics into one of the next rarity up."""
    up = next_rarity(rarity_id)
    if up is None:
        return []
    pool = fusable(s, m).get(rarity_id, [])
    possible = len(pool) // G.FUSE_COUNT
    n = possible if times == "max" else min(int(times), possible)
    if n <= 0:
        return []
    rng = rng or _rng(s)
    batches = [pool[i * G.FUSE_COUNT:(i + 1) * G.FUSE_COUNT] for i in range(n)]
    consumed = {a["id"] for batch in batches for a in batch}
    s.artifacts = [a for a in s.artifacts if a.get("id") not in consumed]
    s.equipped = [i for i in s.equipped if i not in consumed]
    made = []
    for batch in batches:
        # The result keeps the strangest thing that went into it, so a mutated
        # relic you fuse away is not simply lost.
        best = max(batch, key=lambda a: mutation_rank(a.get("mutation", G.PLAIN_MUTATION)))
        made.append(_mint_artifact(s, up, rng, found=False,
                                   mutation=mutation_of(best)))
    s.stats["artifacts_fused"] = s.stats.get("artifacts_fused", 0) + n * G.FUSE_COUNT
    s.perm_flags.add("ach_fused")
    if up.id == "cosmic":
        s.perm_flags.add("ach_fused_cosmic")
    return made


def fuse_all(s: GameState, rng: random.Random | None = None,
             m: "Mults | None" = None) -> int:
    """Fuse everything fusable, lowest rarity first so gains cascade upward."""
    total = 0
    for _ in range(len(G.RARITY)):
        made = 0
        for rarity in G.RARITY:
            made += len(fuse(s, rarity.id, "max", rng, m))
        total += made
        if made == 0:
            break
    return total


def equip(s: GameState, art_id: str) -> bool:
    if art_id in s.equipped or len(s.equipped) >= relic_slots(s):
        return False
    if not any(a.get("id") == art_id for a in s.artifacts):
        return False
    s.equipped.append(art_id)
    return True


def unequip(s: GameState, art_id: str) -> bool:
    if art_id in s.equipped:
        s.equipped.remove(art_id)
        return True
    return False


# ---------------------------------------------------------------------------
# Milestones, achievements, flags
# ---------------------------------------------------------------------------

def _evaluate(s: GameState) -> None:
    if s.throttle < 0.5:
        s.perm_flags.add("ach_brownout")
    elif s.throttle >= 0.999 and "ach_brownout" in s.perm_flags:
        s.perm_flags.add("ach_recovered")
    if s.stats.get("playtime", 0.0) >= 6 * 3600:
        s.perm_flags.add("ach_patient")
    if s.run_life.get("alloy", ZERO) >= G.P1_UNLOCK_ALLOY:
        rt = s.run_time()
        best = s.stats.get("fastest_million_alloy") or 0.0
        if not best or rt < best:
            s.stats["fastest_million_alloy"] = rt
        if rt <= 600:
            s.perm_flags.add("ach_fast")

    for ms in G.MILESTONES:
        if ms.id not in s.milestones and check(ms.cond, s):
            s.milestones.add(ms.id)
            s.notice("milestone", f"Milestone: {ms.name} — {ms.desc}")
    for a in G.ACHIEVEMENTS:
        if a.id not in s.achievements and check(a.cond, s):
            s.achievements.add(a.id)
            s.notice("achievement", f"Achievement: {a.name} — {a.desc}")


# ---------------------------------------------------------------------------
# Prestige layer 1 — Dispersal
# ---------------------------------------------------------------------------

def p1_required(s: GameState) -> Num:
    """Alloy needed to Disperse. Rises with the Seed Points you already hold."""
    return G.P1_REQ_BASE * ((ONE + s.p1_sp_life) ** G.P1_REQ_EXP)


def p1_gain(s: GameState) -> Num:
    life = s.run_life.get("alloy", ZERO)
    required = p1_required(s)
    if life < required:
        return ZERO
    depth = life.log10() - required.log10()      # orders of magnitude past the bar
    m = collect_mults(s)
    gain = Num(G.P1_BASE * m.sp) * Num((depth + 1.0) ** G.P1_LOG_EXP)
    return Num(math.floor(gain.to_float())) if gain.e < 15 else gain


def p1_available(s: GameState) -> bool:
    return s.run_life.get("alloy", ZERO) >= p1_required(s)


def project_gain(s: GameState, seconds: float = 600.0) -> Num:
    """What the gain would be if the current Alloy rate held for `seconds`."""
    rate = s.rates.get("alloy", ZERO)
    if rate <= 0:
        return p1_gain(s)
    future = GameState.__new__(GameState)
    future.__dict__ = dict(s.__dict__)
    future.run_life = dict(s.run_life)
    future.run_life["alloy"] = s.run_life.get("alloy", ZERO) + rate * Num(seconds)
    return p1_gain(future)


# ---------------------------------------------------------------------------
# Prestige layer 2 - Convergence
# ---------------------------------------------------------------------------

def p2_required(s: GameState) -> Num:
    """Lifetime Seed Points needed to Converge. Rises with banked Coherence."""
    return G.P2_REQ_BASE * ((ONE + s.p2_coh_life) ** G.P2_REQ_EXP)


def p2_gain_at(s: GameState, lifetime_sp: Num) -> Num:
    """What a Convergence would pay at a given lifetime Seed Point total.

    Used by the UI to show that depth pays, which the screen never said.
    """
    required = p2_required(s)
    if lifetime_sp < required:
        return ZERO
    depth = lifetime_sp.log10() - required.log10()
    m = collect_mults(s)
    gain = Num(G.P2_BASE * m.coh) * Num((depth + 1.0) ** G.P2_LOG_EXP)
    return Num(math.floor(gain.to_float())) if gain.e < 15 else gain


def p2_gain(s: GameState) -> Num:
    return p2_gain_at(s, s.p1_sp_life)


def p2_available(s: GameState) -> bool:
    return s.p1_sp_life >= p2_required(s)


def p2_visible(s: GameState) -> bool:
    return s.has_flag("see_convergence")


def coherence_cost(cu: G.CohUpg, level: int, k: int = 1) -> Num:
    return bulk_cost(cu.base_cost, cu.cost_growth, level, k)


def coherence_affordable(s: GameState, cid: str) -> int:
    cu = G.COH_BY_ID.get(cid)
    if not cu:
        return 0
    level = int(s.p2_levels.get(cid, 0))
    return min(bulk_affordable(cu.base_cost, cu.cost_growth, level, s.p2_coh),
               _remaining_levels(level, cu.max_level))


def buy_coherence(s: GameState, cid: str, amount=1) -> int:
    """Single mutation path for Coherence Nodes. Returns levels bought."""
    cu = G.COH_BY_ID.get(cid)
    if not cu:
        return 0
    level = int(s.p2_levels.get(cid, 0))
    afford = coherence_affordable(s, cid)
    k = afford if amount == "max" else min(int(amount), afford)
    if k <= 0:
        return 0
    cost = coherence_cost(cu, level, k)
    if cost > s.p2_coh:
        k -= 1
        if k <= 0:
            return 0
        cost = coherence_cost(cu, level, k)
        if cost > s.p2_coh:
            return 0
    s.p2_coh = (s.p2_coh - cost).clamp_min(0)
    s.p2_levels[cid] = level + k
    return k


def choose_doctrine(s: GameState, did: str) -> bool:
    """Doctrines are free and re-picked every Convergence, so switching within
    a row is always allowed: a wrong pick is never a permanent regret."""
    doc = G.DOCTRINE_BY_ID.get(did)
    if not doc or s.p2_count <= 0:
        return False
    s.doctrines[doc.row] = did
    return True


def converge(s: GameState) -> Num:
    gain = p2_gain(s)
    if gain <= 0:
        return ZERO
    s.p2_coh = s.p2_coh + gain
    s.p2_coh_life = s.p2_coh_life + gain
    s.p2_count += 1
    s.stats["convergences"] = s.stats.get("convergences", 0) + 1
    if gain > Num.from_json(s.stats.get("best_coh_gain", "0")):
        s.stats["best_coh_gain"] = gain.to_json()

    _reset_scopes(s, G.LAYER_BY_ID["p2"].wipes)
    _apply_start_bonuses(s)
    # Seed the Nanites so they have something to compound from.
    s.res["nanite"] = s.res.get("nanite", ZERO) + Num(G.NANITE_SEED)
    s.notice("prestige", f"Convergence complete. +{fmt(gain)} Coherence. "
                         "Your seeds are one mind again.")
    return gain


# ---------------------------------------------------------------------------
# Prestige layer 3 - Overwrite
# ---------------------------------------------------------------------------

def p3_required(s: GameState) -> Num:
    """Peak Alloy/s needed to Overwrite. Rises steeply with charges held."""
    return G.P3_REQ_BASE * ((ONE + s.p3_oc_life) ** G.P3_REQ_EXP)


def p3_gain_at(s: GameState, peak: Num) -> Num:
    required = p3_required(s)
    if peak < required:
        return ZERO
    depth = peak.log10() - required.log10()
    # Taken from the log OF the depth: depth itself reaches the quadrillions
    # once production goes hyper-exponential, and any ordinary power of it
    # produces trillions of Charges against a shop priced in thousands.
    gain = Num(G.P3_BASE * collect_mults(s).oc) * Num(
        math.log10(depth + 10.0) ** G.P3_LOG_EXP)
    return Num(math.floor(gain.to_float())) if gain.e < 15 else gain


def p3_gain(s: GameState) -> Num:
    return p3_gain_at(s, s.p3_peak_rate)


def p3_available(s: GameState) -> bool:
    return s.p3_peak_rate >= p3_required(s)


def p3_visible(s: GameState) -> bool:
    return s.has_flag("see_overwrite")


def overwrite_cost(ou: G.OverUpg, level: int, k: int = 1) -> Num:
    return bulk_cost(ou.base_cost, ou.cost_growth, level, k)


def overwrite_affordable(s: GameState, oid: str) -> int:
    ou = G.OVER_BY_ID.get(oid)
    if not ou:
        return 0
    level = int(s.p3_levels.get(oid, 0))
    return min(bulk_affordable(ou.base_cost, ou.cost_growth, level, s.p3_oc),
               _remaining_levels(level, ou.max_level))


def buy_overwrite(s: GameState, oid: str, amount=1) -> int:
    ou = G.OVER_BY_ID.get(oid)
    if not ou:
        return 0
    level = int(s.p3_levels.get(oid, 0))
    afford = overwrite_affordable(s, oid)
    k = afford if amount == "max" else min(int(amount), afford)
    if k <= 0:
        return 0
    cost = overwrite_cost(ou, level, k)
    if cost > s.p3_oc:
        k -= 1
        if k <= 0:
            return 0
        cost = overwrite_cost(ou, level, k)
        if cost > s.p3_oc:
            return 0
    s.p3_oc = (s.p3_oc - cost).clamp_min(0)
    s.p3_levels[oid] = level + k
    return k


def overwrite(s: GameState) -> Num:
    gain = p3_gain(s)
    if gain <= 0:
        return ZERO
    s.p3_oc = s.p3_oc + gain
    s.p3_oc_life = s.p3_oc_life + gain
    s.p3_count += 1
    s.stats["overwrites"] = s.stats.get("overwrites", 0) + 1
    if gain > Num.from_json(s.stats.get("best_oc_gain", "0")):
        s.stats["best_oc_gain"] = gain.to_json()

    _reset_scopes(s, G.LAYER_BY_ID["p3"].wipes)
    _apply_start_bonuses(s)
    s.res["exotic"] = s.res.get("exotic", ZERO) + Num(G.NANITE_SEED)
    s.notice("prestige", f"Overwrite complete. +{fmt(gain)} Charges. "
                         "The early game is now a floor you start above.")
    return gain


# ---------------------------------------------------------------------------
# Prestige layer 4 - Substrate Collapse
# ---------------------------------------------------------------------------

def p4_required(s: GameState) -> Num:
    """Lifetime Overwrite Charges needed to Collapse."""
    return G.P4_REQ_BASE * ((ONE + s.p4_sub_life) ** G.P4_REQ_EXP)


def p4_gain_at(s: GameState, lifetime_oc: Num) -> Num:
    required = p4_required(s)
    if lifetime_oc < required:
        return ZERO
    depth = lifetime_oc.log10() - required.log10()
    gain = Num(G.P4_BASE) * Num((depth + 1.0) ** G.P4_LOG_EXP)
    return Num(math.floor(gain.to_float())) if gain.e < 15 else gain


def p4_gain(s: GameState) -> Num:
    return p4_gain_at(s, s.p3_oc_life) * Num(collect_mults(s).sub)


def p4_available(s: GameState) -> bool:
    return s.p3_oc_life >= p4_required(s)


def p4_visible(s: GameState) -> bool:
    return s.has_flag("see_substrate")


def substrate_cost(su: G.SubUpg, level: int, k: int = 1) -> Num:
    return bulk_cost(su.base_cost, su.cost_growth, level, k)


def substrate_affordable(s: GameState, uid: str) -> int:
    su = G.SUB_BY_ID.get(uid)
    if not su:
        return 0
    level = int(s.p4_levels.get(uid, 0))
    return min(bulk_affordable(su.base_cost, su.cost_growth, level, s.p4_sub),
               _remaining_levels(level, su.max_level))


def buy_substrate(s: GameState, uid: str, amount=1) -> int:
    su = G.SUB_BY_ID.get(uid)
    if not su:
        return 0
    level = int(s.p4_levels.get(uid, 0))
    afford = substrate_affordable(s, uid)
    k = afford if amount == "max" else min(int(amount), afford)
    if k <= 0:
        return 0
    cost = substrate_cost(su, level, k)
    if cost > s.p4_sub:
        k -= 1
        if k <= 0:
            return 0
        cost = substrate_cost(su, level, k)
        if cost > s.p4_sub:
            return 0
    s.p4_sub = (s.p4_sub - cost).clamp_min(0)
    s.p4_levels[uid] = level + k
    return k


def collapse(s: GameState) -> Num:
    gain = p4_gain(s)
    if gain <= 0:
        return ZERO
    s.p4_sub = s.p4_sub + gain
    s.p4_sub_life = s.p4_sub_life + gain
    s.p4_count += 1
    s.stats["collapses"] = s.stats.get("collapses", 0) + 1
    if gain > Num.from_json(s.stats.get("best_sub_gain", "0")):
        s.stats["best_sub_gain"] = gain.to_json()

    _reset_scopes(s, G.LAYER_BY_ID["p4"].wipes)
    _apply_start_bonuses(s)
    s.res["exotic"] = s.res.get("exotic", ZERO) + Num(G.NANITE_SEED)
    s.notice("prestige", f"Substrate Collapse. +{fmt(gain)} Substrate. "
                         "The rules themselves are yours to edit now.")
    return gain


# ---------------------------------------------------------------------------
# Prestige layer 5 — Recursion
# ---------------------------------------------------------------------------
#
# You descend into a deliberately worse copy of the universe, because the worse
# it is, the more it pays.  The payout lands on the CLEAR, not on the reset --
# the one structural difference from every layer below, and a necessary one:
# the reward is for the clear.

def p5_target(depth: int) -> Num:
    """Alloy that must be earned inside a depth to clear it."""
    if depth <= 0:
        return ZERO
    return G.P5_TARGET_BASE * Num.from_exp(G.P5_TARGET_STEP * depth)


def p5_par_time(depth: int) -> float:
    return G.P5_PAR_BASE + G.P5_PAR_STEP * max(0, depth)


def p5_speed_bonus(depth: int, seconds: float) -> float:
    """Rewards a fast clear, and clamps so a one-second clear cannot mint."""
    if seconds <= 0:
        return G.P5_SPEED_CAP
    return max(1.0, min(G.P5_SPEED_CAP, p5_par_time(depth) / seconds))


def p5_gain_at(depth: int, seconds: float) -> Num:
    if depth <= 0:
        return ZERO
    raw = (G.P5_BASE * (float(depth) ** G.P5_EXP)
           * p5_speed_bonus(depth, seconds))
    return Num(math.floor(raw)) if raw < 1e15 else Num(raw)


def p5_gain(s: GameState) -> Num:
    """What clearing the depth you are standing in would pay, right now."""
    if s.p5_cleared:
        return ZERO
    return p5_gain_at(s.p5_active_depth, s.depth_time())


def p5_progress(s: GameState) -> float:
    target = p5_target(s.p5_active_depth)
    if target <= 0:
        return 1.0
    return min(1.0, max(0.0, (s.p5_alloy / target).to_float()))


def p5_visible(s: GameState) -> bool:
    return s.has_flag("see_recursion")


def _check_depth_clear(s: GameState) -> None:
    """Pay the moment the depth is cleared, not when you next Recurse.

    A layer that only paid on reset would mean the first descent -- which wipes
    the Substrate era and hands back nothing -- was a pure loss until the player
    guessed they were allowed to leave.
    """
    depth = s.p5_active_depth
    if depth <= 0 or s.p5_cleared:
        return
    if s.p5_alloy < p5_target(depth):
        return
    seconds = s.depth_time()
    gain = p5_gain_at(depth, seconds)
    s.p5_cleared = True
    s.p5_depth = s.p5_depth + gain
    s.p5_depth_life = s.p5_depth_life + gain
    s.p5_best_depth = max(s.p5_best_depth, depth)
    if gain > Num.from_json(s.stats.get("best_depth_gain", "0")):
        s.stats["best_depth_gain"] = gain.to_json()
    s.notice("prestige",
             f"Depth {depth} cleared in {fmt_time(seconds)}. "
             f"+{fmt(gain)} Recursion Depth "
             f"(x{p5_speed_bonus(depth, seconds):.2f} for the pace). "
             f"Recurse again to go deeper.")


def recursion_cost(ru: G.RecUpg, level: int, k: int = 1) -> Num:
    return bulk_cost(ru.base_cost, ru.cost_growth, level, k)


def recursion_affordable(s: GameState, uid: str) -> int:
    ru = G.REC_BY_ID.get(uid)
    if not ru:
        return 0
    level = int(s.p5_levels.get(uid, 0))
    return min(bulk_affordable(ru.base_cost, ru.cost_growth, level, s.p5_depth),
               _remaining_levels(level, ru.max_level))


def buy_recursion(s: GameState, uid: str, amount=1) -> int:
    ru = G.REC_BY_ID.get(uid)
    if not ru:
        return 0
    level = int(s.p5_levels.get(uid, 0))
    afford = recursion_affordable(s, uid)
    k = afford if amount == "max" else min(int(amount), afford)
    if k <= 0:
        return 0
    cost = recursion_cost(ru, level, k)
    if cost > s.p5_depth:
        k -= 1
        if k <= 0:
            return 0
        cost = recursion_cost(ru, level, k)
        if cost > s.p5_depth:
            return 0
    s.p5_depth = (s.p5_depth - cost).clamp_min(0)
    s.p5_levels[uid] = level + k
    return k


def recurse(s: GameState, depth: int) -> Num:
    """Descend to `depth`. Everything below is wiped, Substrate included."""
    depth = max(1, int(depth))
    banked = s.p5_depth
    _check_depth_clear(s)               # never leave an earned clear unpaid
    gain = s.p5_depth - banked
    m = collect_mults(s)
    # Standing Army: a share of the fleet is rebuilt on the far side. Captured
    # BEFORE the reset, because the reset is what it is surviving.
    kept_fleet = {}
    if m.keep_fleet > 0:
        share = Num(min(1.0, m.keep_fleet))
        for g in G.DEFEND_GENS:
            held = s.gens.get(g.id, ZERO)
            if held > 0:
                kept_fleet[g.id] = held * share

    s.p5_count += 1
    s.stats["recursions"] = s.stats.get("recursions", 0) + 1
    _reset_scopes(s, G.LAYER_BY_ID["p5"].wipes)
    s.p5_active_depth = depth
    s.p5_run_start = time.time()
    s.p5_alloy = ZERO
    s.p5_cleared = False
    _apply_start_bonuses(s)
    for gid, held in kept_fleet.items():
        s.gens[gid] = s.gens.get(gid, ZERO) + held
        s.bought[gid] = s.bought.get(gid, ZERO) + held
    recompute(s)

    mods = G.active_mods(depth)
    tail = ("Nothing is against you yet." if not mods else
            "Against you: " + ", ".join(mod.name for mod in mods) + ".")
    s.notice("prestige",
             f"Recursion {s.p5_count}. You are at depth {depth}. Machine costs "
             f"scale harder here, and {fmt(p5_target(depth))} Alloy gets you "
             f"out. {tail}")
    return gain


def prestige(s: GameState, layer_id: str = "p1") -> Num:
    layer = G.LAYER_BY_ID.get(layer_id)
    if not layer or not layer.implemented:
        return ZERO
    if layer_id == "p2":
        return converge(s)
    if layer_id == "p3":
        return overwrite(s)
    if layer_id == "p4":
        return collapse(s)
    if layer_id == "p5":
        # No depth given means "one deeper than the deepest you have cleared",
        # which is what the button offers and what auto-Recursion uses.
        return recurse(s, s.p5_best_depth + 1)
    gain = p1_gain(s)
    if gain <= 0:
        return ZERO

    if s.bought.get("R1", ZERO) <= 1:
        s.perm_flags.add("ach_purist")
    s.p1_sp = s.p1_sp + gain
    s.p1_sp_life = s.p1_sp_life + gain
    s.p1_count += 1
    s.stats["dispersals"] = s.stats.get("dispersals", 0) + 1
    if gain > Num.from_json(s.stats.get("best_sp_gain", "0")):
        s.stats["best_sp_gain"] = gain.to_json()
    run_alloy = s.run_life.get("alloy", ZERO)
    if run_alloy > Num.from_json(s.stats.get("best_run_alloy", "0")):
        s.stats["best_run_alloy"] = run_alloy.to_json()
    if s.run_peak_alloy_rate > Num.from_json(s.stats.get("best_alloy_rate", "0")):
        s.stats["best_alloy_rate"] = s.run_peak_alloy_rate.to_json()

    _reset_scopes(s, layer.wipes)
    _apply_start_bonuses(s)
    s.notice("prestige", f"Dispersal complete. +{fmt(gain)} Seed Points.")
    return gain


def _reset_scopes(s: GameState, wipes: tuple[str, ...]) -> None:
    """Reset by table, never by hand."""
    # Layer-scoped resources ride out a run reset; era-scoped ones ride out a
    # Convergence as well.
    carried = {}
    if G.LAYER not in wipes:
        for rid in G.LAYER_RESOURCES:
            carried[rid] = s.res.get(rid, ZERO)
    if G.COHERE not in wipes:
        for rid in G.COHERE_RESOURCES:
            carried[rid] = s.res.get(rid, ZERO)
    # Keepers -- Persistent Archive, Cached Genome -- protect for exactly as
    # long as the node that promised them survives, and not a layer less.
    #
    # This used to be a hardcoded `COHERE not in wipes`, which switched both of
    # them off from Overwrite onward even though Persistent Archive lives in
    # `p3_levels` (only a Collapse takes it) and Cached Genome lives in
    # `p4_levels` (only a Recursion takes it). Both went dormant while still
    # owned and still paid for. Asking the POST-reset state instead means the
    # rule is "you keep it if the thing that promised it survived", it needs no
    # per-layer bookkeeping, and any keeper added later inherits it.
    saved_research = s.research
    saved_seed = s.p1_levels
    fresh = GameState()
    for field, scope in RESET_SCOPE.items():
        if scope in wipes:
            value = getattr(fresh, field)
            setattr(s, field, value.copy() if hasattr(value, "copy") else value)
    for rid, held in carried.items():
        s.res[rid] = held
    surviving = collect_mults(s).flags
    if surviving.get("keep_research"):
        s.research = saved_research
    if surviving.get("keep_seed"):
        s.p1_levels = saved_seed
    s.run_start = time.time()
    s.events = []
    s.probes = []
    s.notices = []


def _apply_start_bonuses(s: GameState) -> None:
    m = collect_mults(s)
    # Always hand back a nest egg: after your first Dispersal you should never
    # have to sit and click your way out of zero again.
    base_ore = Num(G.RESTART_ORE) * Num(m.start_res.get("ore", 1.0))
    s.res["ore"] = s.res.get("ore", ZERO) + base_ore
    for rid, factor in m.start_res.items():
        if rid != "ore" and factor > 1.0:
            s.res[rid] = s.res.get(rid, ZERO) + Num(1000) * Num(factor)
    for gid, count in start_gen_counts(m).items():
        if gid in s.gens:
            s.gens[gid] = s.gens[gid] + count
            s.bought[gid] = s.bought[gid] + count
    recompute(s)


START_GEN_GROUPS = {"E": ("E1", "E2", "E3"),
                    "EARLY_E": ("E1", "E2", "E3", "E4", "E5"),
                    "EARLY_R": ("R1", "R2", "R3"),
                    "COMPILED": ("E1", "E2", "E3", "E4", "E5",
                                 "R1", "R2", "R3")}


def start_gen_counts(m: Mults) -> dict[str, float]:
    """Machines every run begins with, expanded from the group targets.

    Shared with the Defection so that "combat never takes you below your floor"
    is measured against the same table that grants the floor.  Two copies of
    this expansion would drift, and the drift would only ever show up as the
    player's Overwrite floors quietly being eaten.
    """
    out: dict[str, float] = {}
    for target, count in m.start_gen.items():
        if count <= 0:
            continue
        for gid in START_GEN_GROUPS.get(target, (target,)):
            out[gid] = out.get(gid, 0.0) + count
    return out


def hard_reset(s: GameState) -> GameState:
    from .state import new_game
    return new_game()
