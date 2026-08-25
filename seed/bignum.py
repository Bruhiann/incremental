"""Big-number arithmetic and formatting for SEED.

Numbers are stored as a normalized (mantissa, exponent) pair so the game keeps
counting long after float64 dies at ~1.8e308.  Every quantity in the game funnels
through :class:`Num`, so the late-game Substrate exponent layer needs no retrofit
of formulas, save fields or labels.

Representation
--------------
``m`` is a float with ``1.0 <= abs(m) < 10.0`` (or exactly ``0.0``), ``e`` is an
int.  The value is ``m * 10**e``.  Zero is ``(0.0, 0)``.
"""

from __future__ import annotations

import math

_LOG10 = math.log10

# Suffix i covers exponents 3i .. 3i+2.  Past the last one we switch to
# scientific notation, per the design doc (suffixes to ~1e33, then 1.42e37).
_SUFFIXES = ("", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc")
_SCI_FROM_EXP = 3 * len(_SUFFIXES)  # 36

# Beyond this the exponent itself gets formatted:  1.42e1.23e6
_NESTED_FROM_EXP = 1_000_000

# Adding a number this many orders of magnitude smaller is a no-op in float64.
_ADD_CUTOFF = 17


def _normalize(m: float, e: int) -> tuple[float, int]:
    """Return (mantissa, exponent) with 1 <= |mantissa| < 10, or (0.0, 0)."""
    if m == 0.0 or m != m:  # zero or NaN
        return 0.0, 0
    if m == math.inf:
        return 1.0, 308 * 4  # shouldn't happen; degrade instead of crashing
    if m == -math.inf:
        return -1.0, 308 * 4
    a = abs(m)
    if 1.0 <= a < 10.0:
        return m, e
    shift = math.floor(_LOG10(a))
    if -300 <= shift <= 300:
        m /= 10.0**shift
    else:  # split the scaling so 10**shift itself cannot overflow
        half = shift // 2
        m = m / 10.0**half / 10.0 ** (shift - half)
    e += shift
    # log10/float rounding can leave us a hair outside the window
    a = abs(m)
    if a >= 10.0:
        m /= 10.0
        e += 1
    elif a < 1.0:
        m *= 10.0
        e -= 1
    return m, e


def _from_int(v: int) -> tuple[float, int]:
    """Handle Python ints that overflow float()."""
    if -(2**53) < v < 2**53:
        return _normalize(float(v), 0)
    neg = v < 0
    s = str(-v if neg else v)
    e = len(s) - 1
    m = float(s[0] + "." + s[1:18])
    return _normalize(-m if neg else m, e)


def _parse(s: str) -> tuple[float, int]:
    s = s.strip()
    if not s:
        return 0.0, 0
    if "e" in s or "E" in s:
        mant, _, exp = s.replace("E", "e").partition("e")
        return _normalize(float(mant or "1"), int(float(exp)))
    try:
        return _normalize(float(s), 0)
    except (ValueError, OverflowError):
        return _from_int(int(s))


class Num:
    """Immutable (mantissa, exponent) number."""

    __slots__ = ("m", "e")

    def __init__(self, m=0.0, e: int = 0):
        if isinstance(m, Num):
            self.m, self.e = m.m, m.e
            return
        if isinstance(m, str):
            mm, ee = _parse(m)
            self.m, self.e = _normalize(mm, ee + e)
            return
        if isinstance(m, int) and not (-(2**53) < m < 2**53):
            mm, ee = _from_int(m)
            self.m, self.e = _normalize(mm, ee + e)
            return
        self.m, self.e = _normalize(float(m), int(e))

    # -- constructors -----------------------------------------------------
    @staticmethod
    def of(v) -> "Num":
        return v if isinstance(v, Num) else Num(v)

    @staticmethod
    def from_exp(e: float) -> "Num":
        """10 ** e, for any real e."""
        i = math.floor(e)
        return Num(10.0 ** (e - i), int(i))

    # -- basic protocol ---------------------------------------------------
    def __repr__(self) -> str:
        return f"Num({self.m!r}, {self.e!r})"

    def __str__(self) -> str:
        if self.m == 0.0:
            return "0"
        return f"{self.m:.15g}e{self.e}"

    def __hash__(self) -> int:
        return hash((self.m, self.e))

    def __bool__(self) -> bool:
        return self.m != 0.0

    def to_float(self) -> float:
        if self.e > 308:
            return math.inf if self.m > 0 else -math.inf
        if self.e < -308:
            return 0.0
        return self.m * 10.0**self.e

    __float__ = to_float

    def to_int(self) -> int:
        """Exact-ish Python int.  Used for generator counts."""
        if self.m == 0.0:
            return 0
        if self.e < 15:
            return int(self.m * 10.0**self.e)
        head = int(self.m * 1e15)
        return head * 10 ** (self.e - 15)

    __int__ = to_int

    def log10(self) -> float:
        if self.m <= 0.0:
            return -math.inf
        return self.e + _LOG10(self.m)

    def sqrt(self) -> "Num":
        return self.pow(0.5)

    # -- arithmetic -------------------------------------------------------
    def __neg__(self) -> "Num":
        return Num(-self.m, self.e)

    def __abs__(self) -> "Num":
        return Num(abs(self.m), self.e)

    def __add__(self, other) -> "Num":
        o = Num.of(other)
        if self.m == 0.0:
            return o
        if o.m == 0.0:
            return self
        if self.e >= o.e:
            big, small = self, o
        else:
            big, small = o, self
        diff = big.e - small.e
        if diff > _ADD_CUTOFF:
            return big
        return Num(big.m + small.m * 10.0**-diff, big.e)

    __radd__ = __add__

    def __sub__(self, other) -> "Num":
        return self.__add__(-Num.of(other))

    def __rsub__(self, other) -> "Num":
        return Num.of(other).__add__(-self)

    def __mul__(self, other) -> "Num":
        o = Num.of(other)
        if self.m == 0.0 or o.m == 0.0:
            return ZERO
        return Num(self.m * o.m, self.e + o.e)

    __rmul__ = __mul__

    def __truediv__(self, other) -> "Num":
        o = Num.of(other)
        if o.m == 0.0:
            raise ZeroDivisionError("Num division by zero")
        if self.m == 0.0:
            return ZERO
        return Num(self.m / o.m, self.e - o.e)

    def __rtruediv__(self, other) -> "Num":
        return Num.of(other).__truediv__(self)

    def pow(self, p: float) -> "Num":
        """self ** p, for positive self and real p."""
        if self.m == 0.0:
            return ZERO if p != 0 else ONE
        if self.m < 0:
            raise ValueError("Num.pow on a negative base")
        if p == 0:
            return ONE
        if p == 1:
            return self
        return Num.from_exp(self.log10() * float(p))

    def __pow__(self, p) -> "Num":
        return self.pow(float(p))

    # -- comparison -------------------------------------------------------
    def _cmp(self, other) -> int:
        o = Num.of(other)
        a, b = self.m, o.m
        if a == 0.0 or b == 0.0 or (a > 0) != (b > 0):
            return (a > b) - (a < b)
        if self.e != o.e:
            hi = self.e > o.e
            if a > 0:
                return 1 if hi else -1
            return -1 if hi else 1
        return (a > b) - (a < b)

    def __eq__(self, other) -> bool:
        if other is None:
            return False
        return self._cmp(other) == 0

    def __lt__(self, other) -> bool:
        return self._cmp(other) < 0

    def __le__(self, other) -> bool:
        return self._cmp(other) <= 0

    def __gt__(self, other) -> bool:
        return self._cmp(other) > 0

    def __ge__(self, other) -> bool:
        return self._cmp(other) >= 0

    # -- helpers ----------------------------------------------------------
    def clamp_min(self, floor=0) -> "Num":
        f = Num.of(floor)
        return f if self < f else self

    def min(self, other) -> "Num":
        o = Num.of(other)
        return o if o < self else self

    def max(self, other) -> "Num":
        o = Num.of(other)
        return o if o > self else self

    # -- persistence ------------------------------------------------------
    def to_json(self) -> str:
        return str(self)

    @staticmethod
    def from_json(s) -> "Num":
        if isinstance(s, Num):
            return s
        if s is None:
            return ZERO
        if isinstance(s, (int, float)):
            return Num(s)
        return Num(str(s))


ZERO = Num(0.0, 0)
ONE = Num(1.0, 0)


def N(v) -> Num:
    """Terse constructor used throughout gamedata."""
    return Num.of(v)


def _sig3(x: float) -> str:
    """Three significant figures, trailing zeros kept: 1.24 / 15.6 / 842."""
    a = abs(x)
    if a < 10:
        return f"{x:.2f}"
    if a < 100:
        return f"{x:.1f}"
    return f"{x:.0f}"


def fmt(value, places: int = 2) -> str:
    """Human-readable string: 1.24K, 15.6M, 8.42B, 1.42e37, 1.42e1.23e6."""
    n = Num.of(value)
    if n.m == 0.0:
        return "0"
    sign = "-" if n.m < 0 else ""
    m, e = abs(n.m), n.e

    if e < 0:
        v = m * 10.0**e if e > -300 else 0.0
        if v < 0.001:
            return sign + f"{v:.2e}"
        s = f"{v:.{places + 2}f}".rstrip("0").rstrip(".")
        return sign + (s or "0")

    if e < 3:
        return sign + _sig3(m * 10.0**e)

    if e < _SCI_FROM_EXP:
        idx = e // 3
        mant = m * 10.0 ** (e - 3 * idx)
        return sign + _sig3(mant) + _SUFFIXES[idx]

    if e < _NESTED_FROM_EXP:
        return sign + f"{m:.{places}f}e{e}"

    return sign + f"{m:.{places}f}e" + fmt(Num(e), places)


def fmt_rate(value, unit: str = "") -> str:
    s = fmt(value)
    return f"{s}{unit}/s" if unit else f"{s}/s"


def fmt_time(seconds: float) -> str:
    """Compact duration: 45s, 12m 30s, 3h 05m, 2d 04h."""
    if seconds is None or seconds != seconds or seconds == math.inf:
        return "never"
    s = int(max(0, seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    if s < 86400:
        return f"{s // 3600}h {(s % 3600) // 60:02d}m"
    return f"{s // 86400}d {(s % 86400) // 3600:02d}h"
