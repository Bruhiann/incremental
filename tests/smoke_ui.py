"""Drive the real Tk app headlessly-ish: build it, tick it, visit every tab.

Not part of the unittest suite (it needs a display); run it directly.
"""

import os
import sys
import tempfile

_tmp = tempfile.TemporaryDirectory()
os.environ["LOCALAPPDATA"] = _tmp.name

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402

from seed import engine as E  # noqa: E402
from seed import gamedata as G  # noqa: E402
from seed import saveman  # noqa: E402
from seed.bignum import N, ZERO, fmt  # noqa: E402
from seed.ui import App  # noqa: E402


def pump(root, n=6):
    for _ in range(n):
        root.update_idletasks()
        root.update()


def step(app, root, n, dt=0.1):
    """Advance the model n ticks and refresh.

    Deliberately NOT app.tick(): that reschedules itself via after(), so calling
    it in a loop piles up callbacks that the real game never creates -- the
    scheduler only ever has one outstanding. app.tick() is exercised separately.
    """
    for _ in range(n):
        E.tick(app.state, dt)
    app.refresh()
    pump(root, 2)


def main():
    root = tk.Tk()
    app = App(root)
    s = app.state
    pump(root)
    print(f"tabs at start: {app.visible_tabs}")
    assert app.visible_tabs == ["production", "stats"], app.visible_tabs

    # Early game: click, buy, verify the button actually spends.
    for _ in range(40):
        app.manual()
    app.refresh()
    pump(root)
    assert s.res["ore"] > ZERO
    # Exercise the real scheduled tick path once (it reschedules itself).
    before_ticks = app.ticks
    app.tick()
    pump(root)
    assert app.ticks == before_ticks + 1, "the game loop did not advance"
    app.buy("E1")
    assert s.gens["E1"] > ZERO, "manual buy did nothing"
    print(f"after 40 clicks + 1 buy: ore={fmt(s.res['ore'])} E1={fmt(s.gens['E1'])}")

    # Fast-forward a wealthy mid-game state and unlock everything visible.
    for rid, amount in (("ore", 1e14), ("alloy", 1e11), ("data", 1e8), ("isotope", 1e5)):
        s.res[rid] = N(amount)
        s.run_life[rid] = N(amount)
        s.total_life[rid] = N(amount)
    s.research.add("r_probes")
    s.research.add("r_foreman")
    E.recompute(s)

    for gid in ("E1", "E2", "E3", "E4", "E5", "E6", "R1", "R2", "R3"):
        E.buy(s, gid, 30)
    app.buy_amount.set("Max")
    app.refresh()
    pump(root)

    # Every tab must build and refresh without raising.
    step(app, root, 30)
    print(f"tabs now: {app.visible_tabs}")
    for tab_id in app.visible_tabs:
        for index, tab in enumerate(G.TABS):
            if tab.id == tab_id:
                break
        app.nb.select(app.frames[tab_id])
        pump(root)
        app.refresh()
        pump(root)
        print(f"  refreshed tab: {tab_id}")

    # Exploration interactions.
    app.nb.select(app.frames["exploration"])
    E.launch_probe(s, "near")
    app.refresh()
    pump(root)
    for _ in range(5):
        E._roll_artifact(s, G.TARGETS[0], E._rng(s))
    app.refresh()
    pump(root)
    first = s.artifacts[0]["id"]
    app._toggle_equip(first)
    app._toggle_equip(first)
    print(f"  artifacts={len(s.artifacts)} equipped={len(s.equipped)}")

    # Automation toggles.
    app.nb.select(app.frames["automation"])
    app.auto_master.set(True)
    app._auto_master_changed()
    app.auto_vars["E1"].set(True)
    app._auto_gen_changed("E1")
    app.reserve_entries["ore"].delete(0, "end")
    app.reserve_entries["ore"].insert(0, "1e12")
    app._reserve_changed("ore")
    step(app, root, 20)
    assert s.res["ore"] >= N(1e12), "auto-buy spent through the reserve"
    print(f"  auto-buy respected reserve: ore={fmt(s.res['ore'])}")

    # Prestige without the modal dialog.
    s.settings["confirm_prestige"] = False
    s.run_life["alloy"] = E.p1_required(s) * N(1e3)
    app.nb.select(app.frames["prestige"])
    app.refresh()
    pump(root)
    gain = E.p1_gain(s)
    app.do_prestige()
    pump(root)
    assert s.p1_sp == gain and s.p1_count == 1, (fmt(s.p1_sp), fmt(gain))
    assert s.gens["E1"] == ZERO and "r_probes" in s.research
    print(f"  dispersed: +{fmt(gain)} SP, machines cleared, research kept")

    # Seed grid: the buy-amount selector drives bulk purchases.
    s.p1_sp = N(1e12)          # enough that 1/10/25 are all fully affordable
    for amount, expect in (("1", 1), ("10", 11), ("25", 36)):
        app.seed_amount.set(amount)
        app.refresh(); pump(root)
        app._buy_seed("sg_global")
        assert s.p1_levels["sg_global"] == expect, (amount, s.p1_levels["sg_global"])
    app.seed_amount.set("Max")
    app.refresh(); pump(root)
    app._buy_seed("sg_global")
    assert E.seed_affordable(s, "sg_global") == 0, "Max left something affordable"
    assert s.p1_sp >= ZERO
    print(f"  seed grid 1/10/25/Max -> sg_global level={s.p1_levels['sg_global']}")

    # A capped node must never overshoot its cap.
    app._buy_seed("sg_cheap")
    assert s.p1_levels["sg_cheap"] <= G.SEED_BY_ID["sg_cheap"].max_level
    print(f"  capped node respected cap: sg_cheap={s.p1_levels['sg_cheap']}"
          f"/{G.SEED_BY_ID['sg_cheap'].max_level}")

    # --- Convergence (prestige layer 2) --------------------------------
    s.p1_sp_life = E.p2_required(s) * N(1e4)
    app.refresh()
    pump(root)
    assert "convergence" in app.visible_tabs, app.visible_tabs
    app.nb.select(app.frames["convergence"])
    app.refresh()
    pump(root)
    coh = E.p2_gain(s)
    app.do_converge()
    pump(root)
    assert s.p2_count == 1 and s.p2_coh == coh, (s.p2_count, fmt(s.p2_coh), fmt(coh))
    assert s.p1_sp == ZERO and s.p1_levels == {} and s.research == set(), "P2 under-reset"
    assert s.p1_count == 1, "machine tiers unlocked by Dispersal must survive"
    print(f"  converged: +{fmt(coh)} Coherence, Seed Grid and Research wiped")

    app.refresh()
    pump(root)
    app._choose_doctrine("d1_swarm")
    app._choose_doctrine("d1_forge")          # same row replaces
    app._choose_doctrine("d3_mind")
    assert s.doctrines == {1: "d1_forge", 3: "d3_mind"}, s.doctrines
    s.p2_coh = N(1e12)
    for amount, expect in (("1", 1), ("10", 11), ("25", 36)):
        app.coh_amount.set(amount)
        app.refresh(); pump(root)
        app._buy_coh("c_global")
        assert s.p2_levels["c_global"] == expect, (amount, s.p2_levels["c_global"])
    app.coh_amount.set("Max")
    app.refresh(); pump(root)
    app._buy_coh("c_global")
    assert E.coherence_affordable(s, "c_global") == 0
    assert s.p2_coh >= ZERO
    s.p2_coh = N(1e12)
    app._buy_coh("c_autoprestige")
    assert s.p2_levels["c_autoprestige"] == 1, "flat-priced node overshot its cap"
    app.refresh(); pump(root)
    print(f"  coherence 1/10/25/Max -> c_global level={s.p2_levels['c_global']}")
    print(f"  doctrines={s.doctrines} nodes={sorted(s.p2_levels)}")

    # Nanites should now exist and compound.
    E.recompute(s)
    assert s.has_flag("nanites")
    s.res["nanite"] = N(1e6)
    step(app, root, 20)
    assert s.res["nanite"] > N(1e6), "nanites did not compound"
    print(f"  nanites compounding: {fmt(s.res['nanite'])}")

    # Auto-upgrades and auto-relics via the Seed Grid.
    s.p1_levels["sg_autoupg"] = 1
    s.p1_levels["sg_autorelic"] = 1
    s.auto["upgrades"] = True
    s.auto["relics"] = True
    for rid, amount in (("ore", 1e14), ("alloy", 1e11)):
        s.res[rid] = N(amount)
        s.run_life[rid] = N(amount)
    s.auto["reserve"]["ore"] = "0"
    E.recompute(s)
    for gid in ("E1", "E2", "E3", "E4", "E5", "E6"):
        E.buy(s, gid, 30)
    E.recompute(s)
    before_upg = len(s.upgrades)
    step(app, root, 30)
    assert len(s.upgrades) > before_upg, "auto-upgrade bought nothing"
    print(f"  auto-upgrades bought {len(s.upgrades) - before_upg} upgrades")

    s.artifacts.append({"id": "smoke_best", "name": "Smoke Core",
                        "kind": G.MULT_GLOBAL, "target": "", "value": 25.0,
                        "rarity": "cosmic", "desc": "+2400% to everything."})
    step(app, root, 5)
    assert "smoke_best" in s.equipped, "auto-relic did not slot the best artifact"
    app.nb.select(app.frames["exploration"])
    app.refresh()
    pump(root)
    app.optimise_relics()
    pump(root)
    print(f"  best relic auto-slotted; loadout size {len(s.equipped)}")

    # Standing Seed Orders: the Seed Grid buys itself.
    s.p2_coh = N(1e6)
    app.coh_amount.set("1")
    app.refresh(); pump(root)
    app._buy_coh("c_autoseed")
    assert s.p2_levels.get("c_autoseed") == 1, "could not buy Standing Seed Orders"
    E.recompute(s)
    var, cb, flag = app.standing["seed"]
    var.set(True); app._standing_changed("seed", var)
    s.p1_levels.clear()
    s.p1_sp = N(1e6)
    step(app, root, 40)
    assert s.p1_levels, "auto-seed bought nothing"
    assert s.p1_sp < N(1e6) and s.p1_sp >= ZERO
    for su in G.SEED_GRID:
        assert s.p1_levels.get(su.id, 0) <= su.max_level, su.id
    print(f"  auto-seed bought {sum(s.p1_levels.values())} levels across "
          f"{len(s.p1_levels)} nodes, {fmt(s.p1_sp)} SP left")

    app.nb.select(app.frames["automation"])
    app.refresh(); pump(root)
    assert str(cb.cget("state")) == "normal", "auto-seed checkbox still locked"
    print("  auto-Seed Grid control enabled")

    # Auto-Dispersal became available via the Coherence node.
    app.nb.select(app.frames["automation"])
    app.refresh()
    pump(root)
    assert str(app.autop_cb.cget("state")) == "normal", "auto-Dispersal still locked"
    print("  auto-Dispersal control enabled")

    # Save/close path.
    app.save_now()
    assert saveman.save_path().exists()
    reloaded, status = saveman.load()
    assert status == "loaded" and reloaded.p1_count == 1
    print(f"  saved and reloaded: status={status} dispersals={reloaded.p1_count}")

    root.destroy()
    print("\nSMOKE OK")


if __name__ == "__main__":
    main()
