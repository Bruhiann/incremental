"""Tkinter interface.

The UI computes nothing.  Widgets are created once and cached; refresh only
mutates text.  Rebuilding rows every frame is the standard way a Tkinter
incremental ends up freezing, so it is never done here.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import engine as E
from . import gamedata as G
from . import saveman
from .bignum import N, Num, ZERO, fmt, fmt_time
from .state import new_game, seed_from_text

BG = "#12151c"
BG2 = "#1a1f2a"
BG3 = "#232937"
FG = "#d7dde8"
DIM = "#8b93a3"
ACCENT = "#5aa9e6"
GOLD = "#d8a83f"
GREEN = "#4ea36a"
YELLOW = "#c9a227"
RED = "#c05050"
VIOLET = "#9a6fd0"
CRIMSON = "#d8506f"
CYAN = "#4fd6c8"

F = ("Segoe UI", 9)
FB = ("Segoe UI", 9, "bold")
FH = ("Segoe UI", 13, "bold")
FMONO = ("Consolas", 9)


class Tooltip:
    """One shared tooltip window; content is set per hover."""

    def __init__(self, root):
        self.root = root
        self.win = None
        self.label = None

    def show(self, widget, text):
        if not text:
            return
        self.hide()
        self.win = tk.Toplevel(self.root)
        self.win.wm_overrideredirect(True)
        self.win.configure(bg=BG3)
        self.label = tk.Label(self.win, text=text, justify="left", bg=BG3, fg=FG,
                              font=F, padx=8, pady=6, relief="solid", borderwidth=1)
        self.label.pack()
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        self.win.wm_geometry(f"+{x}+{y}")

    def hide(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None

    def attach(self, widget, provider):
        widget.bind("<Enter>", lambda _e: self.show(widget, provider()), add="+")
        widget.bind("<Leave>", lambda _e: self.hide(), add="+")


def is_packed(widget) -> bool:
    """Whether the widget is managed by pack right now.

    NOT winfo_ismapped(): that reports on-screen visibility, which is False for
    every widget on a tab the player is not currently looking at. Using it for
    show/hide logic meant rows were re-packed (and so re-ordered) whenever their
    tab happened to be in the background.
    """
    return bool(widget.winfo_manager())


def pack_ordered(widget, later_widgets, **kw):
    """Pack `widget` before the first still-visible widget that follows it.

    Tk appends on pack(), so a row that is hidden and later re-shown lands at
    the bottom regardless of where it belongs. Machines unlock at different
    times, so without this the Production list drifts out of order and rows end
    up under the wrong ladder heading.
    """
    for candidate in later_widgets:
        if is_packed(candidate):
            widget.pack(before=candidate, **kw)
            return
    widget.pack(**kw)


def scrollable(parent):
    """A vertically scrollable frame. Returns the inner frame."""
    canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
    bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=BG)
    inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")

    def wheel(event):
        canvas.yview_scroll(int(-event.delta / 120), "units")
    canvas.bind_all("<MouseWheel>", wheel, add="+")
    return inner


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.state, status = saveman.load()
        self.state.stats["sessions"] = self.state.stats.get("sessions", 0) + 1
        E.recompute(self.state)

        root.title(f"{G.GAME_NAME} — a self-replicating machine")
        root.geometry("1040x720")
        root.minsize(880, 600)
        root.configure(bg=BG)

        self._style()
        self.tip = Tooltip(root)
        self.buy_amount = tk.StringVar(value=self.state.settings.get("buy_amount", "1"))
        self.visible_tabs: list[str] = []
        self.frames: dict[str, tk.Frame] = {}
        self.widgets: dict[str, tk.Widget] = {}
        self.log_lines: list[str] = []

        self._build_header()
        self._build_notebook()
        self._build_log()

        self.last = time.perf_counter()
        self.ticks = 0
        self.autosave_in = G.AUTOSAVE_SECONDS
        self.save_flash = 0.0

        if status == "backup":
            self.log("Main save was unreadable — restored from backup.", "warn")
        elif status == "new" and self.state.p1_count == 0:
            self.log("Welcome. You are one damaged probe on a nickel-iron asteroid.", "major")
            self.log("Scrape some regolith to begin.", "info")
        else:
            self.log("Save loaded.", "info")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh()
        self.root.after(G.TICK_MS, self.tick)

    # -- chrome ----------------------------------------------------------
    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=BG2, foreground=DIM,
                     padding=(14, 7), font=FB, borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", BG3)],
               foreground=[("selected", FG)])
        st.configure("TScrollbar", background=BG3, troughcolor=BG,
                     borderwidth=0, arrowcolor=DIM)
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BG3,
                     borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT)

    def _build_header(self):
        head = tk.Frame(self.root, bg=BG2)
        head.pack(fill="x", side="top")

        res_row = tk.Frame(head, bg=BG2)
        res_row.pack(fill="x", padx=12, pady=(9, 4))
        self.res_labels = {}
        for r in G.RESOURCES:
            if r.kind != G.STOCK:
                continue
            box = tk.Frame(res_row, bg=BG2)
            name = tk.Label(box, text=r.name, bg=BG2, fg=DIM, font=F)
            name.pack(anchor="w")
            value = tk.Label(box, text="0", bg=BG2, fg=FG, font=("Segoe UI", 14, "bold"))
            value.pack(anchor="w")
            rate = tk.Label(box, text="", bg=BG2, fg=GREEN, font=F)
            rate.pack(anchor="w")
            self.res_labels[r.id] = (box, value, rate)
            self.tip.attach(box, lambda rr=r: f"{rr.name}\n{rr.desc}")

        power = tk.Frame(head, bg=BG2)
        power.pack(fill="x", padx=12, pady=(0, 4))
        self.power_label = tk.Label(power, text="", bg=BG2, fg=FG, font=FB)
        self.power_label.pack(side="left")
        self.power_hint = tk.Label(power, text="", bg=BG2, fg=YELLOW, font=F)
        self.power_hint.pack(side="left", padx=(10, 0))
        self.power_canvas = tk.Canvas(power, height=8, bg=BG3, highlightthickness=0)
        self.power_canvas.pack(fill="x", pady=(3, 0))
        self.power_bar = self.power_canvas.create_rectangle(0, 0, 0, 8,
                                                            fill=GREEN, width=0)
        self.tip.attach(power, lambda: (
            "Power is never stockpiled: supply must meet demand.\n"
            "If demand exceeds supply everything except power generation\n"
            "slows to supply/demand, floored at 10%. Build more power."))

        goal = tk.Frame(head, bg=BG2)
        goal.pack(fill="x", padx=12, pady=(2, 8))
        self.goal_label = tk.Label(goal, text="", bg=BG2, fg=ACCENT, font=F, anchor="w")
        self.goal_label.pack(side="left")
        self.clock_label = tk.Label(goal, text="", bg=BG2, fg=DIM, font=F)
        self.clock_label.pack(side="right")

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(6, 4))
        builders = {
            "production": self._build_production,
            "upgrades": self._build_upgrades,
            "research": self._build_research,
            "exploration": self._build_exploration,
            "prestige": self._build_prestige,
            "convergence": self._build_convergence,
            "overwrite": self._build_overwrite,
            "substrate": self._build_substrate,
            "automation": self._build_automation,
            "stats": self._build_stats,
        }
        for tab in G.TABS:
            frame = tk.Frame(self.nb, bg=BG)
            self.frames[tab.id] = frame
            builders[tab.id](frame)

    def _build_log(self):
        wrap = tk.Frame(self.root, bg=BG2)
        wrap.pack(fill="x", side="bottom")
        self.log_widget = tk.Text(wrap, height=4, bg=BG2, fg=DIM, font=FMONO,
                                  wrap="word", relief="flat", padx=10, pady=6,
                                  state="disabled")
        self.log_widget.pack(fill="x")
        for tag, colour in (("info", DIM), ("major", GOLD), ("event", ACCENT),
                            ("warn", RED), ("good", GREEN)):
            self.log_widget.tag_configure(tag, foreground=colour)

    def log(self, text: str, tag: str = "info"):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text + "\n", tag)
        lines = int(self.log_widget.index("end-1c").split(".")[0])
        if lines > 200:
            self.log_widget.delete("1.0", f"{lines - 200}.0")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    # -- production ------------------------------------------------------
    def _build_production(self, parent):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=10, pady=(8, 4))
        self.manual_btn = tk.Button(bar, text="Scrape Regolith", command=self.manual,
                                    bg=BG3, fg=FG, font=FB, relief="flat",
                                    activebackground=ACCENT, cursor="hand2",
                                    padx=14, pady=6)
        self.manual_btn.pack(side="left")
        tk.Label(bar, text="Buy", bg=BG, fg=DIM, font=F).pack(side="left", padx=(18, 6))
        for amount in ("1", "10", "25", "Max"):
            tk.Radiobutton(bar, text=amount, value=amount, variable=self.buy_amount,
                           bg=BG, fg=FG, selectcolor=BG3, font=F, indicatoron=False,
                           width=4, relief="flat", activebackground=ACCENT,
                           cursor="hand2", command=self._remember_amount).pack(side="left", padx=2)

        body = tk.Frame(parent, bg=BG)
        body.pack(fill="both", expand=True)
        inner = scrollable(body)

        self.gen_rows = {}
        for ladder, title in ((G.EXTRACT, "Extraction — machines that make things"),
                              (G.REPLICATE, "Replication — machines that make machines")):
            header = tk.Label(inner, text=title, bg=BG, fg=ACCENT, font=FB, anchor="w")
            header.pack(fill="x", padx=10, pady=(10, 2))
            self.gen_rows[f"hdr_{ladder}"] = header
            for g in G.GENERATORS:
                if g.ladder == ladder:
                    self.gen_rows[g.id] = self._gen_row(inner, g)

    def _gen_row(self, parent, g: G.Gen):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", padx=10, pady=2)
        left = tk.Frame(row, bg=BG2)
        left.pack(side="left", fill="x", expand=True, padx=10, pady=7)

        title = tk.Label(left, text=g.name, bg=BG2, fg=FG, font=FB, anchor="w")
        title.pack(fill="x")
        detail = tk.Label(left, text="", bg=BG2, fg=DIM, font=F, anchor="w")
        detail.pack(fill="x")
        pips = tk.Label(left, text="", bg=BG2, fg=GOLD, font=FMONO, anchor="w")
        pips.pack(fill="x")

        right = tk.Frame(row, bg=BG2)
        right.pack(side="right", padx=10)
        cost = tk.Label(right, text="", bg=BG2, fg=FG, font=F)
        cost.pack()
        btn = tk.Button(right, text="Buy", width=10, bg=BG3, fg=FG, font=FB,
                        relief="flat", activebackground=ACCENT, cursor="hand2",
                        command=lambda gid=g.id: self.buy(gid))
        btn.pack(pady=(3, 0))

        self.tip.attach(row, lambda gg=g: self._gen_tip(gg))
        return {"row": row, "title": title, "detail": detail, "pips": pips,
                "cost": cost, "btn": btn}

    def _rows_after(self, key):
        """Generator rows and headers that should sit below `key`."""
        keys = list(self.gen_rows)
        out = []
        for later in keys[keys.index(key) + 1:]:
            w = self.gen_rows[later]
            out.append(w["row"] if isinstance(w, dict) else w)
        return out

    def _gen_tip(self, g: G.Gen) -> str:
        s = self.state
        lines = [g.name, g.desc, ""]
        if g.produces in G.RES_BY_ID:
            lines.append(f"Each one makes {g.base_rate:g} {G.RES_BY_ID[g.produces].name}/s "
                         f"before multipliers.")
        elif g.produces:
            lines.append(f"Each one builds {g.base_rate:g} {G.GEN_BY_ID[g.produces].name}/s "
                         f"before multipliers.")
        if g.draw:
            lines.append(f"Draws {fmt(N(g.draw) * s.gens.get(g.id, ZERO))} Power in total.")
        if g.upkeep:
            res, per = g.upkeep
            lines.append(f"Upkeep {fmt(N(per) * s.gens.get(g.id, ZERO))} "
                         f"{G.RES_BY_ID[res].name}/s.")
            eff = s.upkeep_eff.get(g.id)
            if eff is not None and eff < 0.999:
                lines.append(f"IDLED to {eff * 100:.0f}% — not enough "
                             f"{G.RES_BY_ID[res].name} income.")
        for res_id, per in g.consumes:
            m = E.collect_mults(s)
            capture = min(G.MAX_CAPTURE,
                          E._capture(s.gens.get(g.id, ZERO), min(0.95, per * m.capture)))
            lines.append(f"Diverts {capture * 100:.1f}% of your "
                         f"{G.RES_BY_ID[res_id].name} income "
                         f"(never more than {G.MAX_CAPTURE * 100:.0f}%, so some "
                         f"always reaches you).")
        parts = s.breakdown.get(g.id) or []
        if parts:
            lines.append("")
            lines.append("Multipliers:")
            for label, value in parts:
                lines.append(f"   {label}: x{value:,.3g}")
            lines.append(f"   = x{s.mults.get(g.id, Num(1)).to_float():,.4g} total")
        return "\n".join(lines)

    def _remember_amount(self):
        self.state.settings["buy_amount"] = self.buy_amount.get()
        if hasattr(self, "seed_amount"):
            self.state.settings["seed_buy_amount"] = self.seed_amount.get()
        if hasattr(self, "coh_amount"):
            self.state.settings["coh_buy_amount"] = self.coh_amount.get()
        if hasattr(self, "over_amount"):
            self.state.settings["over_buy_amount"] = self.over_amount.get()
        if hasattr(self, "sub_amount"):
            self.state.settings["sub_buy_amount"] = self.sub_amount.get()

    def manual(self):
        s = self.state
        gain = Num(G.MANUAL_ORE_PER_CLICK) + (
            s.gens.get("E1", ZERO) * N(G.GEN_BY_ID["E1"].base_rate)
            * s.mults.get("E1", Num(1)) * N(G.MANUAL_CLICK_SCALES_WITH_E1))
        s.res["ore"] = s.res["ore"] + gain
        s.run_life["ore"] = s.run_life["ore"] + gain
        s.total_life["ore"] = s.total_life["ore"] + gain

    def buy(self, gid: str):
        amount = self.buy_amount.get()
        got = E.buy(self.state, gid, "max" if amount == "Max" else int(amount))
        if got:
            self.refresh()

    # -- upgrades / research --------------------------------------------
    def _build_upgrades(self, parent):
        inner = scrollable(parent)
        tk.Label(inner, text="Upgrades are permanent for this run, and are reset by "
                             "Dispersal.", bg=BG, fg=DIM, font=F, anchor="w"
                 ).pack(fill="x", padx=10, pady=(10, 4))
        self.upg_cards = {}
        for u in G.UPGRADES:
            self.upg_cards[u.id] = self._card(
                inner, u.name, u.desc,
                lambda uid=u.id: self._buy_upgrade(uid), gold=u.major)

    def _build_research(self, parent):
        inner = scrollable(parent)
        tk.Label(inner, text="Research is bought with Data and survives Dispersal.",
                 bg=BG, fg=DIM, font=F, anchor="w").pack(fill="x", padx=10, pady=(10, 4))
        self.tech_cards = {}
        for t in G.RESEARCH:
            self.tech_cards[t.id] = self._card(
                inner, t.name, t.desc,
                lambda tid=t.id: self._buy_research(tid), gold=t.major)

    def _amount_strip(self, parent, var, label):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(bar, text=label, bg=BG, fg=DIM, font=F).pack(side="left", padx=(0, 6))
        for amount in ("1", "10", "25", "Max"):
            tk.Radiobutton(bar, text=amount, value=amount, variable=var,
                           bg=BG, fg=FG, selectcolor=BG3, font=F, indicatoron=False,
                           width=4, relief="flat", activebackground=ACCENT,
                           cursor="hand2", command=self._remember_amount
                           ).pack(side="left", padx=2)
        return bar

    def _shop_button(self, card, level, cap, cost, currency, k, affordable, colour):
        """Shared button text for the two prestige shops."""
        suffix = f"  [{level}{cap}]"
        label = f"{fmt(cost)} {currency}" + (f"  x{k}" if k > 1 else "") + suffix
        card["btn"].config(text=label,
                           state="normal" if affordable else "disabled",
                           bg=colour if affordable else BG3,
                           fg="#12151c" if affordable else DIM)

    def _card(self, parent, name, desc, command, gold=False):
        row = tk.Frame(parent, bg=BG2, highlightthickness=1,
                       highlightbackground=GOLD if gold else BG2)
        row.pack(fill="x", padx=10, pady=2)
        left = tk.Frame(row, bg=BG2)
        left.pack(side="left", fill="x", expand=True, padx=10, pady=7)
        tk.Label(left, text=name, bg=BG2, fg=GOLD if gold else FG, font=FB,
                 anchor="w").pack(fill="x")
        tk.Label(left, text=desc, bg=BG2, fg=DIM, font=F, anchor="w",
                 wraplength=640, justify="left").pack(fill="x")
        btn = tk.Button(row, text="", width=16, bg=BG3, fg=FG, font=FB, relief="flat",
                        activebackground=ACCENT, cursor="hand2", command=command)
        btn.pack(side="right", padx=10)
        return {"row": row, "btn": btn}

    def _buy_upgrade(self, uid):
        if E.buy_upgrade(self.state, uid):
            self.refresh()

    def _buy_research(self, tid):
        if E.buy_research(self.state, tid):
            self.refresh()

    # -- exploration -----------------------------------------------------
    def _build_exploration(self, parent):
        inner = scrollable(parent)
        tk.Label(inner, text="Probes run in parallel and never block anything else.",
                 bg=BG, fg=DIM, font=F, anchor="w").pack(fill="x", padx=10, pady=(10, 4))

        self.probe_frame = tk.Frame(inner, bg=BG)
        self.probe_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.probe_labels = []
        for i in range(12):
            lbl = tk.Label(self.probe_frame, text="", bg=BG2, fg=DIM, font=FMONO,
                           anchor="w", padx=10, pady=5)
            self.probe_labels.append(lbl)

        tk.Label(inner, text="Targets", bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(8, 2))
        self.target_rows = {}
        for t in G.TARGETS:
            self.target_rows[t.id] = self._card(
                inner, t.name, t.desc, lambda tid=t.id: self._launch(tid))

        tk.Label(inner, text="Relic Frame", bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(12, 2))
        relic_head = tk.Frame(inner, bg=BG)
        relic_head.pack(fill="x", padx=10)
        self.relic_note = tk.Label(relic_head, text="", bg=BG, fg=DIM, font=F, anchor="w")
        self.relic_note.pack(side="left")
        tk.Button(relic_head, text="Slot my best relics", bg=BG3, fg=FG, font=F,
                  relief="flat", cursor="hand2", padx=10, pady=3,
                  command=self.optimise_relics).pack(side="right")
        self.artifact_box = tk.Frame(inner, bg=BG)
        self.artifact_box.pack(fill="x", padx=10, pady=4)
        self.artifact_rows = {}
        self.vault_note = tk.Label(inner, text="", bg=BG, fg=DIM, font=F, anchor="w")
        self.vault_note.pack(fill="x", padx=10)

        self.crucible_head = tk.Label(inner, text="The Crucible", bg=BG, fg=ACCENT,
                                      font=FB, anchor="w")
        self.crucible_head.pack(fill="x", padx=10, pady=(14, 2))
        self.crucible_note = tk.Label(
            inner, text="", bg=BG, fg=DIM, font=F, anchor="w",
            wraplength=900, justify="left")
        self.crucible_note.pack(fill="x", padx=10)
        self.crucible_box = tk.Frame(inner, bg=BG)
        self.crucible_box.pack(fill="x", padx=10, pady=4)
        self.crucible_rows = {}
        for rarity in G.RARITY[:-1]:
            row = tk.Frame(self.crucible_box, bg=BG2)
            label = tk.Label(row, text="", bg=BG2, fg=FG, font=F, anchor="w",
                             padx=10, pady=5)
            label.pack(side="left", fill="x", expand=True)
            btn = tk.Button(row, text="", width=14, bg=BG3, fg=FG, font=F,
                            relief="flat", cursor="hand2",
                            command=lambda r=rarity.id: self._fuse(r))
            btn.pack(side="right", padx=8)
            self.crucible_rows[rarity.id] = {"row": row, "label": label, "btn": btn}
        self.fuse_all_btn = tk.Button(
            inner, text="Fuse everything spare", bg=BG3, fg=FG, font=FB,
            relief="flat", cursor="hand2", padx=12, pady=5,
            command=self._fuse_all)
        self.fuse_all_btn.pack(anchor="w", padx=10, pady=(4, 10))

    def _launch(self, tid):
        if E.launch_probe(self.state, tid):
            self.refresh()

    def optimise_relics(self):
        s = self.state
        if E.auto_equip(s):
            names = [next(a["name"] for a in s.artifacts if a["id"] == i)
                     for i in s.equipped]
            self.log("Relics re-slotted: " + (", ".join(names) or "none"), "good")
        else:
            self.log("Your relics are already the best set you own.", "info")
        self.refresh()

    def _fuse(self, rarity_id):
        made = E.fuse(self.state, rarity_id, "max")
        if made:
            names = ", ".join(a["name"] for a in made[:3])
            extra = f" (+{len(made) - 3} more)" if len(made) > 3 else ""
            self.log(f"Fused {len(made) * G.FUSE_COUNT} spare relics into "
                     f"{len(made)}: {names}{extra}", "major")
            self.refresh()

    def _fuse_all(self):
        made = E.fuse_all(self.state)
        if made:
            self.log(f"The Crucible produced {made} better relics.", "major")
        else:
            self.log("Nothing spare to fuse — you need "
                     f"{G.FUSE_COUNT} of one rarity you are not using.", "info")
        self.refresh()

    def _toggle_equip(self, art_id):
        s = self.state
        if art_id in s.equipped:
            E.unequip(s, art_id)
        else:
            E.equip(s, art_id)
        self.refresh()

    # -- prestige --------------------------------------------------------
    def _build_prestige(self, parent):
        inner = scrollable(parent)
        top = tk.Frame(inner, bg=BG2)
        top.pack(fill="x", padx=10, pady=10)
        self.p1_title = tk.Label(top, text="Dispersal", bg=BG2, fg=GOLD, font=FH,
                                 anchor="w")
        self.p1_title.pack(fill="x", padx=12, pady=(10, 2))
        self.p1_body = tk.Label(top, text="", bg=BG2, fg=FG, font=F, anchor="w",
                                justify="left", wraplength=900)
        self.p1_body.pack(fill="x", padx=12)
        self.p1_btn = tk.Button(top, text="Disperse", bg=GOLD, fg="#12151c", font=FB,
                                relief="flat", cursor="hand2", padx=20, pady=8,
                                command=self.do_prestige)
        self.p1_btn.pack(anchor="w", padx=12, pady=10)

        tk.Label(inner, text="Seed Grid — permanent, paid for with Seed Points",
                 bg=BG, fg=ACCENT, font=FB, anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        self.seed_amount = tk.StringVar(
            value=self.state.settings.get("seed_buy_amount", "1"))
        self._amount_strip(inner, self.seed_amount, "Buy")
        self.seed_cards = {}
        for su in G.SEED_GRID:
            self.seed_cards[su.id] = self._card(
                inner, su.name, su.desc, lambda sid=su.id: self._buy_seed(sid))

        tk.Label(inner, text="Later layers", bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(14, 2))
        for layer in G.LAYERS[4:]:
            tk.Label(inner, text=f"{layer.name} — {layer.currency_name} — locked",
                     bg=BG2, fg=DIM, font=F, anchor="w", padx=10, pady=6
                     ).pack(fill="x", padx=10, pady=2)

    def _buy_seed(self, sid):
        amount = self.seed_amount.get()
        if E.buy_seed(self.state, sid, "max" if amount == "Max" else int(amount)):
            self.refresh()

    # -- convergence -----------------------------------------------------
    def _build_convergence(self, parent):
        inner = scrollable(parent)
        top = tk.Frame(inner, bg=BG2)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Convergence", bg=BG2, fg=VIOLET, font=FH, anchor="w"
                 ).pack(fill="x", padx=12, pady=(10, 2))
        self.p2_body = tk.Label(top, text="", bg=BG2, fg=FG, font=F, anchor="w",
                                justify="left", wraplength=900)
        self.p2_body.pack(fill="x", padx=12)
        self.p2_btn = tk.Button(top, text="Converge", bg=VIOLET, fg="#12151c", font=FB,
                                relief="flat", cursor="hand2", padx=20, pady=8,
                                command=self.do_converge)
        self.p2_btn.pack(anchor="w", padx=12, pady=10)

        tk.Label(inner, text="Doctrines — pick one per row. Free, switchable at "
                             "any time, and kept through a Convergence, so no "
                             "choice is ever a regret.",
                 bg=BG, fg=ACCENT, font=FB, anchor="w", wraplength=900, justify="left"
                 ).pack(fill="x", padx=10, pady=(10, 4))
        self.doctrine_note = tk.Label(inner, text="", bg=BG, fg=GOLD, font=FB,
                                      anchor="w")
        self.doctrine_note.pack(fill="x", padx=10)
        self.doctrine_btns = {}
        for row in G.DOCTRINE_ROWS:
            strip = tk.Frame(inner, bg=BG)
            strip.pack(fill="x", padx=10, pady=3)
            for doc in [d for d in G.DOCTRINES if d.row == row]:
                btn = tk.Button(strip, text=f"{doc.name}\n{doc.desc}", bg=BG2, fg=FG,
                                font=F, relief="flat", cursor="hand2", justify="left",
                                wraplength=250, anchor="w", padx=10, pady=8,
                                command=lambda d=doc.id: self._choose_doctrine(d))
                btn.pack(side="left", fill="both", expand=True, padx=2)
                self.doctrine_btns[doc.id] = btn

        tk.Label(inner, text="Coherence Nodes — most of these have no level cap",
                 bg=BG, fg=ACCENT, font=FB, anchor="w").pack(fill="x", padx=10, pady=(14, 2))
        self.coh_amount = tk.StringVar(
            value=self.state.settings.get("coh_buy_amount", "1"))
        self._amount_strip(inner, self.coh_amount, "Buy")
        self.coh_cards = {}
        for cu in G.COHERENCE_GRID:
            self.coh_cards[cu.id] = self._card(
                inner, cu.name, cu.desc, lambda cid=cu.id: self._buy_coh(cid))

    def _choose_doctrine(self, did):
        if E.choose_doctrine(self.state, did):
            doc = G.DOCTRINE_BY_ID[did]
            self.log(f"Doctrine set: {doc.name} — {doc.desc}", "major")
            self.refresh()

    def _buy_coh(self, cid):
        amount = self.coh_amount.get()
        if E.buy_coherence(self.state, cid, "max" if amount == "Max" else int(amount)):
            self.refresh()

    def do_converge(self):
        s = self.state
        gain = E.p2_gain(s)
        if gain <= 0:
            return
        if s.settings.get("confirm_prestige", True):
            ok = messagebox.askyesno(
                "Converge?",
                f"Gain {fmt(gain)} Coherence.\n\n"
                "RESET: everything Dispersal resets, AND your Seed Points,\n"
                "          the whole Seed Grid, and all Research.\n"
                "KEPT: Coherence, Doctrines, artifacts, milestones,\n"
                "          achievements, and every machine tier you unlocked.\n\n"
                "This is a bigger reset than Dispersal. Converge now?")
            if not ok:
                return
        E.converge(s)
        saveman.save(s)
        self.refresh()

    def _refresh_convergence(self):
        s = self.state
        gain = E.p2_gain(s)
        required = E.p2_required(s)
        body = [
            f"Coherence:  {fmt(s.p2_coh)}      Convergences: {s.p2_count}",
            f"Lifetime Seed Points:  {fmt(s.p1_sp_life)}   /   {fmt(required)} needed",
            "",
            f"Converge now:  +{fmt(gain)} Coherence",
        ]
        # Depth pays far more than converging the moment the bar is cleared, and
        # nothing on this screen used to say so.
        if gain > 0:
            body.append("")
            body.append("Waiting is worth a lot here:")
            for mult, label in ((10, "10x"), (100, "100x"), (10_000, "10,000x")):
                deeper = E.p2_gain_at(s, required * Num(mult))
                body.append(f"    at {label:>8} the bar ({fmt(required * Num(mult))} SP)"
                            f"   ->  +{fmt(deeper)} Coherence")
        body += [
            "",
            "RESET: everything Dispersal resets, plus Seed Points, the Seed Grid",
            "          and all Research.",
            "KEPT:  Coherence, Doctrines, artifacts, milestones, achievements,",
            "          and every machine tier you have unlocked.",
        ]
        if s.p2_count == 0:
            body += ["", "Converging unlocks Nanite Mass, Doctrines, and the "
                         "Coherence Nodes below."]
        self.p2_body.config(text="\n".join(body))
        self.p2_btn.config(state="normal" if gain > 0 else "disabled",
                           bg=VIOLET if gain > 0 else BG3,
                           fg="#12151c" if gain > 0 else DIM)

        unlocked = s.p2_count > 0
        unpicked = len(G.DOCTRINE_ROWS) - len(s.doctrines) if unlocked else 0
        self.doctrine_note.config(
            text=("" if not unpicked else
                  f"{unpicked} row{'s' if unpicked > 1 else ''} unchosen — these "
                  "are free, and you keep them through a Convergence."),
            fg=GOLD)
        for doc in G.DOCTRINES:
            btn = self.doctrine_btns[doc.id]
            chosen = s.doctrines.get(doc.row) == doc.id
            btn.config(state="normal" if unlocked else "disabled",
                       bg=VIOLET if chosen else BG2,
                       fg="#12151c" if chosen else (FG if unlocked else DIM))

        amount = self.coh_amount.get()
        for cu in G.COHERENCE_GRID:
            card = self.coh_cards[cu.id]
            level = int(s.p2_levels.get(cu.id, 0))
            if cu.max_level and level >= cu.max_level:
                card["btn"].config(text=f"Maxed ({level})", state="disabled",
                                   bg=BG3, fg=GREEN)
                continue
            afford = E.coherence_affordable(s, cu.id)
            headroom = (cu.max_level - level) if cu.max_level else E.MAX_BUY
            if amount == "Max":
                k = max(1, afford)
            else:
                k = min(int(amount), headroom)
            cost = E.coherence_cost(cu, level, k)
            can = unlocked and afford > 0 and s.p2_coh >= cost
            cap = f"/{cu.max_level}" if cu.max_level else ""
            self._shop_button(card, level, cap, cost, "Coh", k, can, VIOLET)

    def do_prestige(self):
        s = self.state
        gain = E.p1_gain(s)
        if gain <= 0:
            return
        if s.settings.get("confirm_prestige", True):
            ok = messagebox.askyesno(
                "Disperse?",
                f"Gain {fmt(gain)} Seed Points.\n\n"
                "RESET: resources, all machines, and this run's upgrades.\n"
                "KEPT: Research, artifacts, milestones, achievements,\n"
                "          Seed Points and everything bought with them.\n\n"
                "Disperse now?")
            if not ok:
                return
        E.prestige(s)
        saveman.save(s)
        self.refresh()

    # -- overwrite -------------------------------------------------------
    def _build_overwrite(self, parent):
        inner = scrollable(parent)
        top = tk.Frame(inner, bg=BG2)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Overwrite", bg=BG2, fg=CRIMSON, font=FH, anchor="w"
                 ).pack(fill="x", padx=12, pady=(10, 2))
        self.p3_body = tk.Label(top, text="", bg=BG2, fg=FG, font=F, anchor="w",
                                justify="left", wraplength=900)
        self.p3_body.pack(fill="x", padx=12)
        self.p3_btn = tk.Button(top, text="Overwrite", bg=CRIMSON, fg="#12151c",
                                font=FB, relief="flat", cursor="hand2",
                                padx=20, pady=8, command=self.do_overwrite)
        self.p3_btn.pack(anchor="w", padx=12, pady=10)

        tk.Label(inner,
                 text="Floors - permanent starting states, paid for with Charges",
                 bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(10, 2))
        self.over_amount = tk.StringVar(
            value=self.state.settings.get("over_buy_amount", "1"))
        self._amount_strip(inner, self.over_amount, "Buy")
        self.over_cards = {}
        for ou in G.OVERWRITE_GRID:
            self.over_cards[ou.id] = self._card(
                inner, ou.name, ou.desc, lambda oid=ou.id: self._buy_over(oid))

    def _buy_over(self, oid):
        amount = self.over_amount.get()
        if E.buy_overwrite(self.state, oid,
                           "max" if amount == "Max" else int(amount)):
            self.refresh()

    def do_overwrite(self):
        s = self.state
        gain = E.p3_gain(s)
        if gain <= 0:
            return
        if s.settings.get("confirm_prestige", True):
            message = (
                f"Gain {fmt(gain)} Overwrite Charges.\n\n"
                "RESET: everything Convergence resets, AND your Coherence,\n"
                "          the Coherence Nodes, and Exotic Matter.\n"
                "KEPT: Charges and the Floors they buy, artifacts,\n"
                "          milestones, achievements, and every unlocked tier.\n\n"
                "Charges come from your PEAK Alloy per second, so waiting\n"
                "earns nothing - only a better engine does. Overwrite now?")
            if not messagebox.askyesno("Overwrite?", message):
                return
        E.overwrite(s)
        saveman.save(s)
        self.refresh()

    def _refresh_overwrite(self):
        s = self.state
        gain = E.p3_gain(s)
        required = E.p3_required(s)
        body = [
            f"Overwrite Charges:  {fmt(s.p3_oc)}      Overwrites: {s.p3_count}",
            f"Peak Alloy/s this era:  {fmt(s.p3_peak_rate)}   /   "
            f"{fmt(required)} needed",
            "",
            f"Overwrite now:  +{fmt(gain)} Charges",
        ]
        if gain > 0:
            body.append("")
            body.append("A stronger engine pays more:")
            for mult, label in ((1e3, "1,000x"), (1e6, "1,000,000x")):
                deeper = E.p3_gain_at(s, required * Num(mult))
                body.append(f"    peak {label:>12} the bar  ->  +{fmt(deeper)} Charges")
        body += [
            "",
            "RESET: everything Convergence resets, plus Coherence, the",
            "          Coherence Nodes and Exotic Matter.",
            "KEPT:  Charges and Floors, artifacts, milestones, achievements.",
            "",
            "Charges come from your PEAK Alloy per second, never a lifetime",
            "total - waiting earns nothing here, only a better engine does.",
        ]
        if gain <= 0:
            body += ["", f"Needs a peak of {fmt(required)} Alloy/s this era."]
        self.p3_body.config(text=chr(10).join(body))
        self.p3_btn.config(state="normal" if gain > 0 else "disabled",
                           bg=CRIMSON if gain > 0 else BG3,
                           fg="#12151c" if gain > 0 else DIM)

        amount = self.over_amount.get()
        for ou in G.OVERWRITE_GRID:
            card = self.over_cards[ou.id]
            level = int(s.p3_levels.get(ou.id, 0))
            if ou.max_level and level >= ou.max_level:
                card["btn"].config(text=f"Maxed ({level})", state="disabled",
                                   bg=BG3, fg=GREEN)
                continue
            afford = E.overwrite_affordable(s, ou.id)
            headroom = (ou.max_level - level) if ou.max_level else E.MAX_BUY
            k = max(1, afford) if amount == "Max" else min(int(amount), headroom)
            cost = E.overwrite_cost(ou, level, k)
            can = afford > 0 and s.p3_oc >= cost
            cap = f"/{ou.max_level}" if ou.max_level else ""
            self._shop_button(card, level, cap, cost, "OC", k, can, CRIMSON)

    # -- substrate -------------------------------------------------------
    def _build_substrate(self, parent):
        inner = scrollable(parent)
        top = tk.Frame(inner, bg=BG2)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Substrate Collapse", bg=BG2, fg=CYAN, font=FH,
                 anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        self.p4_body = tk.Label(top, text="", bg=BG2, fg=FG, font=F, anchor="w",
                                justify="left", wraplength=900)
        self.p4_body.pack(fill="x", padx=12)
        self.p4_btn = tk.Button(top, text="Collapse", bg=CYAN, fg="#12151c",
                                font=FB, relief="flat", cursor="hand2",
                                padx=20, pady=8, command=self.do_collapse)
        self.p4_btn.pack(anchor="w", padx=12, pady=10)

        tk.Label(inner,
                 text="The Lattice - every multiplier you own is already "
                      "astronomical, so Substrate buys exponents instead",
                 bg=BG, fg=ACCENT, font=FB, anchor="w", wraplength=900,
                 justify="left").pack(fill="x", padx=10, pady=(10, 2))
        self.sub_amount = tk.StringVar(
            value=self.state.settings.get("sub_buy_amount", "1"))
        self._amount_strip(inner, self.sub_amount, "Buy")
        self.sub_cards = {}
        for su in G.SUBSTRATE_GRID:
            self.sub_cards[su.id] = self._card(
                inner, su.name, su.desc, lambda uid=su.id: self._buy_sub(uid))

    def _buy_sub(self, uid):
        amount = self.sub_amount.get()
        if E.buy_substrate(self.state, uid,
                           "max" if amount == "Max" else int(amount)):
            self.refresh()

    def do_collapse(self):
        s = self.state
        gain = E.p4_gain(s)
        if gain <= 0:
            return
        if s.settings.get("confirm_prestige", True):
            message = (
                f"Gain {fmt(gain)} Substrate.\n\n"
                "RESET: everything Overwrite resets, AND your Overwrite\n"
                "          Charges and every Floor they bought.\n"
                "KEPT: Substrate and what it buys, artifacts, milestones,\n"
                "          achievements, and every unlocked tier.\n\n"
                "Substrate buys EXPONENTS, not multipliers. Collapse now?")
            if not messagebox.askyesno("Collapse the substrate?", message):
                return
        E.collapse(s)
        saveman.save(s)
        self.refresh()

    def _refresh_substrate(self):
        s = self.state
        gain = E.p4_gain(s)
        required = E.p4_required(s)
        exponent = 1.0 + E.collect_mults(s).exponent
        body = [
            f"Substrate:  {fmt(s.p4_sub)}      Collapses: {s.p4_count}",
            f"Lifetime Overwrite Charges:  {fmt(s.p3_oc_life)}   /   "
            f"{fmt(required)} needed",
            "",
            f"Production exponent:  ^{exponent:.4f}",
            f"Collapse now:  +{fmt(gain)} Substrate",
        ]
        if gain > 0:
            body.append("")
            body.append("Depth pays here too:")
            for mult, label in ((100, "100x"), (10_000, "10,000x")):
                deeper = E.p4_gain_at(s, required * Num(mult))
                body.append(f"    at {label:>9} the bar  ->  +{fmt(deeper)} Substrate")
        body += [
            "",
            "RESET: everything Overwrite resets, plus Overwrite Charges and",
            "          every Floor they bought.",
            "KEPT:  Substrate and what it buys, artifacts, milestones,",
            "          achievements, and every tier you have unlocked.",
        ]
        if gain <= 0:
            body += ["", f"Needs {fmt(required)} lifetime Overwrite Charges."]
        self.p4_body.config(text=chr(10).join(body))
        self.p4_btn.config(state="normal" if gain > 0 else "disabled",
                           bg=CYAN if gain > 0 else BG3,
                           fg="#12151c" if gain > 0 else DIM)

        amount = self.sub_amount.get()
        for su in G.SUBSTRATE_GRID:
            card = self.sub_cards[su.id]
            level = int(s.p4_levels.get(su.id, 0))
            if su.max_level and level >= su.max_level:
                card["btn"].config(text=f"Maxed ({level})", state="disabled",
                                   bg=BG3, fg=GREEN)
                continue
            afford = E.substrate_affordable(s, su.id)
            headroom = (su.max_level - level) if su.max_level else E.MAX_BUY
            k = max(1, afford) if amount == "Max" else min(int(amount), headroom)
            cost = E.substrate_cost(su, level, k)
            can = afford > 0 and s.p4_sub >= cost
            cap = f"/{su.max_level}" if su.max_level else ""
            self._shop_button(card, level, cap, cost, "Sub", k, can, CYAN)

    # -- automation ------------------------------------------------------
    def _build_automation(self, parent):
        inner = scrollable(parent)
        self.auto_master = tk.BooleanVar(value=bool(self.state.auto.get("enabled")))
        tk.Checkbutton(inner, text="Enable auto-buy", variable=self.auto_master,
                       command=self._auto_master_changed, bg=BG, fg=FG, font=FB,
                       selectcolor=BG3, activebackground=BG, anchor="w"
                       ).pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(inner, text="Auto-buy uses exactly the same purchase path you do, so it "
                             "can never buy something you could not afford.",
                 bg=BG, fg=DIM, font=F, anchor="w", wraplength=900, justify="left"
                 ).pack(fill="x", padx=10, pady=(0, 8))

        self.auto_vars = {}
        for g in G.GENERATORS:
            var = tk.BooleanVar(value=bool(self.state.auto["gens"].get(g.id)))
            self.auto_vars[g.id] = var
            cb = tk.Checkbutton(inner, text=g.name, variable=var, bg=BG, fg=FG, font=F,
                                selectcolor=BG3, activebackground=BG, anchor="w",
                                command=lambda gid=g.id: self._auto_gen_changed(gid))
            cb.pack(fill="x", padx=24)
            self.widgets[f"auto_{g.id}"] = cb

        tk.Label(inner, text="Spending reserve — auto-buy will not touch this much",
                 bg=BG, fg=ACCENT, font=FB, anchor="w").pack(fill="x", padx=10, pady=(14, 2))
        tk.Label(inner, text="An absolute amount, so it stays put instead of draining "
                             "away tick by tick. Accepts forms like 5000 or 2.5e9.",
                 bg=BG, fg=DIM, font=F, anchor="w", wraplength=900, justify="left"
                 ).pack(fill="x", padx=10)
        self.reserve_entries = {}
        for rid in G.STOCK_RESOURCES:
            row = tk.Frame(inner, bg=BG)
            row.pack(fill="x", padx=24, pady=2)
            tk.Label(row, text=G.RES_BY_ID[rid].name, bg=BG, fg=FG, font=F,
                     width=10, anchor="w").pack(side="left")
            entry = tk.Entry(row, bg=BG3, fg=FG, font=FMONO, width=16,
                             insertbackground=FG, relief="flat")
            entry.insert(0, str(Num.from_json(self.state.auto["reserve"].get(rid, 0)).to_json()))
            entry.pack(side="left")
            entry.bind("<FocusOut>", lambda _e, r=rid: self._reserve_changed(r))
            entry.bind("<Return>", lambda _e, r=rid: self._reserve_changed(r))
            self.reserve_entries[rid] = entry

        tk.Label(inner, text="Auto-Dispersal", bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(14, 2))
        self.autop_var = tk.BooleanVar(value=bool(self.state.auto.get("prestige_enabled")))
        self.autop_cb = tk.Checkbutton(
            inner, text="Disperse automatically", variable=self.autop_var,
            command=self._autop_changed, bg=BG, fg=FG, font=F, selectcolor=BG3,
            activebackground=BG, anchor="w")
        self.autop_cb.pack(fill="x", padx=24)
        prow = tk.Frame(inner, bg=BG)
        prow.pack(fill="x", padx=24, pady=2)
        tk.Label(prow, text="when the gain is at least", bg=BG, fg=DIM, font=F
                 ).pack(side="left")
        self.autop_entry = tk.Entry(prow, bg=BG3, fg=FG, font=FMONO, width=6,
                                    insertbackground=FG, relief="flat")
        self.autop_entry.insert(0, str(self.state.auto.get("prestige_threshold", 2.0)))
        self.autop_entry.pack(side="left", padx=6)
        self.autop_entry.bind("<FocusOut>", lambda _e: self._autop_threshold())
        self.autop_entry.bind("<Return>", lambda _e: self._autop_threshold())
        tk.Label(prow, text="x the Seed Points you already hold", bg=BG, fg=DIM,
                 font=F).pack(side="left")

        tk.Label(inner, text="Auto-Overwrite", bg=BG, fg=ACCENT, font=FB,
                 anchor="w").pack(fill="x", padx=10, pady=(14, 2))
        self.autoo_var = tk.BooleanVar(
            value=bool(self.state.auto.get("overwrite_enabled")))
        self.autoo_cb = tk.Checkbutton(
            inner, text="Overwrite automatically", variable=self.autoo_var,
            command=self._autoo_changed, bg=BG, fg=FG, font=F, selectcolor=BG3,
            activebackground=BG, anchor="w")
        self.autoo_cb.pack(fill="x", padx=24)
        orow = tk.Frame(inner, bg=BG)
        orow.pack(fill="x", padx=24, pady=2)
        tk.Label(orow, text="when peak Alloy/s reaches 10^", bg=BG, fg=DIM,
                 font=F).pack(side="left")
        self.autoo_entry = tk.Entry(orow, bg=BG3, fg=FG, font=FMONO, width=5,
                                    insertbackground=FG, relief="flat")
        self.autoo_entry.insert(0, str(self.state.auto.get("overwrite_depth", 2.0)))
        self.autoo_entry.pack(side="left", padx=6)
        self.autoo_entry.bind("<FocusOut>", lambda _e: self._autoo_depth())
        self.autoo_entry.bind("<Return>", lambda _e: self._autoo_depth())
        tk.Label(orow, text="x past the bar", bg=BG, fg=DIM, font=F).pack(side="left")

        tk.Label(inner, text="Auto-Convergence", bg=BG, fg=ACCENT, font=FB,
                 anchor="w").pack(fill="x", padx=10, pady=(14, 2))
        self.autoc_var = tk.BooleanVar(
            value=bool(self.state.auto.get("converge_enabled")))
        self.autoc_cb = tk.Checkbutton(
            inner, text="Converge automatically", variable=self.autoc_var,
            command=self._autoc_changed, bg=BG, fg=FG, font=F, selectcolor=BG3,
            activebackground=BG, anchor="w")
        self.autoc_cb.pack(fill="x", padx=24)
        crow = tk.Frame(inner, bg=BG)
        crow.pack(fill="x", padx=24, pady=2)
        tk.Label(crow, text="when lifetime Seed Points reach 10^", bg=BG, fg=DIM,
                 font=F).pack(side="left")
        self.autoc_entry = tk.Entry(crow, bg=BG3, fg=FG, font=FMONO, width=5,
                                    insertbackground=FG, relief="flat")
        self.autoc_entry.insert(0, str(self.state.auto.get("converge_depth", 2.0)))
        self.autoc_entry.pack(side="left", padx=6)
        self.autoc_entry.bind("<FocusOut>", lambda _e: self._autoc_depth())
        self.autoc_entry.bind("<Return>", lambda _e: self._autoc_depth())
        tk.Label(crow, text="x past the bar (depth pays: 2 means 100x)", bg=BG,
                 fg=DIM, font=F).pack(side="left")

        tk.Label(inner, text="Standing orders", bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(14, 2))
        self.standing = {}
        for key, label, flag in (("upgrades", "Auto-buy Upgrades (cheapest first)", "auto_upgrade"),
                                 ("seed", "Auto-buy Seed Grid (cheapest first)", "auto_seed"),
                                 ("coherence", "Auto-buy Coherence Nodes (cheapest first)", "auto_coh"),
                                 ("relics", "Auto-equip best Relics", "auto_relic"),
                                 ("fuse", "Auto-fuse spare Relics", "auto_fuse"),
                                 ("research", "Auto-Research (cheapest first)", "auto_research"),
                                 ("expedition", "Auto-Expedition (keep bays full)", "auto_expedition"),
                                 ("balance", "Load Balancer (spend on the bottleneck)", "auto_balance")):
            var = tk.BooleanVar(value=bool(self.state.auto.get(key)))
            cb = tk.Checkbutton(inner, text=label, variable=var, bg=BG, fg=FG, font=F,
                                selectcolor=BG3, activebackground=BG, anchor="w",
                                command=lambda k=key, v=var: self._standing_changed(k, v))
            cb.pack(fill="x", padx=24)
            self.standing[key] = (var, cb, flag)

    def _autoo_changed(self):
        self.state.auto["overwrite_enabled"] = bool(self.autoo_var.get())

    def _autoo_depth(self):
        try:
            value = max(0.0, float(self.autoo_entry.get().strip() or "2"))
        except ValueError:
            value = 2.0
        self.state.auto["overwrite_depth"] = value
        self.autoo_entry.delete(0, "end")
        self.autoo_entry.insert(0, f"{value:g}")

    def _autoc_changed(self):
        self.state.auto["converge_enabled"] = bool(self.autoc_var.get())

    def _autoc_depth(self):
        try:
            value = max(0.0, float(self.autoc_entry.get().strip() or "2"))
        except ValueError:
            value = 2.0
        self.state.auto["converge_depth"] = value
        self.autoc_entry.delete(0, "end")
        self.autoc_entry.insert(0, f"{value:g}")

    def _autop_changed(self):
        self.state.auto["prestige_enabled"] = bool(self.autop_var.get())

    def _autop_threshold(self):
        try:
            value = max(1.0, float(self.autop_entry.get().strip() or "2"))
        except ValueError:
            value = 2.0
        self.state.auto["prestige_threshold"] = value
        self.autop_entry.delete(0, "end")
        self.autop_entry.insert(0, f"{value:g}")

    def _auto_master_changed(self):
        self.state.auto["enabled"] = bool(self.auto_master.get())

    def _auto_gen_changed(self, gid):
        self.state.auto["gens"][gid] = bool(self.auto_vars[gid].get())

    def _standing_changed(self, key, var):
        self.state.auto[key] = bool(var.get())

    def _reserve_changed(self, rid):
        entry = self.reserve_entries[rid]
        try:
            value = Num(entry.get().strip() or "0")
            if value < 0:
                value = ZERO
        except Exception:
            value = ZERO
        self.state.auto["reserve"][rid] = value.to_json()
        entry.delete(0, "end")
        entry.insert(0, value.to_json())

    # -- stats -----------------------------------------------------------
    def _build_stats(self, parent):
        inner = scrollable(parent)
        self.stats_label = tk.Label(inner, text="", bg=BG, fg=FG, font=FMONO,
                                    anchor="w", justify="left")
        self.stats_label.pack(fill="x", padx=12, pady=10)

        tk.Label(inner, text="Milestones", bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(8, 2))
        self.milestone_label = tk.Label(inner, text="", bg=BG, fg=DIM, font=F,
                                        anchor="w", justify="left", wraplength=920)
        self.milestone_label.pack(fill="x", padx=12)

        tk.Label(inner, text="Achievements", bg=BG, fg=ACCENT, font=FB, anchor="w"
                 ).pack(fill="x", padx=10, pady=(12, 2))
        self.ach_box = tk.Frame(inner, bg=BG)
        self.ach_box.pack(fill="x", padx=12)
        self.ach_labels = {}
        for a in G.ACHIEVEMENTS:
            lbl = tk.Label(self.ach_box, text="", bg=BG, fg=DIM, font=F, anchor="w",
                           justify="left")
            lbl.pack(fill="x")
            self.ach_labels[a.id] = lbl

        danger = tk.Frame(inner, bg=BG)
        danger.pack(fill="x", padx=12, pady=(20, 12))
        tk.Button(danger, text="Save now", bg=BG3, fg=FG, font=F, relief="flat",
                  cursor="hand2", padx=12, pady=5,
                  command=self.save_now).pack(side="left")
        tk.Button(danger, text="Delete save", bg=BG3, fg=RED, font=F, relief="flat",
                  cursor="hand2", padx=12, pady=5,
                  command=self.hard_reset).pack(side="left", padx=8)
        self.save_dir_label = tk.Label(danger, text=str(saveman.save_dir()),
                                       bg=BG, fg=DIM, font=F)
        self.save_dir_label.pack(side="right")

    def save_now(self):
        if saveman.save(self.state):
            self.save_flash = 2.0
            self.log("Saved.", "good")
        else:
            self.log("Save FAILED — the save on disk was left untouched.", "warn")

    def hard_reset(self):
        from tkinter import simpledialog
        answer = simpledialog.askstring(
            "Delete save",
            "This erases everything permanently.\n\nType DELETE to confirm:",
            parent=self.root)
        if answer != "DELETE":
            self.log("Delete cancelled.", "info")
            return
        prompt = (
            "World seed for the new game.\n\n"
            "Leave blank for a random one. Type a number or any words to pick\n"
            "your own — the same seed gives the same luck, so you and a friend\n"
            "can start from the same world.")
        seed_text = simpledialog.askstring("World seed", prompt,
                                           parent=self.root) or ""
        saveman.delete_save()
        self.state = new_game(seed_text)
        E.recompute(self.state)
        self.log(f"Save deleted. New world, seed {self.state.rng_seed}.", "warn")
        self.refresh()

    # -- the loop --------------------------------------------------------
    def tick(self):
        try:
            now = time.perf_counter()
            dt = min(now - self.last, G.MAX_DT)
            self.last = now
            E.tick(self.state, dt)

            self.ticks += 1
            if self.ticks % G.UI_REFRESH_EVERY == 0:
                self.refresh()

            self.autosave_in -= dt
            if self.autosave_in <= 0:
                self.autosave_in = G.AUTOSAVE_SECONDS
                if self.state.settings.get("autosave", True):
                    if saveman.save(self.state):
                        self.save_flash = 1.5
            if self.save_flash > 0:
                self.save_flash -= dt
        finally:
            # Rescheduled at the END, and only here, so it cannot double-register.
            self.root.after(G.TICK_MS, self.tick)

    # -- refresh ---------------------------------------------------------
    def refresh(self):
        s = self.state
        self._drain_notices()
        self._refresh_header()
        self._refresh_tabs()
        current = self.nb.tab(self.nb.select(), "text") if self.nb.tabs() else ""
        if current == "Production":
            self._refresh_production()
        elif current == "Upgrades":
            self._refresh_upgrades()
        elif current == "Research":
            self._refresh_research()
        elif current == "Exploration":
            self._refresh_exploration()
        elif current == "Dispersal":
            self._refresh_prestige()
        elif current == "Convergence":
            self._refresh_convergence()
        elif current == "Overwrite":
            self._refresh_overwrite()
        elif current == "Substrate":
            self._refresh_substrate()
        elif current == "Automation":
            self._refresh_automation()
        elif current == "Stats":
            self._refresh_stats()

    def _drain_notices(self):
        tags = {"unlock": "good", "major": "major", "milestone": "good",
                "achievement": "good", "event": "event", "event_end": "info",
                "artifact": "major", "probe": "info", "prestige": "major"}
        for kind, text in self.state.notices:
            self.log(text, tags.get(kind, "info"))
        self.state.notices.clear()

    def _refresh_header(self):
        s = self.state
        for rid, (box, value, rate) in self.res_labels.items():
            visible = s.run_life.get(rid, ZERO) > 0 or s.res.get(rid, ZERO) > 0
            if visible and not is_packed(box):
                box.pack(side="left", padx=(0, 26))
            elif not visible and is_packed(box):
                box.pack_forget()
            if not visible:
                continue
            value.config(text=fmt(s.res.get(rid, ZERO)))
            r = s.rates.get(rid, ZERO)
            if r > 0:
                rate.config(text=f"+{fmt(r)}/s", fg=GREEN)
            elif r < 0:
                rate.config(text=f"{fmt(r)}/s", fg=RED)
            else:
                rate.config(text="—", fg=DIM)

        supply, demand = s.energy_supply, s.energy_demand
        if demand <= 0 and supply <= 0:
            self.power_label.config(text="Power — idle")
            self.power_hint.config(text="")
            frac = 1.0
        else:
            pct = s.throttle * 100
            self.power_label.config(
                text=f"Power {fmt(supply)} / {fmt(demand)} — throttle {pct:.0f}%")
            if s.throttle >= 0.999:
                self.power_hint.config(text="", fg=GREEN)
            else:
                self.power_hint.config(text="Build Solar Film or Fusion Cell", fg=YELLOW)
            frac = s.throttle
        width = max(1, self.power_canvas.winfo_width())
        colour = GREEN if frac >= 0.95 else (YELLOW if frac >= 0.6 else RED)
        self.power_canvas.coords(self.power_bar, 0, 0, width * frac, 8)
        self.power_canvas.itemconfig(self.power_bar, fill=colour)

        self.goal_label.config(text="Next: " + self._next_goal())
        saving = "  •  saving…" if self.save_flash > 0 else ""
        self.clock_label.config(
            text=f"run {fmt_time(s.run_time())}   total {fmt_time(s.stats.get('playtime', 0))}{saving}")

    def _next_goal(self) -> str:
        s = self.state
        # Doctrines are free and easy to never notice -- a real save reached 17
        # Convergences with all five rows empty.
        if s.p2_count > 0:
            unpicked = len(G.DOCTRINE_ROWS) - len(s.doctrines)
            if unpicked > 0:
                return (f"pick your free Doctrines on the Convergence tab "
                        f"({unpicked} row{'s' if unpicked > 1 else ''} unchosen)")
        for g in G.GENERATORS:
            if g.id in s.unlocked and s.gens.get(g.id, ZERO) <= 0:
                return f"buy your first {g.name} ({fmt(E.cost_of(s, g.id))} " \
                       f"{G.RES_BY_ID[g.cost_res].name})"
        for g in G.GENERATORS:
            if g.id not in s.unlocked:
                c = g.unlock
                if c.res and c.amount:
                    have = (s.run_life if c.lifetime else s.res).get(c.res, ZERO)
                    if have < c.amount:
                        return f"{fmt(c.amount)} {G.RES_BY_ID[c.res].name} to unlock {g.name}"
                if c.gen:
                    return f"{c.count:g} {G.GEN_BY_ID[c.gen].name} to unlock {g.name}"
        if E.p2_available(s):
            return f"Converge for {fmt(E.p2_gain(s))} Coherence"
        if E.p1_available(s):
            return f"Disperse for {fmt(E.p1_gain(s))} Seed Points"
        if E.p2_visible(s):
            return (f"{fmt(E.p2_required(s))} lifetime Seed Points to Converge "
                    f"(at {fmt(s.p1_sp_life)})")
        alloy = s.run_life.get("alloy", ZERO)
        if alloy > 0:
            return f"{fmt(G.P1_UNLOCK_ALLOY)} lifetime Alloy to unlock Dispersal " \
                   f"(at {fmt(alloy)})"
        return "produce your first Alloy"

    def _refresh_tabs(self):
        s = self.state
        for index, tab in enumerate(G.TABS):
            if tab.id in self.visible_tabs:
                continue
            if not E.check(tab.unlock, s):
                continue
            position = sum(1 for t in G.TABS[:index] if t.id in self.visible_tabs)
            # ttk cannot insert past the end (or into an empty notebook).
            if position >= len(self.nb.tabs()):
                self.nb.add(self.frames[tab.id], text=tab.name)
            else:
                self.nb.insert(position, self.frames[tab.id], text=tab.name)
            self.visible_tabs.append(tab.id)
            if len(self.visible_tabs) > 1:
                self.log(f"New tab unlocked: {tab.name}", "good")

    def _refresh_production(self):
        s = self.state
        m = E.collect_mults(s)
        for g in G.GENERATORS:
            w = self.gen_rows[g.id]
            if g.id not in s.unlocked:
                if is_packed(w["row"]):
                    w["row"].pack_forget()
                continue
            if not is_packed(w["row"]):
                pack_ordered(w["row"], self._rows_after(g.id),
                             fill="x", padx=10, pady=2)

            count = s.gens.get(g.id, ZERO)
            bought = s.bought.get(g.id, ZERO)
            mult = s.mults.get(g.id, Num(1))
            output = count * N(g.base_rate) * mult
            if g.produces in G.RES_BY_ID:
                unit = G.RES_BY_ID[g.produces].name
            elif g.produces:
                unit = G.GEN_BY_ID[g.produces].name
            else:
                unit = ""
            shown = fmt(count) if count >= 100 else f"{count.to_float():.2f}".rstrip("0").rstrip(".")
            w["title"].config(text=f"{g.name}   ×{shown}")
            detail = f"{fmt(output)} {unit}/s"
            if g.produces != "energy" and s.throttle < 0.999:
                detail += f"  (throttled to {s.throttle * 100:.0f}%)"
            eff = s.upkeep_eff.get(g.id)
            if eff is not None and eff < 0.999:
                detail += f"  ·  IDLED {(1 - eff) * 100:.0f}% (needs Alloy)"
            w["detail"].config(text=detail)

            steps = int(bought.to_float() % 10) if bought.e < 15 else 0
            w["pips"].config(text="●" * steps + "○" * (10 - steps) +
                                  f"  {steps}/10 to the next ×1.10")

            amount = self.buy_amount.get()
            k = E.max_affordable(s, g.id, m) if amount == "Max" else int(amount)
            k = max(1, min(k, E.MAX_BUY)) if amount == "Max" else k
            cost = E.cost_of(s, g.id, k, m)
            affordable = s.res.get(g.cost_res, ZERO) >= cost and \
                (amount != "Max" or E.max_affordable(s, g.id, m) > 0)
            label = f"x{k}" if amount == "Max" else f"x{amount}"
            w["cost"].config(text=f"{fmt(cost)} {G.RES_BY_ID[g.cost_res].name}",
                             fg=FG if affordable else DIM)
            w["btn"].config(text=f"Buy {label}",
                            bg=ACCENT if affordable else BG3,
                            fg="#12151c" if affordable else DIM,
                            state="normal" if affordable else "disabled")

    def _refresh_upgrades(self):
        s = self.state
        for u in G.UPGRADES:
            card = self.upg_cards[u.id]
            owned = u.id in s.upgrades
            visible = owned or E.check(u.unlock, s)
            if not visible:
                if is_packed(card["row"]):
                    card["row"].pack_forget()
                continue
            if not is_packed(card["row"]):
                card["row"].pack(fill="x", padx=10, pady=2)
            if owned:
                card["btn"].config(text="Owned", state="disabled", bg=BG3, fg=GREEN)
            else:
                can = s.res.get(u.cost_res, ZERO) >= u.cost
                card["btn"].config(
                    text=f"{fmt(u.cost)} {G.RES_BY_ID[u.cost_res].name}",
                    state="normal" if can else "disabled",
                    bg=ACCENT if can else BG3, fg="#12151c" if can else DIM)

    def _refresh_research(self):
        s = self.state
        for t in G.RESEARCH:
            card = self.tech_cards[t.id]
            owned = t.id in s.research
            visible = owned or E.check(t.unlock, s)
            if not visible:
                if is_packed(card["row"]):
                    card["row"].pack_forget()
                continue
            if not is_packed(card["row"]):
                card["row"].pack(fill="x", padx=10, pady=2)
            if owned:
                card["btn"].config(text="Researched", state="disabled", bg=BG3, fg=GREEN)
            else:
                can = s.res.get("data", ZERO) >= t.cost
                card["btn"].config(text=f"{fmt(t.cost)} Data",
                                   state="normal" if can else "disabled",
                                   bg=ACCENT if can else BG3,
                                   fg="#12151c" if can else DIM)

    def _refresh_exploration(self):
        s = self.state
        slots = E.probe_slots(s)
        for i, lbl in enumerate(self.probe_labels):
            if i >= slots:
                if is_packed(lbl):
                    lbl.pack_forget()
                continue
            if not is_packed(lbl):
                lbl.pack(fill="x", pady=1)
            if i < len(s.probes):
                p = s.probes[i]
                t = E.TARGET_BY_ID.get(p["target"])
                total = max(1.0, float(p.get("total", 1.0)))
                done = 1.0 - max(0.0, p["remaining"]) / total
                bar = "█" * int(done * 20) + "░" * (20 - int(done * 20))
                lbl.config(text=f"  {t.name if t else '?'}  {bar}  "
                                f"{fmt_time(p['remaining'])} left", fg=ACCENT)
            else:
                lbl.config(text="  (bay empty)", fg=DIM)

        for t in G.TARGETS:
            card = self.target_rows[t.id]
            if not E.check(t.unlock, s):
                if is_packed(card["row"]):
                    card["row"].pack_forget()
                continue
            if not is_packed(card["row"]):
                card["row"].pack(fill="x", padx=10, pady=2)
            can = (len(s.probes) < slots and s.res.get("isotope", ZERO) >= N(t.cost_iso))
            cost = "free" if t.cost_iso <= 0 else f"{fmt(N(t.cost_iso))} Iso"
            card["btn"].config(text=f"Launch · {cost} · {fmt_time(t.duration)}",
                               state="normal" if can else "disabled",
                               bg=ACCENT if can else BG3,
                               fg="#12151c" if can else DIM)

        relics = E.relic_slots(s)
        best = set(E.best_loadout(s))
        optimal = best == set(s.equipped)
        self.relic_note.config(
            text=f"{len(s.equipped)}/{relics} slots used · {len(s.artifacts)} held · "
                 + ("best set slotted" if optimal else "a better set is available"),
            fg=DIM if optimal else GOLD)

        # Only relics worth acting on get a row.  A long game accumulates
        # hundreds, and one row each would be unreadable and slow.
        ranked = sorted(s.artifacts, key=lambda a: E.artifact_score(s, a),
                        reverse=True)
        shown, seen = [], set()
        by_id = {a["id"]: a for a in s.artifacts}
        for aid in s.equipped:
            if aid in by_id:
                shown.append(by_id[aid])
                seen.add(aid)
        for art in ranked:
            if len(shown) >= relics + 10:
                break
            if art["id"] not in seen:
                shown.append(art)
                seen.add(art["id"])

        # Fusion destroys relics, so rows have to be able to go away again.
        for aid in list(self.artifact_rows):
            if aid not in by_id:
                self.artifact_rows.pop(aid)["row"].destroy()
            elif aid not in seen and is_packed(self.artifact_rows[aid]["row"]):
                self.artifact_rows[aid]["row"].pack_forget()

        for art in shown:
            aid = art["id"]
            if aid not in self.artifact_rows:
                row = tk.Frame(self.artifact_box, bg=BG2)
                name = tk.Label(row, text="", bg=BG2, font=FB, anchor="w",
                                padx=10, pady=5)
                name.pack(side="left", fill="x", expand=True)
                btn = tk.Button(row, text="", width=10, bg=BG3, fg=FG, font=F,
                                relief="flat", cursor="hand2",
                                command=lambda a=aid: self._toggle_equip(a))
                btn.pack(side="right", padx=8)
                self.artifact_rows[aid] = {"row": row, "name": name, "btn": btn}
            w = self.artifact_rows[aid]
            if not is_packed(w["row"]):
                later = [self.artifact_rows[a["id"]]["row"]
                         for a in shown[shown.index(art) + 1:]
                         if a["id"] in self.artifact_rows]
                pack_ordered(w["row"], later, fill="x", pady=1)
            rarity = G.RARITY_BY_ID.get(art.get("rarity", "common"))
            mut = E.mutation_of(art)
            colour = mut.colour or (rarity.colour if rarity else FG)
            score = E.artifact_score(s, art)
            w["name"].config(
                text=f"{art['name']}  —  {art.get('desc', '')}   (value {score:.2f})",
                fg=colour)
            equipped = aid in s.equipped
            wanted = aid in best
            w["btn"].config(text="Remove" if equipped else "Slot",
                            fg=GREEN if equipped else (GOLD if wanted else FG),
                            state="normal" if equipped or len(s.equipped) < relics
                            else "disabled")
        hidden = len(s.artifacts) - len(shown)
        self.vault_note.config(
            text=f"...and {hidden} more in the vault" if hidden > 0 else "")

        self._refresh_crucible(s)

    def _refresh_crucible(self, s):
        fusion = s.has_flag("fusion")
        widgets = (self.crucible_head, self.crucible_note, self.crucible_box,
                   self.fuse_all_btn)
        if not fusion:
            for widget in widgets:
                if is_packed(widget):
                    widget.pack_forget()
            return
        for widget in widgets:
            if not is_packed(widget):
                if widget is self.fuse_all_btn:
                    widget.pack(anchor="w", padx=10, pady=(4, 10))
                else:
                    widget.pack(fill="x", padx=10, pady=2)

        self.crucible_note.config(
            text=f"Fuse {G.FUSE_COUNT} spare relics of one rarity into one of the "
                 "next rarity up. The result keeps the strangest mutation that "
                 "went into it, and nothing you are using is ever consumed.")
        spare = E.fusable_counts(s)
        total = 0
        for rarity in G.RARITY[:-1]:
            w = self.crucible_rows[rarity.id]
            count = spare.get(rarity.id, 0)
            sets = count // G.FUSE_COUNT
            total += sets
            if count <= 0:
                if is_packed(w["row"]):
                    w["row"].pack_forget()
                continue
            if not is_packed(w["row"]):
                w["row"].pack(fill="x", pady=1)
            up = E.next_rarity(rarity.id)
            w["label"].config(text=f"{rarity.name} spare: {count}", fg=rarity.colour)
            w["btn"].config(text=f"Fuse into {sets}" if sets else "need more",
                            state="normal" if sets else "disabled",
                            bg=ACCENT if sets else BG3,
                            fg="#12151c" if sets else DIM)
        self.fuse_all_btn.config(state="normal" if total else "disabled",
                                 fg=FG if total else DIM)

    def _refresh_prestige(self):
        s = self.state
        gain = E.p1_gain(s)
        soon = E.project_gain(s, 600)
        body = [
            f"Seed Points:  {fmt(s.p1_sp)}      Dispersals: {s.p1_count}",
            f"Alloy this run:  {fmt(s.run_life.get('alloy', ZERO))}"
            f"   /   {fmt(E.p1_required(s))} needed",
            "",
            f"Disperse now:            +{fmt(gain)} Seed Points",
            f"In 10 minutes at this rate: +{fmt(soon)} Seed Points",
            "",
            "RESET: resources, all machines, this run's upgrades.",
            "KEPT:  Research, artifacts, milestones, achievements, Seed Points.",
        ]
        if gain <= 0:
            body.append("")
            body.append(f"Needs {fmt(E.p1_required(s))} Alloy in this run.")
            body.append("The bar rises as you accumulate Seed Points, so a run "
                        "always has to mean something.")
        self.p1_body.config(text="\n".join(body))
        self.p1_btn.config(state="normal" if gain > 0 else "disabled",
                           bg=GOLD if gain > 0 else BG3,
                           fg="#12151c" if gain > 0 else DIM)

        amount = self.seed_amount.get()
        for su in G.SEED_GRID:
            card = self.seed_cards[su.id]
            level = int(s.p1_levels.get(su.id, 0))
            if su.max_level and level >= su.max_level:
                card["btn"].config(text=f"Maxed ({level})", state="disabled",
                                   bg=BG3, fg=GREEN)
                continue
            afford = E.seed_affordable(s, su.id)
            headroom = (su.max_level - level) if su.max_level else E.MAX_BUY
            if amount == "Max":
                k = max(1, afford)
            else:
                k = min(int(amount), headroom)
            cost = E.seed_cost(su, level, k)
            can = afford > 0 and s.p1_sp >= cost
            cap = f"/{su.max_level}" if su.max_level > 1 else ""
            self._shop_button(card, level, cap, cost, "SP", k, can, ACCENT)

    def _sync_automation_controls(self):
        """Push state -> widgets.

        A prestige (or a save load, or a hard reset) can replace the settings
        dict wholesale, and a checkbox that still shows ticked while the setting
        behind it is off is worse than no checkbox at all.
        """
        s = self.state
        if bool(self.auto_master.get()) != bool(s.auto.get("enabled")):
            self.auto_master.set(bool(s.auto.get("enabled")))
        for gid, var in self.auto_vars.items():
            want = bool(s.auto.get("gens", {}).get(gid))
            if bool(var.get()) != want:
                var.set(want)
        for key, (var, _cb, _flag) in self.standing.items():
            want = bool(s.auto.get(key))
            if bool(var.get()) != want:
                var.set(want)
        want_o = bool(s.auto.get("overwrite_enabled"))
        if bool(self.autoo_var.get()) != want_o:
            self.autoo_var.set(want_o)
        want_c = bool(s.auto.get("converge_enabled"))
        if bool(self.autoc_var.get()) != want_c:
            self.autoc_var.set(want_c)
        want_p = bool(s.auto.get("prestige_enabled"))
        if bool(self.autop_var.get()) != want_p:
            self.autop_var.set(want_p)
        for rid, entry in self.reserve_entries.items():
            shown = Num.from_json(s.auto.get("reserve", {}).get(rid, 0)).to_json()
            if entry.get().strip() != shown and self.root.focus_get() is not entry:
                entry.delete(0, "end")
                entry.insert(0, shown)

    def _refresh_automation(self):
        s = self.state
        self._sync_automation_controls()
        unlocked = s.has_flag("autobuy")
        for g in G.GENERATORS:
            cb = self.widgets[f"auto_{g.id}"]
            show = unlocked and g.id in s.unlocked
            if show and not is_packed(cb):
                cb.pack(fill="x", padx=24)
            elif not show and is_packed(cb):
                cb.pack_forget()
        for key, (var, cb, flag) in self.standing.items():
            state = "normal" if s.has_flag(flag) else "disabled"
            cb.config(state=state, fg=FG if state == "normal" else DIM)
        ap = "normal" if s.has_flag("auto_prestige") else "disabled"
        self.autop_cb.config(state=ap, fg=FG if ap == "normal" else DIM)
        self.autop_entry.config(state=ap)
        ac = "normal" if s.has_flag("auto_converge") else "disabled"
        self.autoc_cb.config(state=ac, fg=FG if ac == "normal" else DIM)
        self.autoc_entry.config(state=ac)
        ao = "normal" if s.has_flag("auto_overwrite") else "disabled"
        self.autoo_cb.config(state=ao, fg=FG if ao == "normal" else DIM)
        self.autoo_entry.config(state=ao)

    def _refresh_stats(self):
        s = self.state
        st = s.stats
        lines = [
            f"World seed          {s.rng_seed}",
            f"Playtime            {fmt_time(st.get('playtime', 0))}",
            f"This run            {fmt_time(s.run_time())}",
            f"Sessions            {st.get('sessions', 0)}",
            "",
            f"Machines bought     {st.get('gens_bought', 0):,}",
            f"Upgrades bought     {st.get('upgrades_bought', 0):,}",
            f"Research completed  {st.get('research_bought', 0):,}",
            "",
            f"Alloy this run      {fmt(s.run_life.get('alloy', ZERO))}",
            f"Peak Alloy/s        {fmt(s.run_peak_alloy_rate)}",
            f"Best Alloy/s ever   {fmt(Num.from_json(st.get('best_alloy_rate', '0')))}",
            f"Best run Alloy      {fmt(Num.from_json(st.get('best_run_alloy', '0')))}",
            "",
            f"Dispersals          {s.p1_count}",
            f"Convergences        {s.p2_count}",
            f"Overwrites          {s.p3_count}",
            f"Collapses           {s.p4_count}",
            f"Substrate           {fmt(s.p4_sub)}",
            f"Overwrite Charges   {fmt(s.p3_oc)}",
            f"Peak Alloy/s (era)  {fmt(s.p3_peak_rate)}",
            f"Coherence           {fmt(s.p2_coh)}",
            f"Best Coherence gain {fmt(Num.from_json(st.get('best_coh_gain', '0')))}",
            f"Best Seed Points    {fmt(Num.from_json(st.get('best_sp_gain', '0')))}",
            f"Seed Points now     {fmt(s.p1_sp)}",
            "",
            f"Probes sent         {st.get('probes_sent', 0):,}",
            f"Artifacts found     {st.get('artifacts_found', 0):,}",
            f"Anomalies seen      {st.get('anomalies_seen', 0):,}",
        ]
        fused = st.get("artifacts_fused", 0)
        if fused:
            lines.append(f"Relics fused        {fused:,}")
        muts = st.get("artifacts_by_mutation") or {}
        if muts:
            lines.append("  " + "  ".join(
                f"{G.MUTATION_BY_ID[k].name} {v}" for k, v in muts.items()
                if k in G.MUTATION_BY_ID))
        by = st.get("artifacts_by_rarity") or {}
        if by:
            lines.append("  " + "  ".join(
                f"{G.RARITY_BY_ID[r].name} {c}" for r, c in by.items() if r in G.RARITY_BY_ID))
        lines += ["", "Lifetime totals (all runs):"]
        for rid in G.STOCK_RESOURCES:
            total = s.total_life.get(rid, ZERO)
            if total > 0:
                lines.append(f"  {G.RES_BY_ID[rid].name:<10} {fmt(total)}")
        self.stats_label.config(text="\n".join(lines))

        self.milestone_label.config(
            text=f"{len(s.milestones)} / {len(G.MILESTONES)} earned")
        for a in G.ACHIEVEMENTS:
            got = a.id in s.achievements
            if a.hidden and not got:
                self.ach_labels[a.id].config(text="  ???  (hidden)", fg=DIM)
            else:
                self.ach_labels[a.id].config(
                    text=f"  {'✔' if got else '✗'}  {a.name} — {a.desc}",
                    fg=GREEN if got else DIM)

    # -- shutdown --------------------------------------------------------
    def on_close(self):
        if saveman.save(self.state):
            self.root.destroy()
            return
        # Never close silently on a failed save — that is the one moment a
        # whole session can be lost without the player ever being told.
        message = (
            "SEED could not write your save to:\n"
            f"{saveman.save_dir()}\n\n"
            "Your progress from this session would be lost.\n"
            "The save already on disk has NOT been damaged.\n\n"
            "Close anyway?")
        leave = messagebox.askyesno("Save failed", message,
                                    default="no", icon="warning")
        if leave:
            self.root.destroy()
        else:
            self.log("Close cancelled — save failed. Try 'Save now' on the "
                     "Stats tab, or free up disk space.", "warn")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
