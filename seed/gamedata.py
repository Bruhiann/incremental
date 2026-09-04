"""All SEED content, as declarative data.

Nothing in this module executes game logic.  Every generator, upgrade, research
node, milestone, achievement, anomaly and artifact is a frozen record; effects are
declarative (`Eff`) rather than lambdas so they serialize, print and diff cleanly.
Balancing in Phase 6 and content in Phase 7 are edits to these tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bignum import N, Num

SAVE_VERSION = 1
GAME_NAME = "SEED"

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

STOCK = "stock"
RATE = "rate"


@dataclass(frozen=True)
class Res:
    id: str
    name: str
    kind: str = STOCK
    desc: str = ""


RESOURCES: tuple[Res, ...] = (
    Res("ore", "Ore", STOCK, "Raw mass torn out of rock. Buys almost everything early."),
    Res("energy", "Power", RATE, "Not stockpiled. Supply must meet demand or everything throttles."),
    Res("alloy", "Alloy", STOCK, "Refined structural matter. The currency of the mid game."),
    Res("data", "Data", STOCK, "Telemetry from your machines. Spent on Research."),
    Res("isotope", "Isotopes", STOCK, "Fuel for heavy tiers and deep-space probes."),
    Res("exotic", "Exotic Matter", STOCK,
        "Degenerate matter wrung out of a black hole. It powers the deepest "
        "machines and thickens every number you own."),
    Res("nanite", "Nanite Mass", STOCK,
        "Self-replicating matter. It grows in proportion to how much of it "
        "already exists, so it compounds on its own once seeded."),
)
RES_BY_ID = {r.id: r for r in RESOURCES}
STOCK_RESOURCES = tuple(r.id for r in RESOURCES if r.kind == STOCK)

# Resources that belong to the Convergence layer, not to a single run: a
# Dispersal leaves them alone, a Convergence clears them.  Nanite Mass would be
# pointless otherwise -- it would reset to nothing every ten minutes and never
# get the chance to compound.
LAYER_RESOURCES = ("nanite",)

# Resources belonging to the Convergence ERA: Dispersal and Convergence both
# leave them alone, an Overwrite clears them.
COHERE_RESOURCES = ("exotic",)

# ---------------------------------------------------------------------------
# Unlock conditions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cond:
    """Declarative unlock test. Empty condition == always true."""

    res: str | None = None
    amount: Num | None = None
    lifetime: bool = False
    gen: str | None = None
    count: float = 0.0
    flag: str | None = None
    research: str | None = None
    upgrade: str | None = None
    prestige: int = 0
    converge: int = 0
    overwrite: int = 0
    collapse: int = 0
    recurse: int = 0
    all_of: tuple = ()
    any_of: tuple = ()


ALWAYS = Cond()

# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------

MULT_GEN = "mult_gen"        # target = generator id
MULT_LADDER = "mult_ladder"  # target = "E" | "R"
MULT_GLOBAL = "mult_global"
MULT_RES = "mult_res"        # target = resource id
ADD_GROWTH = "add_growth"    # target = gen id | ladder | "*"  (value is negative)
TENFOLD = "tenfold"          # target = gen id | "*", value added to the per-10 bonus
SET_FLAG = "set_flag"        # target = flag name
ADD_SLOT = "add_slot"        # target = "relic" | "probe"
MULT_DROP = "mult_drop"
MULT_SP = "mult_sp"
START_RES = "start_res"      # target = resource id, value = amount per level
START_GEN = "start_gen"      # target = gen id, value = count per level
REFINE_EFF = "refine_eff"    # refineries consume value× less input
MULT_CROSS = "mult_cross"    # scales the Replication -> Extraction coupling
MULT_CAPTURE = "mult_capture"  # scales how much of a stream a converter takes
MULT_AUTOCAT = "mult_autocat"  # scales Autocatalysis
MULT_NANITE = "mult_nanite"  # scales Nanite Mass self-growth
MULT_COH = "mult_coh"        # scales Coherence gained from Convergence
EXPONENT = "exponent"        # raises production to a power: the layer-4 verb
MULT_OC = "mult_oc"          # scales Overwrite Charges
MULT_SUB = "mult_sub"        # scales Substrate gained from a Collapse
KEEP_EXPONENT = "keep_exp"   # exponent carried through a Recursion, per level
KEEP_FLEET = "keep_fleet"    # fraction of the fleet carried through a Recursion
SOFTEN = "soften"            # reduces the per-depth cost handicap: the difficulty dial


@dataclass(frozen=True)
class Eff:
    kind: str
    target: str = ""
    value: float = 1.0


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

EXTRACT = "E"
REPLICATE = "R"
DEFEND = "D"

TENFOLD_BASE = 0.10          # every 10 owned -> x1.10 to that tier
AUTOCATALYSIS_RATE = 0.5     # applied to BOUGHT arms only: never unbounded

# Power demand scales with machines you BUILT, not with the swarm's own
# copies -- otherwise free units pin the throttle at its floor forever and
# the shortage stops being something the player can act on.
CROSS_LADDER_K = 0.08        # mult = prod(1 + K*log10(1+count)) over R tiers >= k
THROTTLE_FLOOR = 0.10
# Converters asymptote to capturing everything, which starves the input
# resource to exactly zero and makes anything priced in it unbuyable.
# A hard ceiling guarantees a share always reaches your pocket.
MAX_CAPTURE = 0.90


@dataclass(frozen=True)
class Gen:
    id: str
    name: str
    ladder: str
    desc: str
    base_cost: Num
    cost_res: str
    growth: float
    tier: int
    produces: str | None = None      # resource id, or another generator id
    base_rate: float = 0.0
    # (input resource, fraction of that resource's INCOME captured per unit)
    consumes: tuple[tuple[str, float], ...] = ()
    # Side outputs: (resource id, share of base_rate). A machine that yields
    # four things at once is a data question, not an engine special case.
    extra: tuple[tuple[str, float], ...] = ()
    draw: float = 0.0                # energy demand per unit
    upkeep: tuple[str, float] = ()   # (resource, per unit per second)
    unlock: Cond = ALWAYS


GENERATORS: tuple[Gen, ...] = (
    # -- Extraction ---------------------------------------------------------
    Gen("E1", "Regolith Scraper", EXTRACT,
        "A blade on a rail. Shaves loose rock into the hopper.",
        N(15), "ore", 1.11, 1, produces="ore", base_rate=0.5),
    Gen("E2", "Solar Film", EXTRACT,
        "Sheets of photovoltaic foil. Adds to your power supply.",
        N(60), "ore", 1.12, 2, produces="energy", base_rate=3.0,
        unlock=Cond(res="ore", amount=N(30), lifetime=True)),
    Gen("E3", "Asteroid Mine", EXTRACT,
        "A shaft sunk into the rock. Far more ore, but it wants power.",
        N(1_200), "ore", 1.14, 3, produces="ore", base_rate=6.0, draw=4.0,
        unlock=Cond(res="ore", amount=N(250), lifetime=True)),
    Gen("E4", "Fusion Cell", EXTRACT,
        "Deuterium pinch reactor. Twenty Solar Films in one housing.",
        N(4_000), "ore", 1.13, 4, produces="energy", base_rate=60.0,
        unlock=Cond(gen="E3", count=5)),
    Gen("E5", "Orbital Refinery", EXTRACT,
        "Diverts part of your Ore stream and melts it into Alloy. Each one "
        "captures 3% more of your Ore income; they stack toward 100%.",
        N(25_000), "ore", 1.15, 5, produces="alloy", base_rate=0.08,
        consumes=(("ore", 0.03),), draw=30.0,
        unlock=Cond(gen="E3", count=15)),
    Gen("E6", "Data Loom", EXTRACT,
        "Correlates machine telemetry into usable Data.",
        N(5_000), "alloy", 1.14, 6, produces="data", base_rate=0.4, draw=20.0,
        unlock=Cond(res="alloy", amount=N(500), lifetime=True)),
    Gen("E7", "Planetary Excavator", EXTRACT,
        "A walking strip mine. Eats continents.",
        N(60_000), "alloy", 1.15, 7, produces="ore", base_rate=4_000.0, draw=400.0,
        unlock=Cond(research="r_landfall")),
    Gen("E8", "Stellar Siphon", EXTRACT,
        "Skims fusing plasma off a star and condenses the Isotopes.",
        N(2e6), "alloy", 1.15, 8, produces="isotope", base_rate=0.5, draw=5_000.0,
        unlock=Cond(research="r_starlift")),

    Gen("E9", "Nanite Vat", EXTRACT,
        "Seeds Nanite Mass. Nanites then multiply on their own, in proportion "
        "to how many already exist.",
        N(1e7), "alloy", 1.16, 9, produces="nanite", base_rate=0.5, draw=5e3,
        unlock=Cond(flag="nanites")),

    Gen("E10", "Black Hole Tap", EXTRACT,
        "Lowers a shaft past the ergosphere and draws Exotic Matter off the "
        "spin of a dying star.",
        N(1e18), "alloy", 1.17, 10, produces="exotic", base_rate=2.0, draw=1e7,
        unlock=Cond(flag="exotics")),

    Gen("E11", "Vacuum Decay Well", EXTRACT,
        "Nucleates a bubble of lower vacuum and skims the decay products. "
        "Everything falls out of it: rock, metal, telemetry, fuel.",
        N(1e30), "alloy", 1.18, 11, produces="ore", base_rate=1e18, draw=1e11,
        extra=(("alloy", 0.01), ("data", 1e-4), ("isotope", 1e-6)),
        unlock=Cond(flag="unlock_e11")),

    # -- Replication --------------------------------------------------------
    Gen("R1", "Fabricator Arm", REPLICATE,
        "Builds Regolith Scrapers for free, forever. The first machine that buys "
        "a machine without being asked.",
        N(600), "ore", 1.16, 1, produces="E1", base_rate=0.04, draw=2.0,
        unlock=Cond(res="ore", amount=N(150), lifetime=True)),
    Gen("R2", "Replicator", REPLICATE,
        "Builds Fabricator Arms. This is where the curve starts to bend.",
        N(40_000), "ore", 1.17, 2, produces="R1", base_rate=0.02, draw=10.0,
        unlock=Cond(gen="R1", count=10)),
    Gen("R3", "Forge Spider", REPLICATE,
        "Builds Replicators. Costs Alloy every second to keep walking.",
        N(1e7), "ore", 1.18, 3, produces="R2", base_rate=0.015,
        upkeep=("alloy", 1.0),
        unlock=Cond(all_of=(Cond(prestige=1), Cond(gen="R2", count=10)))),
    Gen("R4", "Seed Ship", REPLICATE,
        "Builds Forge Spiders. A factory that crosses the dark on its own.",
        N(2e9), "alloy", 1.19, 4, produces="R3", base_rate=0.010,
        upkeep=("alloy", 8.0),
        unlock=Cond(all_of=(Cond(prestige=3), Cond(gen="R3", count=10)))),
    Gen("R5", "Hive Ark", REPLICATE,
        "Builds Seed Ships. A world that exists to launch worlds, paid for in "
        "matter that should not hold together.",
        N(1e6), "exotic", 1.20, 5, produces="R4", base_rate=0.008,
        upkeep=("alloy", 40.0),
        unlock=Cond(all_of=(Cond(flag="exotics"), Cond(gen="R4", count=10)))),
    Gen("R8", "Galactic Bloom", REPLICATE,
        "Builds Hive Arks. Seen from far enough away it is not a machine, it "
        "is a change in what the galaxy is made of.",
        N(1e40), "alloy", 1.21, 6, produces="R5", base_rate=0.006,
        upkeep=("alloy", 200.0),
        unlock=Cond(flag="unlock_r8")),

    # -- Defence ------------------------------------------------------------
    #
    # These gate on the economy, never on each other.  The incursion
    # requirement is sized from the best tier you have unlocked, so a
    # count-based unlock created a feedback loop: buying D1 unlocked D2, which
    # raised the very bar the D1 was bought to clear.
    #
    # These produce NOTHING.  They draw power, they eat upkeep, and they are the
    # first line item in the game that is pure cost -- which is the entire point
    # of the Defection: a decision the economy on its own cannot pose.
    #
    # `base_rate` is read as fleet POWER here, never as a production rate; the
    # production loops walk EXTRACT_GENS and REPLICATE_GENS explicitly, so a D
    # tier is inert to them by construction rather than by a special case.
    Gen("D1", "Sentry Drone", DEFEND,
        "A cheap hull with one gun and no opinions. Shoots what stopped "
        "answering.",
        N(500), "ore", 1.13, 1, base_rate=1.0, draw=3.0,
        unlock=Cond(flag="see_combat")),
    Gen("D2", "Picket Cruiser", DEFEND,
        "Stands off and volleys. Worth a dozen drones and cheaper to keep than "
        "a dozen drones.",
        N(25_000), "alloy", 1.14, 2, base_rate=12.0, draw=25.0,
        unlock=Cond(all_of=(Cond(flag="see_combat"),
                            Cond(res="alloy", amount=N(1e5), lifetime=True)))),
    Gen("D3", "Lance Frigate", DEFEND,
        "One long gun with a ship bolted behind it. Costs Alloy every second "
        "to keep the coils cold.",
        N(5e6), "alloy", 1.15, 3, base_rate=200.0, draw=300.0,
        upkeep=("alloy", 2.0),
        unlock=Cond(all_of=(Cond(flag="see_combat"),
                            Cond(res="alloy", amount=N(1e9), lifetime=True)))),
    Gen("D4", "Bastion", DEFEND,
        "A fortress that does not move, because nothing it fights gets to "
        "choose the ground.",
        N(1e10), "alloy", 1.16, 4, base_rate=4e3, draw=2e4,
        upkeep=("alloy", 20.0),
        unlock=Cond(all_of=(Cond(flag="see_combat"),
                            Cond(res="alloy", amount=N(1e14), lifetime=True)))),
    Gen("D5", "Nemesis Hull", DEFEND,
        "Built from the same pattern as the things it kills, and better at it.",
        N(1e18), "alloy", 1.17, 5, base_rate=1e5, draw=1e8,
        upkeep=("isotope", 200.0),
        unlock=Cond(all_of=(Cond(flag="exotics"),
                            Cond(res="alloy", amount=N(1e22), lifetime=True)))),
)
GEN_BY_ID = {g.id: g for g in GENERATORS}
EXTRACT_GENS = tuple(g for g in GENERATORS if g.ladder == EXTRACT)
REPLICATE_GENS = tuple(g for g in GENERATORS if g.ladder == REPLICATE)
DEFEND_GENS = tuple(g for g in GENERATORS if g.ladder == DEFEND)
ENERGY_GENS = tuple(g.id for g in GENERATORS if g.produces == "energy")

# ---------------------------------------------------------------------------
# The Defection — threat and incursions
# ---------------------------------------------------------------------------
#
# You built self-replicating machines.  Some of them stopped answering.  Threat
# accrues from the size of your own Replication swarm, so the pressure is
# generated by your success rather than by a timer.
#
# Log-damped for the same reason the cross-ladder rule is: a swarm of 1e20
# should contribute ~20, not 1e20.  Everything in this game that reads a count
# and turns it into pressure has to go through a log or it detonates.
# FREQUENCY and MAGNITUDE are separated on purpose, because tying both to the
# swarm made each one break in a different direction.
#
# Frequency is a period in seconds.  Threat was first written as
# 0.9*log10(swarm) against a fixed bar, which on a real endgame save came to
# 5.4e15 threat per second against a bar of 600: an incursion every tick,
# forever.  A period is legible, tunable, and cannot run away.
INCURSION_PERIOD = 600.0        # seconds between incursions, at zero wins
PERIOD_GROWTH_EXP = 0.15        # ...stretching with your war record

# Magnitude is measured against your BANK, not against your swarm.  The swarm
# is built for free by replication and grows hyper-exponentially; a fleet must
# be bought, and cost is exponential in count, so affordable fleet power is
# only logarithmic in cash.  Sizing an incursion off the swarm therefore made
# it literally unwinnable on a deep save -- measured at 1e7.5Qa damage/s needed
# against 1e2.2Qa affordable, a gap of 1e5e15.  Sizing it off what a share of
# your bank buys keeps the demand honest at every scale and makes the decision
# the one this system exists for: park this much of your wealth in something
# that produces nothing.
DEFENCE_SHARE = 0.10

# A fight is a race, not a coin flip: the incursion has HP, your fleet has DPS,
# and the faster you kill it the less it takes from you.  "Kill it sooner, lose
# less" is a rule a player can hold in their head and act on.
TARGET_FIGHT = 60.0             # what an adequate fleet clears an incursion in
# ...and a hard stop, so a fleet of zero cannot bleed you forever.  Breaking off
# is a LOSS, but it is a bounded one: this cap times the attrition rate below is
# the worst thing combat can ever do to you.
INCURSION_TIME = 120.0
# Fraction of a tier destroyed per second at maximum pressure.  120 s x 0.004 is
# a worst case of 48% of the swarm, from a standing start with no fleet at all.
ATTRITION_FRACTION = 0.004
# Bigger machines are harder to kill: tier t loses 1/(1 + TOUGHNESS*(t-1)) of
# the base fraction.  The cheap tiers absorb the damage, which is both what
# attrition means and where a rebuild costs the least.
TIER_TOUGHNESS = 0.5
# Winning pays into the economy so combat is not a pure tax:
#   global multiplier = 1 + COMBAT_WIN_K * log10(1 + wins)
COMBAT_WIN_K = 0.5
SALVAGE_SECONDS = 90.0          # a win pays this many seconds of Alloy income
SALVAGE_RARITY_BIAS = 1.4
# The first incursion is scripted and unlosable: it teaches the system instead
# of taxing it.  Every player meets combat at full strength and zero cost once.
TUTORIAL_INCURSION = 1

# ---------------------------------------------------------------------------
# Upgrades
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Upg:
    id: str
    name: str
    desc: str
    cost: Num
    cost_res: str
    effect: Eff
    unlock: Cond = ALWAYS
    major: bool = False   # gold frame + popup


UPGRADES: tuple[Upg, ...] = (
    # -- early game --------------------------------------------------------
    # Minutes 5-10 were the thinnest stretch of the game: E3 and E4 are bought
    # and Alloy has not started flowing yet.  These fill that gap.
    Upg("u_e1_0", "Sharpened Rails", "Regolith Scrapers produce 50% more Ore.",
        N(60), "ore", Eff(MULT_GEN, "E1", 1.5), Cond(gen="E1", count=5)),
    Upg("u_e2_0", "Wiped Panels", "Solar Films produce 50% more Power.",
        N(220), "ore", Eff(MULT_GEN, "E2", 1.5), Cond(gen="E2", count=5)),
    Upg("u_r1_0", "Faster Servos", "Fabricator Arms work 50% faster.",
        N(2_200), "ore", Eff(MULT_GEN, "R1", 1.5), Cond(gen="R1", count=3)),
    Upg("u_e3_0", "Wider Shafts", "Asteroid Mines produce 50% more Ore.",
        N(3_500), "ore", Eff(MULT_GEN, "E3", 1.5), Cond(gen="E3", count=3)),
    Upg("u_ten_0", "Batch Tooling",
        "Regolith Scrapers get a bigger bonus for every 10 you own (x1.12).",
        N(7_500), "ore", Eff(TENFOLD, "E1", 0.02), Cond(gen="E1", count=30)),
    Upg("u_e4_0", "Better Injectors", "Fusion Cells produce 50% more Power.",
        N(14_000), "ore", Eff(MULT_GEN, "E4", 1.5), Cond(gen="E4", count=3)),
    Upg("u_g0", "Standard Fasteners", "All Extraction machines produce 25% more.",
        N(22_000), "ore", Eff(MULT_LADDER, EXTRACT, 1.25), Cond(gen="E3", count=8)),
    Upg("u_pow_0", "Grid Tuning", "All Power machines produce 50% more.",
        N(40_000), "ore", Eff(MULT_RES, "energy", 1.5), Cond(gen="E4", count=5)),
    Upg("u_e5_0", "Wider Intakes",
        "Orbital Refineries capture 50% more of your Ore stream.",
        N(55_000), "ore", Eff(MULT_CAPTURE, "", 1.5), Cond(gen="E5", count=3)),
    Upg("u_e6_0", "Extra Spindles", "Data Looms produce 50% more Data.",
        N(6_000), "alloy", Eff(MULT_GEN, "E6", 1.5), Cond(gen="E6", count=5)),

    Upg("u_e1_1", "Tungsten Teeth", "Regolith Scrapers produce 100% more Ore.",
        N(120), "ore", Eff(MULT_GEN, "E1", 2.0), Cond(gen="E1", count=10)),
    Upg("u_e1_2", "Vibration Bits", "Regolith Scrapers produce 100% more Ore.",
        N(3_000), "ore", Eff(MULT_GEN, "E1", 2.0), Cond(gen="E1", count=25)),
    Upg("u_e1_3", "Electrostatic Sifting", "Regolith Scrapers produce 200% more Ore.",
        N(90_000), "ore", Eff(MULT_GEN, "E1", 3.0), Cond(gen="E1", count=60)),

    Upg("u_e2_1", "Doped Substrate", "Solar Films produce 100% more Power.",
        N(500), "ore", Eff(MULT_GEN, "E2", 2.0), Cond(gen="E2", count=10)),
    Upg("u_e2_2", "Sun Tracking", "Solar Films produce 100% more Power.",
        N(14_000), "ore", Eff(MULT_GEN, "E2", 2.0), Cond(gen="E2", count=25)),

    Upg("u_e3_1", "Deep Bore Heads", "Asteroid Mines produce 100% more Ore.",
        N(9_000), "ore", Eff(MULT_GEN, "E3", 2.0), Cond(gen="E3", count=10)),
    Upg("u_e3_2", "Slag Reclamation", "Asteroid Mines produce 150% more Ore.",
        N(200_000), "ore", Eff(MULT_GEN, "E3", 2.5), Cond(gen="E3", count=25)),

    Upg("u_e4_1", "Magnetic Confinement", "Fusion Cells produce 100% more Power.",
        N(50_000), "ore", Eff(MULT_GEN, "E4", 2.0), Cond(gen="E4", count=10)),
    Upg("u_e4_2", "Tritium Breeding", "Fusion Cells produce 150% more Power.",
        N(1.2e6), "ore", Eff(MULT_GEN, "E4", 2.5), Cond(gen="E4", count=25)),

    Upg("u_e5_1", "Flux Catalysts", "Orbital Refineries produce 100% more Alloy.",
        N(120_000), "ore", Eff(MULT_GEN, "E5", 2.0), Cond(gen="E5", count=5)),
    Upg("u_e5_2", "Continuous Casting", "Refineries yield 40% more Alloy per Ore.",
        N(400_000), "ore", Eff(MULT_GEN, "E5", 1.4), Cond(gen="E5", count=12)),

    Upg("u_e6_1", "Parallel Looms", "Data Looms produce 100% more Data.",
        N(20_000), "alloy", Eff(MULT_GEN, "E6", 2.0), Cond(gen="E6", count=10)),

    Upg("u_r1_1", "Servo Overclock", "Fabricator Arms work 100% faster.",
        N(1_500), "ore", Eff(MULT_GEN, "R1", 2.0), Cond(gen="R1", count=10)),
    Upg("u_r1_2", "Twin Manipulators", "Fabricator Arms work 100% faster.",
        N(40_000), "ore", Eff(MULT_GEN, "R1", 2.0), Cond(gen="R1", count=25)),
    Upg("u_r2_1", "Recursive Blueprints", "Replicators build 100% faster.",
        N(60_000), "ore", Eff(MULT_GEN, "R2", 2.0), Cond(gen="R2", count=10)),
    Upg("u_r3_1", "Spinneret Arrays", "Forge Spiders build 100% faster.",
        N(3e6), "ore", Eff(MULT_GEN, "R3", 2.0), Cond(gen="R3", count=10)),

    Upg("u_g1", "Standardised Parts", "All Extraction machines produce 50% more.",
        N(150_000), "ore", Eff(MULT_LADDER, EXTRACT, 1.5), Cond(gen="E3", count=20)),
    Upg("u_g2", "Swarm Doctrine", "All Replication machines work 50% faster.",
        N(750_000), "ore", Eff(MULT_LADDER, REPLICATE, 1.5), Cond(gen="R2", count=15)),
    Upg("u_g3", "Interchangeable Tooling", "All machine costs scale 0.5% more slowly.",
        N(2e6), "ore", Eff(ADD_GROWTH, "*", -0.005), Cond(gen="E5", count=10)),
    Upg("u_g4", "Batch Assembly", "The bonus for every 10 owned rises from x1.10 to x1.15.",
        N(2e6), "alloy", Eff(TENFOLD, "*", 0.05), Cond(res="alloy", amount=N(1e6), lifetime=True)),

    # -- major, gold-framed -------------------------------------------------
    Upg("u_m_surplus", "Surplus Bleed",
        "Power you are not using is cast into Alloy instead of being wasted.",
        N(300_000), "ore", Eff(SET_FLAG, "surplus_bleed"), Cond(gen="E5", count=5),
        major=True),
    Upg("u_m_telemetry", "Telemetry Bus",
        "Every machine you own, of every kind, now trickles out Data.",
        N(150_000), "alloy", Eff(SET_FLAG, "telemetry"), Cond(gen="E6", count=15),
        major=True),
    Upg("u_m_selfrep", "Autocatalysis",
        "Every Fabricator Arm you have BUILT also builds more Fabricator Arms.",
        N(5e7), "alloy", Eff(SET_FLAG, "autocatalysis"), Cond(gen="R3", count=20),
        major=True),
)
UPG_BY_ID = {u.id: u for u in UPGRADES}

# ---------------------------------------------------------------------------
# Research  (bought with Data; survives Dispersal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tech:
    id: str
    name: str
    desc: str
    cost: Num
    effect: Eff
    unlock: Cond = ALWAYS
    major: bool = False


RESEARCH: tuple[Tech, ...] = (
    Tech("r_foreman", "Foreman Protocol",
         "Unlocks per-machine auto-buy toggles and a spending reserve.",
         N(40), Eff(SET_FLAG, "autobuy"), major=True),
    Tech("r_grid1", "Grid Conditioning", "All Power machines produce 100% more.",
         N(120), Eff(MULT_RES, "energy", 2.0)),
    Tech("r_reflux", "Reflux Refining", "Orbital Refineries produce 150% more Alloy.",
         N(400), Eff(MULT_GEN, "E5", 2.5), Cond(gen="E5", count=1)),
    Tech("r_probes", "Probe Doctrine",
         "Unlocks Exploration: send probes into the dark and see what comes back.",
         N(600), Eff(SET_FLAG, "exploration"), Cond(prestige=1), major=True),
    Tech("r_metallurgy", "Applied Metallurgy", "All Extraction machines produce 100% more.",
         N(1_500), Eff(MULT_LADDER, EXTRACT, 2.0)),
    Tech("r_landfall", "Landfall", "Unlocks the Planetary Excavator.",
         N(3_000), Eff(SET_FLAG, "landfall"),
         Cond(all_of=(Cond(prestige=1), Cond(res="alloy", amount=N(50_000), lifetime=True))),
         major=True),
    Tech("r_transmute", "Transmutation",
         "Unlocks the Crucible: melt three relics of one rarity into a single "
         "relic of the next rarity up.",
         N(2_500), Eff(SET_FLAG, "fusion"), Cond(flag="exploration"), major=True),
    Tech("r_relic", "Containment Frame", "One more Relic slot.",
         N(5_000), Eff(ADD_SLOT, "relic", 1), Cond(flag="exploration")),
    Tech("r_swarmlogic", "Swarm Logic", "All Replication machines work 100% faster.",
         N(12_000), Eff(MULT_LADDER, REPLICATE, 2.0)),
    Tech("r_probe_bay", "Second Probe Bay", "One more probe can be in flight at a time.",
         N(20_000), Eff(ADD_SLOT, "probe", 1), Cond(flag="exploration")),
    Tech("r_grid2", "Superconducting Grid", "All Power machines produce 200% more.",
         N(50_000), Eff(MULT_RES, "energy", 3.0)),
    Tech("r_starlift", "Starlift", "Unlocks the Stellar Siphon and the Isotope economy.",
         N(150_000), Eff(SET_FLAG, "starlift"), Cond(prestige=2),
         major=True),
    Tech("r_tooling", "Precision Tooling", "All machine costs scale 1% more slowly.",
         N(400_000), Eff(ADD_GROWTH, "*", -0.01)),
    Tech("r_deepscan", "Deep Scan", "Probes find rare things 50% more often.",
         N(1e6), Eff(MULT_DROP, "", 1.5), Cond(flag="exploration")),
)
TECH_BY_ID = {t.id: t for t in RESEARCH}

# ---------------------------------------------------------------------------
# Prestige layer 1 — Dispersal
# ---------------------------------------------------------------------------

P1_UNLOCK_ALLOY = N(1e6)          # lifetime Alloy needed to SEE the Dispersal tab
P1_BASE = 12.0

# The Alloy needed to Disperse rises with the Seed Points you already hold:
#     required = P1_REQ_BASE * (1 + lifetime SP) ** P1_REQ_EXP
# Without this the requirement is trivially re-cleared once you are strong and
# the game degenerates into a one-minute reset treadmill.  The bar and your
# power grow together instead, so runs keep their shape.
P1_REQ_BASE = N(1e12)
P1_REQ_EXP = 0.50

# Seed Points come from the LOGARITHM of how far past the bar you went:
#     gain = P1_BASE * (orders_of_magnitude_past_the_bar + 1) ** P1_LOG_EXP
#
# A power-law gain never peaks against this economy's growth, so "never reset"
# stays optimal and the prestige decision evaporates.  The log form makes Seed
# Points per second peak sharply, which is what turns "when do I reset?" into a
# real question.  It also keeps Seed Points small enough to read and to price
# the Seed Grid against.
P1_LOG_EXP = 2.0


@dataclass(frozen=True)
class SeedUpg:
    id: str
    name: str
    desc: str
    base_cost: float
    cost_growth: float
    max_level: int          # 0 == endless, like the Coherence shop
    effect: Eff


SEED_GRID: tuple[SeedUpg, ...] = (
    SeedUpg("sg_global", "Inherited Design",
            "+25% to everything you produce, per level.", 1, 1.8, 0,
            Eff(MULT_GLOBAL, "", 1.25)),
    SeedUpg("sg_ore", "Ore Memory", "Ore machines produce +50% per level.", 2, 1.7, 0,
            Eff(MULT_RES, "ore", 1.5)),
    SeedUpg("sg_energy", "Power Memory", "Power machines produce +50% per level.", 2, 1.7, 0,
            Eff(MULT_RES, "energy", 1.5)),
    SeedUpg("sg_alloy", "Alloy Memory", "Refineries produce +50% per level.", 4, 1.75, 0,
            Eff(MULT_RES, "alloy", 1.5)),
    SeedUpg("sg_rep", "Replication Memory",
            "Replication machines work +50% faster per level.", 8, 1.8, 0,
            Eff(MULT_LADDER, REPLICATE, 1.5)),
    SeedUpg("sg_cheap", "Cached Blueprints",
            "All machine costs scale 0.3% more slowly per level.", 15, 2.2, 15,
            Eff(ADD_GROWTH, "*", -0.003)),
    SeedUpg("sg_start_ore", "Cargo Reserve",
            "Begin each Dispersal with 10x more starting Ore per level.", 3, 2.0, 20,
            Eff(START_RES, "ore", 10.0)),
    SeedUpg("sg_start_e", "Pre-Sown Machines",
            "Begin each Dispersal owning 5 more of E1-E3 per level.", 6, 2.1, 20,
            Eff(START_GEN, "E", 5)),
    SeedUpg("sg_start_r", "Pre-Sown Fabricators",
            "Begin each Dispersal owning 2 more Fabricator Arms per level.", 25, 2.3, 20,
            Eff(START_GEN, "R1", 2)),
    SeedUpg("sg_autobuy", "Permanent Foreman",
            "Auto-buy is unlocked from the start of every Dispersal.", 20, 1.0, 1,
            Eff(SET_FLAG, "perm_autobuy")),
    SeedUpg("sg_autores", "Standing Research Orders",
            "Research buys itself, cheapest first.", 60, 1.0, 1,
            Eff(SET_FLAG, "auto_research")),
    SeedUpg("sg_autoupg", "Standing Upgrade Orders",
            "Upgrades buy themselves, cheapest first.", 90, 1.0, 1,
            Eff(SET_FLAG, "auto_upgrade")),
    SeedUpg("sg_autofuse", "Automatic Crucible",
            "Spare relics fuse themselves. Never touches anything you are using.",
            200, 1.0, 1, Eff(SET_FLAG, "auto_fuse")),
    SeedUpg("sg_autorelic", "Curator Protocol",
            "Your best relics are slotted automatically as you find them.",
            150, 1.0, 1, Eff(SET_FLAG, "auto_relic")),
    SeedUpg("sg_autoexp", "Standing Probe Orders",
            "Probes launch themselves whenever a bay is free.", 120, 1.0, 1,
            Eff(SET_FLAG, "auto_expedition")),
    SeedUpg("sg_autobal", "Load Balancer",
            "Auto-buy spends preferentially on whatever is throttling you.", 400, 1.0, 1,
            Eff(SET_FLAG, "auto_balance")),
    SeedUpg("sg_relic", "Relic Harness", "+1 Relic slot per level.", 40, 3.0, 6,
            Eff(ADD_SLOT, "relic", 1)),
    SeedUpg("sg_drop", "Fine Sieves", "+25% chance to find artifacts, per level.", 30, 2.0, 0,
            Eff(MULT_DROP, "", 1.25)),
    SeedUpg("sg_sp", "Denser Seed", "+10% Seed Points from every Dispersal, per level.",
            50, 2.5, 0, Eff(MULT_SP, "", 1.10)),
)
SEED_BY_ID = {s.id: s for s in SEED_GRID}

# ---------------------------------------------------------------------------
# Later prestige layers — declared now so resets and saves already know them
# ---------------------------------------------------------------------------

RUN = "run"          # wiped by Dispersal (P1)
LAYER = "layer"      # wiped by Convergence (P2)
COHERE = "cohere"    # wiped by Overwrite (P3): Coherence and everything it bought
OVER = "over"        # wiped by Substrate Collapse (P4): Charges and the Floors
SUB = "sub"          # wiped by Recursion (P5): Substrate, the Lattice, the depth
PERMANENT = "perm"   # never wiped


@dataclass(frozen=True)
class Layer:
    id: str
    index: int
    name: str
    verb: str
    currency: str
    currency_name: str
    wipes: tuple[str, ...]
    implemented: bool = False


LAYERS: tuple[Layer, ...] = (
    Layer("p1", 1, "Dispersal", "Disperse", "sp", "Seed Points", (RUN,), True),
    Layer("p2", 2, "Convergence", "Converge", "coh", "Coherence", (RUN, LAYER), True),
    Layer("p3", 3, "Overwrite", "Overwrite", "oc", "Overwrite Charges",
          (RUN, LAYER, COHERE), True),
    Layer("p4", 4, "Substrate Collapse", "Collapse", "sub", "Substrate",
          (RUN, LAYER, COHERE, OVER), True),
    Layer("p5", 5, "Recursion", "Recurse", "depth", "Recursion Depth",
          (RUN, LAYER, COHERE, OVER, SUB), True),
)
LAYER_BY_ID = {l.id: l for l in LAYERS}

# ---------------------------------------------------------------------------
# Prestige layer 2 — Convergence
# ---------------------------------------------------------------------------
#
# Your scattered seeds re-merge into one distributed intelligence.  Convergence
# wipes Seed Points, the Seed Grid and Research on top of everything Dispersal
# resets, and in exchange changes what you are doing: Nanite Mass, Doctrines you
# CHOOSE rather than buy, auto-Dispersal, and an endless Coherence shop.
#
# Gain uses the same logarithmic shape as Seed Points, for the same reason: a
# power law never peaks against this economy, so reset timing would have no
# answer.  See BALANCE.md.

P2_UNLOCK_SP = N(20_000)          # lifetime Seed Points needed to SEE the tab
P2_BASE = 10.0
P2_LOG_EXP = 2.2
P2_REQ_BASE = N(2e5)           # lifetime Seed Points needed to Converge
P2_REQ_EXP = 0.65                # bar rises with the Coherence you already hold

# Nanite Mass compounds: rate = nanites * NANITE_SELF_RATE (plus vat seeding).
# Its EFFECT is logarithmic, so an exponential resource stays balanced while
# still feeling like a number that runs away from you.
# Convergence seeds this directly: a resource that compounds from nothing
# never starts, and the Vat alone is too far out of reach to be the hook.
NANITE_SEED = 250.0
NANITE_SELF_RATE = 0.004
NANITE_POWER = 0.60              # global mult = (1 + log10(1+nanites)) ** POWER


@dataclass(frozen=True)
class Doctrine:
    id: str
    row: int
    name: str
    desc: str
    effect: Eff


# Five rows, three mutually exclusive branches each.  Free, and re-picked from
# scratch at every Convergence, so a wrong choice is never a permanent regret.
DOCTRINES: tuple[Doctrine, ...] = (
    Doctrine("d1_swarm", 1, "Swarm: Proliferate",
             "All Replication machines work 200% faster.",
             Eff(MULT_LADDER, REPLICATE, 3.0)),
    Doctrine("d1_forge", 1, "Forge: Extract",
             "All Extraction machines produce 200% more.",
             Eff(MULT_LADDER, EXTRACT, 3.0)),
    Doctrine("d1_mind", 1, "Mind: Observe",
             "Data production x10.",
             Eff(MULT_RES, "data", 10.0)),

    Doctrine("d2_swarm", 2, "Swarm: Entangle",
             "The Replication-to-Extraction bonus is twice as strong.",
             Eff(MULT_CROSS, "", 2.0)),
    Doctrine("d2_forge", 2, "Forge: Intake",
             "Refineries capture twice as much of your Ore stream.",
             Eff(MULT_CAPTURE, "", 2.0)),
    Doctrine("d2_mind", 2, "Mind: Divine",
             "Artifacts are found three times as often.",
             Eff(MULT_DROP, "", 3.0)),

    Doctrine("d3_swarm", 3, "Swarm: Standardise",
             "Every 10 owned now gives x1.18 instead of x1.10.",
             Eff(TENFOLD, "*", 0.08)),
    Doctrine("d3_forge", 3, "Forge: Economise",
             "All machine costs scale 2% more slowly.",
             Eff(ADD_GROWTH, "*", -0.02)),
    Doctrine("d3_mind", 3, "Mind: Distil",
             "Seed Points from every Dispersal are doubled.",
             Eff(MULT_SP, "", 2.0)),

    Doctrine("d4_swarm", 4, "Swarm: Autocatalyse",
             "Autocatalysis is four times as strong.",
             Eff(MULT_AUTOCAT, "", 4.0)),
    Doctrine("d4_forge", 4, "Forge: Overdrive",
             "All Power machines produce 500% more.",
             Eff(MULT_RES, "energy", 6.0)),
    Doctrine("d4_mind", 4, "Mind: Assemble",
             "Nanite Mass grows three times as fast.",
             Eff(MULT_NANITE, "", 3.0)),

    Doctrine("d5_swarm", 5, "Swarm: Saturate",
             "Everything you produce is multiplied by 8.",
             Eff(MULT_GLOBAL, "", 8.0)),
    Doctrine("d5_forge", 5, "Forge: Temper",
             "Ore and Alloy production x25.",
             Eff(MULT_RES, "alloy", 25.0)),
    Doctrine("d5_mind", 5, "Mind: Cohere",
             "Coherence from every Convergence is doubled.",
             Eff(MULT_COH, "", 2.0)),
)
DOCTRINE_BY_ID = {d.id: d for d in DOCTRINES}
DOCTRINE_ROWS = tuple(sorted({d.row for d in DOCTRINES}))


@dataclass(frozen=True)
class CohUpg:
    id: str
    name: str
    desc: str
    base_cost: float
    cost_growth: float
    max_level: int          # 0 == endless
    effect: Eff


# Endless by design: these are the late-game sink that keeps scaling forever.
COHERENCE_GRID: tuple[CohUpg, ...] = (
    CohUpg("c_global", "Coherent Design",
           "+50% to everything you produce, per level.", 1, 1.28, 0,
           Eff(MULT_GLOBAL, "", 1.5)),
    CohUpg("c_rep", "Coherent Replication",
           "Replication machines work +80% faster per level.", 2, 1.30, 0,
           Eff(MULT_LADDER, REPLICATE, 1.8)),
    CohUpg("c_sp", "Seeded Memory",
           "+40% Seed Points from every Dispersal, per level.", 3, 1.32, 0,
           Eff(MULT_SP, "", 1.4)),
    CohUpg("c_cheap", "Inherited Tooling",
           "All machine costs scale 0.4% more slowly per level.", 8, 1.55, 40,
           Eff(ADD_GROWTH, "*", -0.004)),
    CohUpg("c_nanite", "Nanite Doctrine",
           "Nanite Mass grows +60% faster per level.", 5, 1.34, 0,
           Eff(MULT_NANITE, "", 1.6)),
    CohUpg("c_cross", "Deep Coupling",
           "The Replication-to-Extraction bonus is +25% stronger per level.",
           10, 1.45, 30, Eff(MULT_CROSS, "", 1.25)),
    CohUpg("c_autoseed", "Standing Seed Orders",
           "The Seed Grid buys itself, always taking whichever level is "
           "cheapest next. Together with Standing Dispersal Orders this makes "
           "the whole Dispersal layer hands-off.", 15, 1.0, 1,
           Eff(SET_FLAG, "auto_seed")),
    CohUpg("c_autoprestige", "Standing Dispersal Orders",
           "Dispersal can run itself at a threshold you choose.", 4, 1.0, 1,
           Eff(SET_FLAG, "auto_prestige")),
    CohUpg("c_start", "Converged Cache",
           "Begin every Dispersal with 100x more starting Ore, per level.",
           6, 1.50, 30, Eff(START_RES, "ore", 100.0)),
)
COH_BY_ID = {c.id: c for c in COHERENCE_GRID}

# ---------------------------------------------------------------------------
# Prestige layer 3 — Overwrite
# ---------------------------------------------------------------------------
#
# Overwrite wipes Coherence and everything it bought, on top of everything
# Convergence resets.  What makes it a different KIND of layer is the currency:
# Overwrite Charges come from your PEAK Alloy per second, not from a lifetime
# total.  Waiting cannot earn them -- only a better engine can.  And what they
# buy are floors: permanent starting states, so the early game stops being
# something you replay at all.

P3_UNLOCK_COH = N(150)           # lifetime Coherence needed to SEE the tab
# Production goes hyper-exponential up here: log10(peak Alloy/s) itself reaches
# the quadrillions. A gain that is any ordinary function of depth therefore runs
# to 1e13 Charges against a shop priced in thousands. Gain is taken from the
# log OF the depth, so it stays in a readable band across the whole range, and
# the shop's prices grow gently enough for it to keep buying levels.
P3_BASE = 10.0
P3_LOG_EXP = 1.9
P3_REQ_BASE = N(1e90)            # peak Alloy/s needed for the first Overwrite
P3_REQ_EXP = 4.0                 # ...rising steeply with charges already held

# Exotic Matter, like Nanites, is scored logarithmically: the number runs away,
# the balance does not.
EXOTIC_POWER = 0.75


@dataclass(frozen=True)
class OverUpg:
    id: str
    name: str
    desc: str
    base_cost: float
    cost_growth: float
    max_level: int          # 0 == endless
    effect: Eff


OVERWRITE_GRID: tuple[OverUpg, ...] = (
    OverUpg("ow_floor_e", "Substrate Cache",
            "Begin every Dispersal owning 25 more of each Extraction machine "
            "E1-E5, per level.", 3, 1.14, 0, Eff(START_GEN, "EARLY_E", 25)),
    OverUpg("ow_floor_r", "Seeded Swarm",
            "Begin every Dispersal owning 10 more of each Replication machine "
            "R1-R3, per level.", 5, 1.15, 0, Eff(START_GEN, "EARLY_R", 10)),
    OverUpg("ow_global", "Rewritten Constants",
            "Everything you produce x3, per level.", 2, 1.13, 0,
            Eff(MULT_GLOBAL, "", 3.0)),
    OverUpg("ow_sp", "Deep Memory",
            "Seed Points from every Dispersal x2, per level.", 4, 1.15, 0,
            Eff(MULT_SP, "", 2.0)),
    OverUpg("ow_coh", "Resonant Memory",
            "Coherence from every Convergence x2, per level.", 6, 1.16, 0,
            Eff(MULT_COH, "", 2.0)),
    OverUpg("ow_exotic", "Exotic Affinity",
            "Black Hole Taps yield x5 more Exotic Matter, per level.", 8, 1.16, 0,
            Eff(MULT_GEN, "E10", 5.0)),
    OverUpg("ow_cheap", "Overwritten Costs",
            "All machine costs scale 1% more slowly, per level.", 12, 1.30, 40,
            Eff(ADD_GROWTH, "*", -0.01)),
    OverUpg("ow_relic", "Rewritten Frame", "+2 Relic slots per level.",
            20, 1.80, 10, Eff(ADD_SLOT, "relic", 2)),
    OverUpg("ow_archive", "Persistent Archive",
            "Research survives Convergence. You never re-learn anything again.",
            40, 1.0, 1, Eff(SET_FLAG, "keep_research")),
    OverUpg("ow_autocoh", "Standing Coherence Orders",
            "The Coherence Nodes buy themselves, cheapest level first. The "
            "Convergence layer's answer to Standing Seed Orders.", 30, 1.0, 1,
            Eff(SET_FLAG, "auto_coh")),
    OverUpg("ow_autoconv", "Standing Convergence Orders",
            "Convergence runs itself at a depth you choose.", 60, 1.0, 1,
            Eff(SET_FLAG, "auto_converge")),
    OverUpg("ow_fleet", "Hardened Pattern",
            "Your whole fleet hits x4 harder, per level.", 5, 1.18, 0,
            Eff(MULT_LADDER, DEFEND, 4.0)),
    OverUpg("ow_autodef", "Standing Defence Orders",
            "The fleet buys itself, keeping ahead of the threat by a margin "
            "you choose. You stop watching the bar.", 25, 1.0, 1,
            Eff(SET_FLAG, "auto_defence")),
)
OVER_BY_ID = {o.id: o for o in OVERWRITE_GRID}

# ---------------------------------------------------------------------------
# Prestige layer 4 — Substrate Collapse
# ---------------------------------------------------------------------------
#
# By here every multiplier in the game is astronomical, so another multiplier is
# noise.  Substrate buys EXPONENTS instead: production is raised to a power.
# That is the whole identity of the layer -- you stop building machines and start
# editing the rules the machines obey.

P4_UNLOCK_OC = N(5_000)          # lifetime Charges needed to SEE the tab
P4_BASE = 5.0
P4_LOG_EXP = 2.0
P4_REQ_BASE = N(20_000)          # lifetime Charges needed to Collapse
P4_REQ_EXP = 0.80                # ...rising with the Substrate already held

# One level of the exponent node adds this to the power production is raised to.
# It looks tiny; against a multiplier of 1e12 it is not.
SUBSTRATE_EXP_STEP = 0.002


@dataclass(frozen=True)
class SubUpg:
    id: str
    name: str
    desc: str
    base_cost: float
    cost_growth: float
    max_level: int          # 0 == endless
    effect: Eff


SUBSTRATE_GRID: tuple[SubUpg, ...] = (
    SubUpg("sb_exponent", "Rewritten Physics",
           "Everything you produce is raised to a higher power (+0.002 to the "
           "exponent per level). Against multipliers this large, nothing else "
           "comes close.", 3, 1.25, 0, Eff(EXPONENT, "", SUBSTRATE_EXP_STEP)),
    SubUpg("sb_global", "Constant Rewrite",
           "Everything you produce x10, per level.", 2, 1.22, 0,
           Eff(MULT_GLOBAL, "", 10.0)),
    SubUpg("sb_oc", "Denser Substrate",
           "Overwrite Charges from every Overwrite x3, per level.", 5, 1.30, 0,
           Eff(MULT_OC, "", 3.0)),
    SubUpg("sb_floor", "Deep Cache",
           "Begin every Dispersal owning 100 more of each of E1-E5, per level.",
           4, 1.28, 0, Eff(START_GEN, "EARLY_E", 100)),
    SubUpg("sb_relic", "Woven Frame", "+5 Relic slots per level.",
           25, 1.60, 10, Eff(ADD_SLOT, "relic", 5)),
    SubUpg("sb_genome", "Cached Genome",
           "The Seed Grid survives Convergence. You keep what you bought.",
           40, 1.0, 1, Eff(SET_FLAG, "keep_seed")),
    SubUpg("sb_autoover", "Standing Overwrite Orders",
           "Overwrite runs itself at a depth you choose.", 60, 1.0, 1,
           Eff(SET_FLAG, "auto_overwrite")),
)
SUB_BY_ID = {u.id: u for u in SUBSTRATE_GRID}

# ---------------------------------------------------------------------------
# Prestige layer 5 — Recursion
# ---------------------------------------------------------------------------
#
# Every layer so far changed the verb: upgrades, then choices, then floors, then
# exponents.  What is left is the game itself.  Recursion sells DIFFICULTY --
# you descend into a deliberately worse copy of the universe, because the worse
# it is, the more it pays.
#
# The design doc said Recursion "auto-replays the entire game at compressed
# speed."  That is a dead idea and it is worth saying why: by here the player
# owns auto-Dispersal, auto-Convergence, auto-Overwrite, auto-Defence and
# Standing Orders for three shops.  The game ALREADY replays itself.  A literal
# replay layer would rename automation they have and make them a spectator.  The
# payout rule survives -- depth reached x speed of clear -- and the mechanism is
# thrown away: the compressed replay is the player's own automation, through an
# early game that the Defection made worth revisiting.
#
# This is also the Challenge system the design doc promised at layer 2 and that
# was never written, arriving at the layer it belongs to.

P5_UNLOCK_SUB = N(250)           # lifetime Substrate needed to SEE the tab
P5_BASE = 2.0
P5_EXP = 1.35
# Requirement exponential in depth, gain mildly polynomial -- the shape that
# stopped layers 3 and 4 running away.
P5_TARGET_BASE = N(1e6)          # lifetime Alloy in a Recursion, at depth 0
P5_TARGET_STEP = 4.0             # ...times 1e4 per depth
P5_PAR_BASE = 300.0              # par clear time in seconds, at depth 0
P5_PAR_STEP = 90.0               # ...per depth
P5_SPEED_CAP = 10.0              # a one-second clear must not mint infinity

# Handicaps hit COSTS, never the exponent.  This is the main balance decision in
# the layer.  Production here is hyper-exponential; a ^0.9 handicap stacked to
# depth 40 is ^0.015, which is not difficulty, it is deletion.  Cost growth is
# the one axis that scales smoothly and that the player owns real tools against.
RECURSE_GROWTH_STEP = 0.004      # added to every machine's cost growth, per depth
RECURSE_GROWTH_FLOOR = 0.001     # ...however much Shallow Water is bought


@dataclass(frozen=True)
class RecMod:
    """A named handicap that switches on at a depth.

    Declarative so the header can print exactly what is being done to you. A
    handicap the player cannot see is indistinguishable from a bug.
    """
    id: str
    depth: int
    name: str
    desc: str


RECURSE_MODS: tuple[RecMod, ...] = (
    RecMod("draw", 3, "Hungry Machines",
           "Every machine draws three times the power."),
    RecMod("threat", 5, "Early Defection",
           "The swarm turns on you five times harder."),
    RecMod("norelic", 8, "Dead Frame",
           "Artifacts give nothing. The Relic Frame is inert."),
    RecMod("noanom", 12, "Silent Sky",
           "No anomalies. Nothing lucky happens down here."),
    RecMod("norep", 15, "Sterile",
           "The Replication ladder is locked. Machines no longer build machines."),
    RecMod("upkeep", 22, "Starved",
           "Alloy upkeep is ten times what it was."),
    RecMod("tenfold", 30, "Diminished",
           "Every 10 owned gives x1.05 instead of x1.10."),
)


MOD_BY_ID = {mod.id: mod for mod in RECURSE_MODS}


def active_mods(depth: int) -> tuple[RecMod, ...]:
    return tuple(mod for mod in RECURSE_MODS if depth >= mod.depth)


@dataclass(frozen=True)
class RecUpg:
    id: str
    name: str
    desc: str
    base_cost: float
    cost_growth: float
    max_level: int          # 0 == endless
    effect: Eff


RECURSION_STACK: tuple[RecUpg, ...] = (
    RecUpg("rc_start", "Compiled Start",
           "Begin every Recursion owning 25 more of each of E1-E5 and R1-R3, "
           "per level.", 3, 1.24, 0, Eff(START_GEN, "COMPILED", 25)),
    # The node that stops the Substrate wipe reading as pure loss: depth pays
    # layer 4 back in layer 4's own currency.
    RecUpg("rc_exponent", "Retained Exponent",
           "Keep +0.001 of your Substrate exponent through a Recursion, per "
           "level. The only thing that survives the wipe.", 6, 1.30, 0,
           Eff(KEEP_EXPONENT, "", 0.001)),
    RecUpg("rc_army", "Standing Army",
           "Keep 10% of your fleet through a Recursion, per level.",
           6, 1.30, 8, Eff(KEEP_FLEET, "", 0.10)),
    RecUpg("rc_sub", "Thicker Substrate",
           "Substrate from every Collapse x3, per level.", 5, 1.28, 0,
           Eff(MULT_SUB, "", 3.0)),
    # The difficulty dial. A player at their ceiling buys past it rather than
    # stalling -- the anti-frustration rule the design has held since day one.
    RecUpg("rc_shallow", "Shallow Water",
           "Each depth costs you 0.0005 less in machine cost growth, per level. "
           "The water gets shallower; you go deeper.", 8, 1.35, 6,
           Eff(SOFTEN, "", 0.0005)),
    RecUpg("rc_relic", "Wider Frame", "+10 Relic slots per level.",
           20, 1.55, 10, Eff(ADD_SLOT, "relic", 10)),
    RecUpg("rc_e11", "Vacuum Decay Well",
           "Unlock E11, which pulls Ore, Alloy, Data and Isotopes out of "
           "nothing at once.", 30, 1.0, 1, Eff(SET_FLAG, "unlock_e11")),
    RecUpg("rc_r8", "Galactic Bloom",
           "Unlock R8, the top of the Replication ladder.", 30, 1.0, 1,
           Eff(SET_FLAG, "unlock_r8")),
    RecUpg("rc_autorec", "Standing Recursion Orders",
           "Recursion runs itself, descending one depth further each time it "
           "clears.", 80, 1.0, 1, Eff(SET_FLAG, "auto_recurse")),
)
REC_BY_ID = {u.id: u for u in RECURSION_STACK}

# ---------------------------------------------------------------------------
# RNG — anomalies
# ---------------------------------------------------------------------------

EVENT_MIN_GAP = 30.0
EVENT_MEAN_GAP = 100.0


@dataclass(frozen=True)
class Anomaly:
    id: str
    name: str
    desc: str
    weight: float
    duration: float = 0.0
    mults: tuple[tuple[str, float], ...] = ()   # (resource id or "*", multiplier)
    instant: str = ""                           # handled in engine
    magnitude: float = 0.0
    unlock: Cond = ALWAYS


ANOMALIES: tuple[Anomaly, ...] = (
    Anomaly("rich_vein", "Rich Vein",
            "A seam of clean metal. Ore output tripled for 5 minutes.",
            25, 300.0, (("ore", 3.0),)),
    Anomaly("solar_flare", "Solar Flare",
            "The star flares. Power doubled, but the dust halves Ore output.",
            14, 120.0, (("energy", 2.0), ("ore", 0.5))),
    Anomaly("solar_wind", "Favourable Solar Wind",
            "Clean, fast particles. Power output up 50% for 3 minutes.",
            16, 180.0, (("energy", 1.5),)),
    Anomaly("derelict", "Derelict Hulk",
            "Something old, and full of good metal.",
            14, 0.0, (), instant="alloy", magnitude=90.0),
    Anomaly("signal_echo", "Signal Echo",
            "A repeating transmission resolves into usable telemetry.",
            13, 0.0, (), instant="data", magnitude=120.0,
            unlock=Cond(gen="E6", count=1)),
    Anomaly("rogue_rep", "Rogue Replicator",
            "Someone else's machine, and it still answers to a build order.",
            12, 0.0, (), instant="gen_R1", magnitude=0.12,
            unlock=Cond(gen="R1", count=5)),
    Anomaly("cascade", "Fabrication Cascade",
            "The swarm finds a shortcut. All Replication doubled for 2 minutes.",
            10, 120.0, (("R", 2.0),), unlock=Cond(gen="R2", count=1)),
    Anomaly("void_static", "Void Static",
            "Interference fouls your sensors. Everything down 10% for a minute.",
            5, 60.0, (("*", 0.9),)),
)

# ---------------------------------------------------------------------------
# RNG — artifacts and rarity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rarity:
    id: str
    name: str
    weight: float
    power: float       # scales the rolled effect
    colour: str


RARITY: tuple[Rarity, ...] = (
    Rarity("common", "Common", 60.0, 1.0, "#9aa4b2"),
    Rarity("uncommon", "Uncommon", 25.0, 1.6, "#4ea36a"),
    Rarity("rare", "Rare", 10.0, 2.6, "#3f7fd0"),
    Rarity("epic", "Epic", 4.0, 4.5, "#9a5fd0"),
    Rarity("legendary", "Legendary", 0.9, 9.0, "#d09a3f"),
    Rarity("cosmic", "Cosmic", 0.1, 22.0, "#d04f7f"),
)
RARITY_BY_ID = {r.id: r for r in RARITY}
# The Crucible: fuse N relics of one rarity into one of the next.  Deleting junk
# would tidy the list but leave the real problem -- once you hold a good relic,
# every later Common is dead loot and the find stops mattering.  Fusing keeps
# every drop worth something and gives the top rarities a route through effort
# rather than luck alone.
FUSE_COUNT = 3

PITY_ROLLS = 40          # guaranteed Epic+ every N artifact rolls
PITY_MIN_RARITY = "epic"


# A second, independent axis on top of rarity.  Rarity says how strong the relic
# is; a mutation says how strange it is, and multiplies the bonus it carries.
# Rolling them separately means a lucky Common can still beat a dull Rare, which
# keeps low-rarity drops worth reading.


@dataclass(frozen=True)
class Mutation:
    id: str
    name: str          # prefixed to the relic name; blank for the plain roll
    desc: str
    weight: float
    power: float       # multiplies the relic's bonus, not its total value
    colour: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation("plain", "", "", 62.0, 1.0, ""),
    Mutation("shiny", "Shiny",
             "Its surface keeps reflecting light that is not there.",
             15.0, 1.6, "#6fd8e8"),
    Mutation("mutated", "Mutated",
             "Something rewrote it, badly, and it works better for it.",
             10.0, 2.2, "#68c850"),
    Mutation("alien", "Alien",
             "Nothing human machined this.",
             7.0, 3.0, "#b06fd0"),
    Mutation("ancient", "Ancient",
             "Older than the star you found it around.",
             4.0, 4.5, "#d8a83f"),
    Mutation("entangled", "Entangled",
             "Part of it is somewhere else, and that part is helping.",
             1.6, 7.0, "#e86fa0"),
    Mutation("singular", "Singular",
             "There is exactly one of these, and you are holding it.",
             0.4, 12.0, "#ff6060"),
)
MUTATION_BY_ID = {m.id: m for m in MUTATIONS}
PLAIN_MUTATION = "plain"


@dataclass(frozen=True)
class ArtifactKind:
    id: str
    name: str
    desc: str
    kind: str          # Eff kind
    target: str
    per_power: float   # effect value = 1 + per_power * rarity.power


ARTIFACT_KINDS: tuple[ArtifactKind, ...] = (
    ArtifactKind("core_ore", "Ferrous Core", "+{p}% Ore production.", MULT_RES, "ore", 0.15),
    ArtifactKind("core_pow", "Charged Lattice", "+{p}% Power production.", MULT_RES, "energy", 0.15),
    ArtifactKind("core_alloy", "Crucible Shard", "+{p}% Alloy production.", MULT_RES, "alloy", 0.15),
    ArtifactKind("core_data", "Etched Wafer", "+{p}% Data production.", MULT_RES, "data", 0.20),
    ArtifactKind("core_rep", "Seed Fragment", "+{p}% Replication speed.", MULT_LADDER, REPLICATE, 0.12),
    ArtifactKind("core_all", "Anomalous Mass", "+{p}% to everything.", MULT_GLOBAL, "", 0.06),
)

ARTIFACT_PREFIX = ("Drifting", "Fused", "Silent", "Ancient", "Cracked", "Humming",
                   "Vitrified", "Folded", "Sealed", "Nameless")

# How much an artifact of each kind is worth to your actual bottom line.  Scores
# are log-weighted so they add the way multipliers compose.  Power is scored
# dynamically: a Power relic is nearly worthless at full throttle and valuable
# while you are throttled, so the weight is decided at ranking time.
ARTIFACT_WEIGHT = {
    (MULT_GLOBAL, ""): 1.00,
    (MULT_RES, "alloy"): 1.00,     # Alloy is the prestige metric
    (MULT_RES, "ore"): 0.90,       # ...and Alloy rides Ore income
    (MULT_LADDER, REPLICATE): 0.85,
    (MULT_LADDER, EXTRACT): 0.80,
    (MULT_RES, "data"): 0.30,
}
ARTIFACT_WEIGHT_DEFAULT = 0.40
POWER_WEIGHT_THROTTLED = 0.90
POWER_WEIGHT_HEALTHY = 0.10

# ---------------------------------------------------------------------------
# Exploration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    desc: str
    duration: float
    cost_iso: float
    drop_chance: float
    rarity_bias: float
    unlock: Cond = ALWAYS


TARGETS: tuple[Target, ...] = (
    Target("near", "Near Debris Field", "A short hop. Reliable, unremarkable.",
           60.0, 0.0, 0.55, 1.0),
    Target("belt", "Outer Belt", "Further out, colder, richer.",
           240.0, 5.0, 0.75, 1.4, Cond(flag="exploration")),
    Target("derelict", "Charted Derelict", "A wreck someone else already found.",
           600.0, 40.0, 0.90, 2.2, Cond(res="isotope", amount=N(100), lifetime=True)),
    Target("deep", "Deep Dark", "Months of nothing, then something impossible.",
           1200.0, 250.0, 1.00, 3.5, Cond(res="isotope", amount=N(2_000), lifetime=True)),
)
PROBE_SLOTS_BASE = 2
RELIC_SLOTS_BASE = 3

# ---------------------------------------------------------------------------
# Milestones  (permanent, bonus-bearing) and achievements (flavour + tiny bonus)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Milestone:
    id: str
    name: str
    desc: str
    cond: Cond
    effect: Eff


def _gen_count_milestones() -> list[Milestone]:
    out: list[Milestone] = []
    for g in GENERATORS:
        for n, mult in ((25, 1.10), (100, 1.15), (500, 1.25), (2500, 1.40)):
            out.append(Milestone(
                f"m_{g.id}_{n}", f"{g.name} x{n}",
                f"Own {n} {g.name}s. That machine produces {int((mult - 1) * 100)}% more.",
                Cond(gen=g.id, count=n), Eff(MULT_GEN, g.id, mult)))
    return out


def _lifetime_milestones() -> list[Milestone]:
    out: list[Milestone] = []
    spec = (("ore", (1e6, 1e9, 1e12, 1e15, 1e18)),
            ("alloy", (1e3, 1e6, 1e9, 1e12, 1e15)),
            ("data", (1e3, 1e6, 1e9, 1e12)))
    for res, steps in spec:
        for amount in steps:
            out.append(Milestone(
                f"m_life_{res}_{amount:.0e}",
                f"{RES_BY_ID[res].name} milestone",
                f"Produce {amount:.0e} {RES_BY_ID[res].name} in one run. +10% to everything.",
                Cond(res=res, amount=N(amount), lifetime=True),
                Eff(MULT_GLOBAL, "", 1.10)))
    return out


MILESTONES: tuple[Milestone, ...] = tuple(
    _gen_count_milestones() + _lifetime_milestones() + [
        Milestone("m_first_fab", "First Autonomy",
                  "Build a Fabricator Arm. Everything produces 25% more.",
                  Cond(gen="R1", count=1), Eff(MULT_GLOBAL, "", 1.25)),
        Milestone("m_first_artifact", "First Find",
                  "Recover an artifact. +25% artifact find chance, permanently.",
                  Cond(flag="found_artifact"), Eff(MULT_DROP, "", 1.25)),
        Milestone("m_first_disperse", "Scattered",
                  "Disperse once. Everything produces 50% more.",
                  Cond(prestige=1), Eff(MULT_GLOBAL, "", 1.5)),
        Milestone("m_ten_disperse", "Sown Wide",
                  "Disperse ten times. All machine costs scale 1% more slowly.",
                  Cond(prestige=10), Eff(ADD_GROWTH, "*", -0.01)),
        Milestone("m_fifty_disperse", "Endemic",
                  "Disperse fifty times. Everything produces 300% more.",
                  Cond(prestige=50), Eff(MULT_GLOBAL, "", 4.0)),
        Milestone("m_first_converge", "One Mind",
                  "Converge once. Everything produces 900% more.",
                  Cond(converge=1), Eff(MULT_GLOBAL, "", 10.0)),
        Milestone("m_five_converge", "Distributed",
                  "Converge five times. All machine costs scale 2% more slowly.",
                  Cond(converge=5), Eff(ADD_GROWTH, "*", -0.02)),
        Milestone("m_first_overwrite", "Rewritten",
                  "Overwrite once. Everything produces 2900% more.",
                  Cond(overwrite=1), Eff(MULT_GLOBAL, "", 30.0)),
        Milestone("m_first_collapse", "New Physics",
                  "Collapse once. Everything produces 9900% more.",
                  Cond(collapse=1), Eff(MULT_GLOBAL, "", 100.0)),
        Milestone("m_first_kill", "First Blood",
                  "Turn back an incursion. The whole fleet hits 50% harder.",
                  Cond(flag="combat_1"), Eff(MULT_LADDER, DEFEND, 1.5)),
        Milestone("m_ten_kills", "Standing Guard",
                  "Turn back ten incursions. Everything produces 100% more.",
                  Cond(flag="combat_10"), Eff(MULT_GLOBAL, "", 2.0)),
        Milestone("m_hundred_kills", "Attrition",
                  "Turn back a hundred incursions. The fleet hits x5 harder.",
                  Cond(flag="combat_100"), Eff(MULT_LADDER, DEFEND, 5.0)),
        Milestone("m_thousand_kills", "The Long War",
                  "Turn back a thousand incursions. Everything produces 900% "
                  "more.", Cond(flag="combat_1000"), Eff(MULT_GLOBAL, "", 10.0)),
        Milestone("m_flawless", "Not One Hull",
                  "Clear an incursion without losing a single machine. All "
                  "machine costs scale 2% more slowly.",
                  Cond(flag="combat_flawless"), Eff(ADD_GROWTH, "*", -0.02)),
        Milestone("m_five_overwrite", "Palimpsest",
                  "Overwrite five times. All machine costs scale 3% more slowly.",
                  Cond(overwrite=5), Eff(ADD_GROWTH, "*", -0.03)),
        Milestone("m_twenty_converge", "Singular",
                  "Converge twenty times. Everything produces 4900% more.",
                  Cond(converge=20), Eff(MULT_GLOBAL, "", 50.0)),
    ])


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    desc: str
    cond: Cond
    hidden: bool = False


ACH_GLOBAL_BONUS = 1.01   # each achievement: +1% to everything

ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement("a_first_ore", "Scratching the Surface", "Mine your first 100 Ore.",
                Cond(res="ore", amount=N(100), lifetime=True)),
    Achievement("a_lights_on", "Lights On", "Own 10 Solar Films.", Cond(gen="E2", count=10)),
    Achievement("a_hands_off", "Hands Off", "Own your first Fabricator Arm.",
                Cond(gen="R1", count=1)),
    Achievement("a_brownout", "Brownout", "Let your power throttle drop below 50%.",
                Cond(flag="ach_brownout")),
    Achievement("a_recovered", "Load Shed", "Recover to full power after a bad brownout.",
                Cond(flag="ach_recovered")),
    Achievement("a_refiner", "Smelter", "Produce your first 1,000 Alloy.",
                Cond(res="alloy", amount=N(1000), lifetime=True)),
    Achievement("a_thinker", "Telemetry", "Produce your first 1,000 Data.",
                Cond(res="data", amount=N(1000), lifetime=True)),
    Achievement("a_swarm", "It Builds Itself", "Own 25 Replicators.", Cond(gen="R2", count=25)),
    Achievement("a_spider", "Eight Legs", "Own a Forge Spider.", Cond(gen="R3", count=1)),
    Achievement("a_hoarder", "Hoarder", "Hold 1 billion Ore at once.",
                Cond(res="ore", amount=N(1e9))),
    Achievement("a_rare", "Curiosity", "Recover a Rare artifact.", Cond(flag="ach_rare")),
    Achievement("a_epic", "Museum Piece", "Recover an Epic artifact.", Cond(flag="ach_epic")),
    Achievement("a_legendary", "Provenance Unknown", "Recover a Legendary artifact.",
                Cond(flag="ach_legendary")),
    Achievement("a_cosmic", "Should Not Exist", "Recover a Cosmic artifact.",
                Cond(flag="ach_cosmic")),
    Achievement("a_first_disperse", "Let Go", "Disperse for the first time.", Cond(prestige=1)),
    Achievement("a_ten_disperse", "Again", "Disperse ten times.", Cond(prestige=10)),
    Achievement("a_fast", "Efficient", "Reach 1M Alloy in a run in under 10 minutes.",
                Cond(flag="ach_fast")),
    Achievement("a_purist", "Bare Hands",
                "Disperse having never owned more than one Fabricator Arm.",
                Cond(flag="ach_purist"), hidden=True),
    Achievement("a_patient", "Long Watch", "Play for six hours in total.",
                Cond(flag="ach_patient")),
    Achievement("a_deep", "Into the Dark", "Complete a Deep Dark expedition.",
                Cond(flag="ach_deep")),
    Achievement("a_converge", "Re-Assembled", "Converge for the first time.",
                Cond(converge=1)),
    Achievement("a_nanite", "Grey Goo", "Accumulate 1e12 Nanite Mass.",
                Cond(res="nanite", amount=N(1e12))),
    Achievement("a_doctrine", "Committed", "Choose all five Doctrines at once.",
                Cond(flag="ach_doctrines")),
    Achievement("a_fuse", "Crucible", "Fuse your first relic.", Cond(flag="ach_fused")),
    Achievement("a_mutation", "Anomalous", "Recover a mutated relic of any kind.",
                Cond(flag="ach_mutation")),
    Achievement("a_singular", "One Of One", "Recover a Singular relic.",
                Cond(flag="ach_singular")),
    Achievement("a_overwrite", "Start Again, Higher", "Overwrite for the first time.",
                Cond(overwrite=1)),
    Achievement("a_exotic", "Degenerate", "Hold 1e18 Exotic Matter.",
                Cond(res="exotic", amount=N(1e18))),
    Achievement("a_hive", "Ark", "Own a Hive Ark.", Cond(gen="R5", count=1)),
    Achievement("a_collapse", "Author", "Collapse the substrate for the first time.",
                Cond(collapse=1)),
    Achievement("a_exponent", "Above The Line",
                "Reach a production exponent of 1.10.", Cond(flag="ach_exponent")),
    Achievement("a_fuse_cosmic", "Made, Not Found",
                "Reach a Cosmic relic by fusing rather than finding one.",
                Cond(flag="ach_fused_cosmic")),
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tab:
    id: str
    name: str
    unlock: Cond = ALWAYS


TABS: tuple[Tab, ...] = (
    Tab("production", "Production"),
    Tab("upgrades", "Upgrades", Cond(gen="E1", count=10)),
    Tab("research", "Research", Cond(res="data", amount=N(1), lifetime=True)),
    Tab("exploration", "Exploration", Cond(flag="exploration")),
    Tab("defence", "Defence", Cond(flag="see_combat")),
    Tab("prestige", "Dispersal", Cond(res="alloy", amount=P1_UNLOCK_ALLOY, lifetime=True)),
    Tab("convergence", "Convergence", Cond(flag="see_convergence")),
    Tab("overwrite", "Overwrite", Cond(flag="see_overwrite")),
    Tab("substrate", "Substrate", Cond(flag="see_substrate")),
    Tab("recursion", "Recursion", Cond(flag="see_recursion")),
    Tab("automation", "Automation", Cond(flag="autobuy")),
    Tab("stats", "Stats"),
)

# ---------------------------------------------------------------------------
# Starting state
# ---------------------------------------------------------------------------

START_ORE = N(0)
MANUAL_ORE_PER_CLICK = 1.0
RESTART_ORE = 250.0
MANUAL_CLICK_SCALES_WITH_E1 = 0.5    # + this fraction of E1 output per click
AUTOSAVE_SECONDS = 30.0
TICK_MS = 100
UI_REFRESH_EVERY = 3
MAX_DT = 0.25
