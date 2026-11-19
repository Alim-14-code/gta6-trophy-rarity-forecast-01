"""Local validation for the Trophy Dilution Ensemble (validation scratch only).

It is not part of the entry: the grader runs main.py alone. It checks the entry
three ways, all with the competition's own scoring rule (mean pinball loss on the
logit scale, rates clamped to [0.01, 99.99]):

  1. Practice cases p00/p01 under the three answer hypotheses the kit's published
     aggregates support. The kit does not ship the practice answers; the yaml gives
     the answering read: 04:30Z, 3,868 players tracked, 4,276 trophies earned
     (pre-refresh: 638 players, 943 earned). So the new players brought
     3,333 new earnings, of which trophy 2 (the opening mission, at 100%) takes
     3,230; the rest spread over the other trophies in proportion to their
     current earners. Hypothesis A (pure dilution) gives the rest nothing;
     C (realistic) gives them 103; D (calibrated) gives them 60, chosen so the
     persistence baseline scores the yaml's 1.51.
  2. Synthetic finals under a power-law player-growth process: players tracked
     N(t) = A * t^alpha, the Exophase page refreshing every few hours and frozen
     between refreshes, each trophy with an eventual rate and a time constant,
     earners built by convolution over join times. The case is cut at the real
     final checkpoint (59.5h) with the real target (168h).
  3. Stress finals under a different process: logistic (saturating) player
     growth, a weekend earning surge, wider refresh gaps, and a mid-window
     regime break where the join rate halves.

Every scenario runs three programs on the same generated case and scores them
against the true target rates: this entry (main.py), the persistence baseline
(house baseline, yaml formula), and the house curve baseline (log-time logit
line over the last 24h, spread the random walk plus the fit residual).
"""

import json
import math
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = (
    Path.home()
    / "workspace/makefun-bounties/gta6-trophy-rarity-forecast-01/kit20"
    / "gta6-trophy-rarity-forecast-01-kit"
)
MAIN = HERE / "main.py"
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
RELEASE = datetime(2026, 11, 19, 0, 0, 0, tzinfo=timezone.utc)
CHECK = datetime(2026, 11, 21, 11, 30, 0, tzinfo=timezone.utc)
TARGET = datetime(2026, 11, 26, 0, 0, 0, tzinfo=timezone.utc)
TROPHIES = json.loads((KIT / "input" / "p00.in").read_text())["trophies"]


# ---------------------------------------------------------------- scoring

def clamp(x):
    return min(99.99, max(0.01, x))


def logit(pct):
    p = clamp(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(lg):
    if lg >= 0:
        return 100.0 / (1.0 + math.exp(-lg))
    e = math.exp(lg)
    return 100.0 * e / (1.0 + e)


def pinball(y, q, tau):
    d = logit(y) - logit(q)
    return 2 * max(tau * d, (tau - 1) * d)


def score(forecast, answer):
    """forecast {id: [q05..q95]}, answer {id: rate} -> (loss, typical miss, coverage)."""
    total = 0.0
    n = 0
    miss = 0.0
    covered = 0
    for tid, y in answer.items():
        qs = forecast[tid]
        for tau, q in zip(LEVELS, qs):
            total += pinball(y, q, tau)
            n += 1
        miss += abs(y - qs[2])
        covered += 1 if qs[0] <= y <= qs[4] else 0
    return total / n, miss / len(answer), covered / len(answer)


def load_out(path):
    d = json.loads(Path(path).read_text())
    return {r["id"]: r["q"] for r in d["trophies"]}


def run_entry(entry_py, case, workdir):
    """Run a program on one case the way the grader does; return its forecast."""
    in_dir = Path(workdir) / "in"
    out_dir = Path(workdir) / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (in_dir / f"{case['id']}.in").write_text(json.dumps(case))
    env = dict(__import__("os").environ)
    env["MAKEFUN_INPUT_DIR"] = str(in_dir)
    env["MAKEFUN_OUTPUT_DIR"] = str(out_dir)
    subprocess.run(
        [sys.executable, str(entry_py)], env=env, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return load_out(out_dir / f"{case['id']}.out")


# ------------------------------------------------------- the two baselines

def persistence_forecast(case):
    """House baseline (yaml): last rate, spread 0.5 * sqrt(horizon in days)."""
    horizon_days = case["horizon_minutes"] / 1440.0
    sigma = 0.5 * math.sqrt(horizon_days)
    rows = {}
    for t in case["trophies"]:
        r = case["history"][-1]["rates"][t["id"] - 1]
        mu = logit(r)
        rows[t["id"]] = [inv_logit(mu + z * sigma) for z in Z]
    return rows


def curve_forecast(case):
    """House curve baseline (yaml): log-time logit line over the last 24h of
    reads, read at the target; spread the random walk plus the fit residual."""
    horizon_days = case["horizon_minutes"] / 1440.0
    walk = 0.5 * math.sqrt(horizon_days)
    target_h = (datetime.fromisoformat(case["target"].replace("Z", "+00:00")) - RELEASE).total_seconds() / 3600.0
    checkpoint = datetime.fromisoformat(case["at"].replace("Z", "+00:00"))
    recent = [
        r for r in case["history"]
        if (checkpoint - datetime.fromisoformat(r["at"].replace("Z", "+00:00"))).total_seconds() <= 24 * 3600
    ]
    if len(recent) < 3:
        recent = case["history"]
    rows = {}
    for t in case["trophies"]:
        i = t["id"] - 1
        xs, ys = [], []
        for r in recent:
            rate = r["rates"][i]
            if rate is None:
                continue
            h = (datetime.fromisoformat(r["at"].replace("Z", "+00:00")) - RELEASE).total_seconds() / 3600.0
            xs.append(math.log1p(max(h, 0.0)))
            ys.append(logit(rate))
        if len(xs) < 3:
            mu = logit(case["history"][-1]["rates"][i])
            sd = 0.3
        else:
            n = len(xs)
            mx, my = sum(xs) / n, sum(ys) / n
            sxx = sum((x - mx) ** 2 for x in xs)
            b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx > 0 else 0.0
            a = my - b * mx
            mu = a + b * math.log1p(target_h)
            sd = math.sqrt(sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / max(n - 2, 1))
        sigma = math.sqrt(walk * walk + sd * sd)
        rows[t["id"]] = [inv_logit(mu + z * sigma) for z in Z]
    return rows


# ------------------------------------------------------- practice answers

def practice_answer(case, extra_earnings):
    """Answer for a practice case: `extra_earnings` non-trophy-2 earnings spread
    over the other trophies in proportion to their current earners. Trophy 2
    stays at 100% (every new player earns the opening mission)."""
    last = case["history"][-1]
    n0 = last["players_tracked"]
    n1 = 3868  # the 04:30Z answering read, per the yaml's aggregates
    earn0 = {t["id"]: r * n0 / 100.0 for t, r in zip(case["trophies"], last["rates"])}
    non2 = sum(v for k, v in earn0.items() if k != 2)
    ans = {}
    for t in case["trophies"]:
        tid = t["id"]
        if tid == 2:
            ans[tid] = 100.0
        else:
            ans[tid] = (earn0[tid] + extra_earnings * earn0[tid] / non2) / n1 * 100.0
    return ans


# ------------------------------------------------------- synthetic finals

def difficulty_profile(rng):
    """(eventual rate, time constant in hours) per trophy, from tier and id."""
    out = []
    for t in TROPHIES:
        tid = t["id"]
        name, desc = t["name"], t["description"]
        if tid == 2:  # opening mission: everyone, fast
            R, tau = 0.99, 2.0
        elif tid == 1:  # platinum: everything, slow
            R, tau = 0.002, 200.0
        elif tid == 14:  # 100% completion
            R, tau = 0.02, 150.0
        elif tid == 15:  # many unique stunts
            R, tau = 0.05, 120.0
        elif tid == 7:  # gold story beat
            R, tau = 0.30, 50.0
        elif 3 <= tid <= 13:  # main story chapters, in order
            frac = (tid - 3) / 10.0
            R, tau = 0.75 - 0.5 * frac, 8.0 + 52.0 * frac
        elif t["tier"] == "silver":
            R, tau = 0.15, 80.0
        elif "Meditate" in desc or "18" in desc:
            R, tau = 0.08, 100.0
        else:  # bronze side activities
            R, tau = 0.25, 40.0
        R *= math.exp(rng.gauss(0, 0.3))
        tau *= math.exp(rng.gauss(0, 0.3))
        out.append((min(max(R, 0.0005), 0.995), max(tau, 1.0)))
    return out


def earners_over_time(join, R, tau, weights=None):
    """Earners of one trophy on an hourly grid, from the join rate per hour.

    A player who joined at hour j has earned it by hour h with probability
    R * (1 - exp(-(eff(h) - eff(j)) / tau)), where eff is the effective clock:
    normally one effective hour per hour, but `weights[h]` effective hours
    during hour h (a weekend earning surge makes weekend hours count more).
    The sum over join times is computed by the exponential-smoothing
    recurrence F(h) = exp(-w(h)/tau) * F(h-1) + join[h], with
    earners(h) = R * (players(h) - F(h)).
    """
    f = 0.0
    total = 0.0
    out = []
    for h, j in enumerate(join):
        w = 1.0 if weights is None else weights[h]
        total += j
        f = math.exp(-w / tau) * f + j
        out.append(R * (total - f))
    return out


def make_case(rng, process="powerlaw", alpha=1.14, n_target=250000):
    """Build a final-shaped case (cut 59.5h, target 168h) and its true answer."""
    hours = list(range(0, 169))
    if process == "powerlaw":
        A = n_target / (168.0 ** alpha)
        n_true = [A * (max(h, 0.25) ** alpha) for h in hours]
        weights = None
    else:  # logistic growth, weekend surge, join rate halves after 96h
        n_inf, t0, s = 400000.0, 72.0, 30.0
        n_true = [n_inf / (1.0 + math.exp(-(h - t0) / s)) for h in hours]
        # Weekend hours count 1.6x on the effective earning clock.
        weights = [
            1.6 if (RELEASE + timedelta(hours=h)).weekday() in (5, 6) else 1.0
            for h in hours
        ]
    join = [0.0] + [n_true[h] - n_true[h - 1] for h in range(1, 169)]
    if process != "powerlaw":
        # Regime break: the launch wave is over, the join rate halves after 96h.
        join = [j if h <= 96 else j * 0.5 for h, j in enumerate(join)]
        n_true = [sum(join[: h + 1]) for h in hours]
    prof = difficulty_profile(rng)
    earn = [earners_over_time(join, R, tau, weights) for (R, tau) in prof]
    # Page refreshes: random gaps; the page holds values at its last refresh.
    refresh_times = [0.0]
    gap = (2.0, 6.0) if process == "powerlaw" else (4.0, 8.0)
    while refresh_times[-1] < 168.0:
        refresh_times.append(refresh_times[-1] + rng.uniform(*gap))

    def page_at(t):
        rt = max(r for r in refresh_times if r <= t)
        h0 = int(math.floor(rt))
        h1 = min(h0 + 1, 168)
        f = rt - h0
        n = n_true[h0] * (1 - f) + n_true[h1] * f
        rates = []
        for i in range(55):
            e = earn[i][h0] * (1 - f) + earn[i][h1] * f
            rates.append(round(e / n * 100.0, 2) if n > 0 else 0.0)
        return n, rates

    # Reads: every 30 min from 23:50 on 18 Nov, then every 10 min to the cut.
    read_hours = []
    t = -0.17
    while t < 12.0:
        read_hours.append(t)
        t += 0.5
    while t <= 59.5:
        read_hours.append(t)
        t += 1.0 / 6.0
    history = []
    for rt in read_hours:
        if rt >= 59.5:
            break
        moment = RELEASE + timedelta(hours=rt)
        n, rates = page_at(max(rt, 0.0))
        history.append({
            "slot": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "at": moment.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "players_tracked": int(round(n)),
            "trophies_earned": int(round(sum(r * n / 100.0 for r in rates))),
            "rates": rates,
        })
    case = {
        "schema": "makefun/gta6-trophies-case/v1",
        "id": "f00",
        "at": CHECK.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_minutes": 6510,
        "target": TARGET.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "levels": LEVELS,
        "game": {
            "name": "Grand Theft Auto VI",
            "platform": "PS5",
            "release_date": "2026-11-19",
            "source": "https://www.exophase.com/game/grand-theft-auto-vi-psn/trophies/",
        },
        "trophies": TROPHIES,
        "history": history,
        "notes": "synthetic final case for local validation",
    }
    # True answer: the rates at the target hour, from the true process.
    n_t = n_true[168]
    answer = {t["id"]: earn[i][168] / n_t * 100.0 for i, t in enumerate(TROPHIES)}
    return case, answer


def main():
    tmp = Path(tempfile.mkdtemp(prefix="fc-validate-"))
    print("practice cases (answer hypotheses A=0, C=103, D=60 extra earnings)")
    print(f"{'case':6} {'hyp':4} {'mine':>7} {'persist':>7} {'curve':>7}")
    practice_wins = 0
    practice_n = 0
    for cid in ("p00", "p01"):
        case = json.loads((KIT / "input" / f"{cid}.in").read_text())
        mine = run_entry(MAIN, case, tmp / f"run-{cid}")
        pers = persistence_forecast(case)
        curv = curve_forecast(case)
        for hyp, x in (("A", 0), ("C", 103), ("D", 60)):
            ans = practice_answer(case, x)
            lm = score(mine, ans)[0]
            lp = score(pers, ans)[0]
            lc = score(curv, ans)[0]
            print(f"{cid:6} {hyp:4} {lm:7.3f} {lp:7.3f} {lc:7.3f}")
            practice_n += 1
            if lm < lp and lm < lc:
                practice_wins += 1
    print(f"practice: mine wins {practice_wins}/{practice_n} hypothesis scores")

    print("\nsynthetic finals (power-law growth)")
    print(f"{'seed':5} {'alpha':>5} {'mine':>7} {'persist':>7} {'curve':>7}")
    wins = 0
    n = 0
    for seed, alpha in ((1, 1.14), (2, 1.14), (3, 0.9), (4, 0.9), (5, 1.4), (6, 1.4)):
        rng = random.Random(seed)
        case, answer = make_case(rng, "powerlaw", alpha=alpha)
        mine = run_entry(MAIN, case, tmp / f"sim-{seed}")
        lm = score(mine, answer)[0]
        lp = score(persistence_forecast(case), answer)[0]
        lc = score(curve_forecast(case), answer)[0]
        print(f"{seed:<5} {alpha:>5} {lm:7.3f} {lp:7.3f} {lc:7.3f}")
        n += 1
        if lm < lp and lm < lc:
            wins += 1
    print(f"power-law: mine wins {wins}/{n} scenarios")

    print("\nstress finals (logistic growth, weekend surge, regime break)")
    wins = 0
    n = 0
    for seed in (11, 12, 13, 14):
        rng = random.Random(seed)
        case, answer = make_case(rng, "logistic")
        mine = run_entry(MAIN, case, tmp / f"stress-{seed}")
        lm = score(mine, answer)[0]
        lp = score(persistence_forecast(case), answer)[0]
        lc = score(curve_forecast(case), answer)[0]
        print(f"{seed:<5} {'':>5} {lm:7.3f} {lp:7.3f} {lc:7.3f}")
        n += 1
        if lm < lp and lm < lc:
            wins += 1
    print(f"stress: mine wins {wins}/{n} scenarios")


if __name__ == "__main__":
    main()
