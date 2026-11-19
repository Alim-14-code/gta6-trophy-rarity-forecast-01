"""Trophy Dilution Ensemble -- gta6-trophy-rarity-forecast-01 (Python 3.13, stdlib only).

Forecasts every GTA VI PS5 trophy's Exophase earn rate at a case's target as five
quantiles, scored by pinball loss on the logit scale.

Why a plain "last rate" forecast fails here: a trophy's rate is earners divided by
players tracked, and both numbers move. Exophase refreshes its page in steps, so
the tracked-player count jumps while the page sits frozen between refreshes. The
new players a refresh brings in have earned almost nothing yet, so every rate is
diluted toward the rate at which newcomers earn. On launch night the first refresh
took the tracked count from 638 to 3,868 and dragged every rate down roughly sixfold;
a forecaster that repeats the last rate with a narrow spread scores about 1.51 on
the practice cases for exactly that reason.

This entry reads the same history two independent ways and averages them in logit
space, so the bias of each one is partly cancelled by the other:

  Dilution view. First, how many players will be tracked at the target? A power
  law in hours since release, fitted on the log of the tracked count against the
  log of (1 + hours) over the last 24 hours of reads. When the history is still
  flat -- no refresh has been seen yet, as on launch night -- fall back to the
  documented first refresh: six times the current count within a day of release,
  one and a half times after that. Then, per trophy, the marginal earn share: the
  least-squares slope of earners on players tracked, stretched a little for the
  longer exposure of the target window; on a flat history, a prior instead -- the
  most-earned trophy goes to every new player, and the rest share (1 + horizon in
  days) new trophies per new player in proportion to their current rates. The
  dilution median is (earners now + share x new players) / players at target.

  Curve view. Per trophy, a least-squares line of the logit rate against
  log(1 + hours since release) over the last 24 hours of reads, read at the
  target -- the house curve baseline's form. Fewer than three reads, and the
  trophy falls back to its last rate.

  The median is the mean of the two views in logit space. The spread is a
  logit-normal band whose sigma comes from each trophy's own log-time fit
  residual (pooled across trophies where a trophy is thin), widened for the
  extrapolation horizon, plus a small base term and a binomial term for small
  earner counts, clamped to [0.25, 1.2]. No weekend adjustment: scaling the
  marginal shares up for the first weekend made every stress scenario worse.

Deterministic: pure float arithmetic, no randomness, input files in name order.
Runs in milliseconds; the 8-second cap is never approached.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z_SCORES = [-1.645, -0.674, 0.0, 0.674, 1.645]
# Release: 2026-11-19T00:00:00Z; every time is measured in hours from here.
RELEASE = datetime(2026, 11, 19, 0, 0, 0, tzinfo=timezone.utc)


def parse_ts(text):
    """ISO 8601 timestamp (with a Z suffix) to an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def hours_since_release(moment):
    """Hours from release to a timestamp (negative before release)."""
    return (parse_ts(moment) - RELEASE).total_seconds() / 3600.0


def clamp_pct(x):
    """A rate in percent, kept inside the logit-safe band [0.01, 99.99]."""
    return min(99.99, max(0.01, x))


def logit_of(pct):
    """logit of a rate given in percent."""
    p = clamp_pct(pct) / 100.0
    return math.log(p / (1.0 - p))


def pct_of(logit_value):
    """Inverse logit, back to a rate in percent (overflow-safe both ways)."""
    if logit_value >= 0:
        return 100.0 / (1.0 + math.exp(-logit_value))
    e = math.exp(logit_value)
    return 100.0 * e / (1.0 + e)


def round4(x):
    """Round to 4 decimals, halves up (the same rounding the house baseline uses)."""
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if value == int(value) else value


def fit_line(xs, ys):
    """Least-squares line through (xs, ys).

    Returns (intercept, slope, residual_sd): the sd of the residuals around the
    fitted line, or None when the points carry no usable spread.
    """
    n = len(xs)
    if n == 0:
        return 0.0, 0.0, None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0.0:
        return mean_y, 0.0, None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sxx
    intercept = mean_y - slope * mean_x
    if n <= 2:
        return intercept, slope, None
    resid_sq = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    return intercept, slope, math.sqrt(resid_sq / (n - 2))


def window_reads(history, checkpoint_h, span_h=24.0):
    """Reads from the last `span_h` hours before the checkpoint; every read when
    fewer than three fall in the window."""
    recent = [r for r in history if hours_since_release(r["at"]) >= checkpoint_h - span_h]
    return recent if len(recent) >= 3 else history


def players_at_target(times_h, counts, target_h, checkpoint_h):
    """Players tracked at the target hour.

    A power-law fit of log(players) on log(1 + hours) over the last day of reads.
    A flat history means no refresh has been seen yet, so fall back to the
    documented first refresh near release, and a gentler one later.
    """
    n0 = counts[-1]
    if len(counts) < 2 or max(counts) <= 1.05 * min(counts):
        if checkpoint_h <= 24.0:
            return n0 * 6.0
        return n0 * 1.5
    pts = [(t, c) for t, c in zip(times_h, counts) if t >= checkpoint_h - 24.0]
    if len(pts) < 3:
        pts = list(zip(times_h, counts))
    xs = [math.log1p(t) for t, _ in pts]
    ys = [math.log(max(c, 1.0)) for _, c in pts]
    a, b, _ = fit_line(xs, ys)
    n1 = math.exp(a + b * math.log1p(target_h))
    return min(max(n1, n0), n0 * 10.0)


def marginal_shares(last_rates, counts, earner_series, horizon_days):
    """Per trophy, the share of newly tracked players who will have earned it by
    the target.

    When the tracked count has moved, the share is the least-squares slope of
    earners on players, stretched mildly for the longer exposure of the target
    window. On a flat history there is no slope to read, so a prior: the
    most-earned trophy goes to every new player, and the rest share
    (1 + horizon_days) new trophies per new player in proportion to their
    current rates.
    """
    n_trophies = len(last_rates)
    varied = max(counts) > 1.05 * min(counts)
    if varied:
        stretch = min(1.5, math.sqrt(1.0 + horizon_days / 4.0))
        shares = []
        for series in earner_series:
            pts = [(c, e) for c, e in zip(counts, series) if e is not None]
            if len(pts) < 2:
                shares.append(0.0)
                continue
            _, slope, _ = fit_line([p[0] for p in pts], [p[1] for p in pts])
            shares.append(min(1.0, max(0.0, slope * stretch)))
        return shares
    total_new = 1.0 + horizon_days
    top = max(range(n_trophies), key=lambda i: last_rates[i])
    shares = [0.0] * n_trophies
    shares[top] = 1.0
    rest = max(total_new - 1.0, 0.0)
    denom = sum(r for j, r in enumerate(last_rates) if j != top)
    if denom > 0.0 and rest > 0.0:
        for j, rate in enumerate(last_rates):
            if j != top:
                shares[j] = min(1.0, rest * rate / denom)
    return shares


def curve_logit(case, history, target_h):
    """Per trophy, the log-time linear fit of the logit rate, read at the target.

    Returns (medians, sds): the median in logit units and the fit's residual sd,
    with the pooled sd across trophies standing in where a trophy is thin.
    """
    checkpoint_h = hours_since_release(case["at"])
    recent = window_reads(history, checkpoint_h)
    medians = []
    sds = []
    pooled_resid_sq = 0.0
    pooled_n = 0
    for i in range(len(case["trophies"])):
        xs, ys = [], []
        for read in recent:
            rate = read["rates"][i]
            if rate is None:
                continue
            xs.append(math.log1p(max(hours_since_release(read["at"]), 0.0)))
            ys.append(logit_of(rate))
        if len(xs) < 3:
            # Too thin to fit: fall back to the trophy's last observed rate
            # (the last read that actually lists it, not necessarily the last
            # read -- a case may lack a trophy in its final read).
            last_seen = next(
                (read["rates"][i] for read in reversed(history)
                 if read["rates"][i] is not None),
                0.0,
            )
            medians.append(logit_of(last_seen))
            sds.append(None)
            continue
        a, b, sd = fit_line(xs, ys)
        medians.append(a + b * math.log1p(target_h))
        sds.append(sd)
        if sd is not None:
            pooled_resid_sq += sd * sd * (len(xs) - 2)
            pooled_n += len(xs) - 2
    pool_sd = math.sqrt(pooled_resid_sq / pooled_n) if pooled_n > 0 else 0.3
    return medians, [s if s is not None else pool_sd for s in sds]


def forecast_case(case):
    """One case in, one forecast out: {"trophies": [{"id": n, "q": [...]}]}."""
    if case["levels"] != LEVELS:
        raise ValueError("unexpected levels")
    history = case["history"]
    if not history:
        raise ValueError("no history")
    trophies = case["trophies"]
    times_h = [hours_since_release(r["at"]) for r in history]
    counts = [float(r["players_tracked"]) for r in history]
    n0 = counts[-1]
    horizon_days = case["horizon_minutes"] / 1440.0
    target_h = hours_since_release(case["target"])
    checkpoint_h = hours_since_release(case["at"])

    # View 1 (dilution): players at target, then earners at target.
    n1 = players_at_target(times_h, counts, target_h, checkpoint_h)
    earner_series = []
    last_rates = []
    for i in range(len(trophies)):
        series = []
        for read in history:
            rate = read["rates"][i]
            series.append(
                rate * read["players_tracked"] / 100.0 if rate is not None else None
            )
        earner_series.append(series)
        last_earners = next((v for v in reversed(series) if v is not None), None)
        last_rates.append(last_earners / n0 * 100.0 if last_earners is not None else 0.0)
    shares = marginal_shares(last_rates, counts, earner_series, horizon_days)

    # View 2 (curve): log-time logit line per trophy, read at the target.
    mu_curve, sds = curve_logit(case, history, target_h)

    rows = []
    for i, trophy in enumerate(trophies):
        e0 = next((v for v in reversed(earner_series[i]) if v is not None), 0.0)
        e1 = e0 + shares[i] * max(n1 - n0, 0.0)
        y_dilution = e1 / n1 * 100.0 if n1 > 0 else e0 / n0 * 100.0
        # Ensemble median: the two views averaged in logit space.
        mu = 0.5 * logit_of(y_dilution) + 0.5 * mu_curve[i]
        # Spread: the trophy's own fit residual, widened for extrapolation,
        # plus a small base term and a binomial term for small earner counts.
        sigma = math.sqrt(
            sds[i] ** 2 * (1.0 + horizon_days / 2.0)
            + 0.15 ** 2
            + 0.25 / max(e1, 1.0)
        )
        sigma = min(max(sigma, 0.25), 1.2)
        quantiles = []
        floor = 0.0001
        for z in Z_SCORES:
            q = pct_of(mu + z * sigma)
            q = min(max(q, 0.0001), 99.9999)
            q = max(q, floor)
            quantiles.append(round4(q))
            floor = quantiles[-1]
        rows.append({"id": trophy["id"], "q": quantiles})
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
