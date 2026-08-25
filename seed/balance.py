"""Headless balance simulator.

Runs the real engine under a scripted "reasonable player" policy and reports
time-to-milestone.  Because the UI holds no logic, this is the same economy the
player experiences.  Not shipped with the game.

    py -m seed.balance [hours]
"""

from __future__ import annotations

import random
import sys
import time as _time

from . import engine as E
from . import gamedata as G
from .bignum import N, Num, ZERO, fmt, fmt_time
from .state import new_game

DT = 0.25
CLICKS_PER_SEC = 2.0
CLICK_UNTIL = 120.0          # a real player stops clicking once R1 exists


class Player:
    """A reasonable, not optimal, player."""

    def __init__(self, seed=1):
        self.s = new_game()
        self.rng = random.Random(seed)
        self.t = 0.0
        self.marks: dict[str, float] = {}
        self.prestige_times: list[float] = []
        self.converge_times: list[float] = []
        self.converge_start = 0.0
        self.run_start = 0.0
        self.click_debt = 0.0
        self.best_rate = 0.0

    def mark(self, key):
        if key not in self.marks:
            self.marks[key] = self.t

    # -- policy ---------------------------------------------------------
    def act(self):
        s = self.s
        m = E.recompute(s)

        # Keep the lights on first.
        if s.throttle < 0.90:
            for gid in ("E4", "E2"):
                if gid in s.unlocked and E.buy(s, gid, 5, m):
                    return

        # Buy the highest unlocked machine we can afford, preferring the
        # replication ladder because it compounds.
        for g in reversed(G.GENERATORS):
            if g.id not in s.unlocked:
                continue
            if g.ladder == G.REPLICATE and E.buy(s, g.id, 1, m):
                return
        for g in reversed(G.GENERATORS):
            if g.id in s.unlocked and E.buy(s, g.id, 1, m):
                return

    def shop(self):
        s = self.s
        for u in G.UPGRADES:
            if u.id not in s.upgrades and E.check(u.unlock, s):
                E.buy_upgrade(s, u.id)
        for t in G.RESEARCH:
            if t.id not in s.research and E.check(t.unlock, s):
                E.buy_research(s, t.id)
        for su in sorted(G.SEED_GRID, key=lambda x: x.base_cost):
            for _ in range(20):
                if not E.buy_seed(s, su.id):
                    break
        for cu in sorted(G.COHERENCE_GRID, key=lambda x: x.base_cost):
            for _ in range(20):
                if not E.buy_coherence(s, cu.id):
                    break

    def maybe_prestige(self):
        """Reset when Seed Points per second has peaked.

        This is what an optimising player actually does, and unlike a fixed
        "reset when it doubles" rule it lets the ECONOMY decide run length —
        which is the thing we are trying to measure.
        """
        s = self.s
        gain = E.p1_gain(s)
        if gain <= 0:
            return
        elapsed = max(1.0, self.t - self.run_start)
        rate = gain.to_float() / elapsed
        if s.p1_count == 0:
            # A first-time player disperses as soon as the option appears.
            E.prestige(s)
            self.prestige_times.append(elapsed)
            self.run_start = self.t
            self.best_rate = 0.0
            self.shop()
            return
        if rate > self.best_rate:
            self.best_rate = rate
            return
        if rate < self.best_rate * 0.80 and elapsed > 30:
            E.prestige(s)
            self.prestige_times.append(elapsed)
            self.run_start = self.t
            self.best_rate = 0.0
            self.shop()

    def maybe_converge(self):
        s = self.s
        gain = E.p2_gain(s)
        # Wait until a Convergence is clearly worth the much larger reset,
        # rather than firing the instant the bar is crossed.
        if gain < Num(G.P2_BASE * 2):
            return
        E.converge(s)
        self.converge_times.append(self.t - self.converge_start)
        self.converge_start = self.t
        self.run_start = self.t
        self.best_rate = 0.0
        # Pick a Doctrine in every row; a real player would not leave them empty.
        for row in G.DOCTRINE_ROWS:
            options = [d for d in G.DOCTRINES if d.row == row]
            E.choose_doctrine(s, options[0].id)
        self.shop()

    def step(self):
        s = self.s
        # A player clicks when, and only when, nothing else is producing.
        if s.rates.get("ore", ZERO) <= 0:
            self.click_debt += CLICKS_PER_SEC * DT
            clicks, self.click_debt = int(self.click_debt), self.click_debt % 1.0
            for _ in range(clicks):
                gain = Num(G.MANUAL_ORE_PER_CLICK) + (
                    s.gens.get("E1", ZERO) * N(G.GEN_BY_ID["E1"].base_rate)
                    * s.mults.get("E1", Num(1)) * N(G.MANUAL_CLICK_SCALES_WITH_E1))
                s.res["ore"] = s.res["ore"] + gain
                s.run_life["ore"] = s.run_life["ore"] + gain
                s.total_life["ore"] = s.total_life["ore"] + gain

        E.tick(s, DT, self.rng)
        self.t += DT

        for _ in range(2):
            self.act()
        self.shop()
        self.maybe_prestige()
        self.maybe_converge()
        self.record()

    def record(self):
        s = self.s
        for g in G.GENERATORS:
            if s.gens.get(g.id, ZERO) > 0:
                self.mark(f"first {g.name}")
        for rid in ("alloy", "data", "isotope"):
            if s.run_life.get(rid, ZERO) > 0 or s.total_life.get(rid, ZERO) > 0:
                self.mark(f"first {G.RES_BY_ID[rid].name}")
        for exp in (3, 6, 9, 12, 15, 18):
            if s.total_life.get("ore", ZERO) >= Num(1, exp):
                self.mark(f"1e{exp} lifetime Ore")
            if s.total_life.get("alloy", ZERO) >= Num(1, exp):
                self.mark(f"1e{exp} lifetime Alloy")
        if E.p1_available(s):
            self.mark("Dispersal available")


def report(hours=6.0, seed=1):
    p = Player(seed)
    steps = int(hours * 3600 / DT)
    wall = _time.perf_counter()
    for i in range(steps):
        p.step()
    elapsed = _time.perf_counter() - wall
    s = p.s

    print(f"=== SEED balance: {hours:g} simulated hours in {elapsed:.1f}s wall "
          f"({hours * 3600 / max(elapsed, 1e-9):.0f}x) ===\n")

    print("-- first reached --")
    for key, when in sorted(p.marks.items(), key=lambda kv: kv[1]):
        print(f"  {fmt_time(when):>10}   {key}")

    print("\n-- dispersal cadence --")
    if p.prestige_times:
        for i, dur in enumerate(p.prestige_times, 1):
            print(f"  #{i:<3} run took {fmt_time(dur)}")
        print(f"  total dispersals: {len(p.prestige_times)}")
    else:
        print("  none reached")

    print("\n-- convergence cadence --")
    if p.converge_times:
        for i, dur in enumerate(p.converge_times, 1):
            print(f"  #{i:<3} took {fmt_time(dur)}")
    else:
        print("  none reached")

    print("\n-- end state --")
    print(f"  seed points      {fmt(s.p1_sp)}  (lifetime {fmt(s.p1_sp_life)})")
    print(f"  coherence        {fmt(s.p2_coh)}  convergences {s.p2_count}")
    print(f"  nanite mass      {fmt(s.res.get('nanite'))}")
    print(f"  throttle         {s.throttle * 100:.0f}%")
    print(f"  milestones       {len(s.milestones)}/{len(G.MILESTONES)}")
    print(f"  achievements     {len(s.achievements)}/{len(G.ACHIEVEMENTS)}")
    print(f"  upgrades         {len(s.upgrades)}/{len(G.UPGRADES)}")
    print(f"  research         {len(s.research)}/{len(G.RESEARCH)}")
    print(f"  artifacts        {len(s.artifacts)}")
    print(f"  anomalies        {s.stats['anomalies_seen']}")

    print("\n-- machine counts and share of output --")
    total_by_res: dict[str, Num] = {}
    contrib: dict[str, Num] = {}
    for g in G.GENERATORS:
        c = s.gens.get(g.id, ZERO)
        out = c * N(g.base_rate) * s.mults.get(g.id, Num(1))
        contrib[g.id] = out
        if g.produces in G.RES_BY_ID:
            total_by_res[g.produces] = total_by_res.get(g.produces, ZERO) + out
    for g in G.GENERATORS:
        c = s.gens.get(g.id, ZERO)
        share = ""
        if g.produces in G.RES_BY_ID and total_by_res.get(g.produces, ZERO) > 0:
            pct = (contrib[g.id] / total_by_res[g.produces]).to_float() * 100
            share = f"{pct:5.1f}% of {G.RES_BY_ID[g.produces].name}"
        print(f"  {g.id:<3} {g.name:<20} owned {fmt(c):>10}  "
              f"bought {fmt(s.bought.get(g.id, ZERO)):>8}  {share}")

    print("\n-- resources --")
    for rid in G.STOCK_RESOURCES:
        print(f"  {G.RES_BY_ID[rid].name:<10} {fmt(s.res[rid]):>12}  "
              f"rate {fmt(s.rates.get(rid, ZERO)):>12}/s  "
              f"lifetime {fmt(s.total_life[rid])}")
    return p


if __name__ == "__main__":
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    report(hours)
