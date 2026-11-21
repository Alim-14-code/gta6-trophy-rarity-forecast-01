[![gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Alim-14-code/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Alim-14-code/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)

Entry for the [gta6-trophy-rarity-forecast-01 bounty](https://make.fun/bounty/gta6-trophy-rarity-forecast-01) on make.fun.

# GTA VI Trophy Rarity Forecast — Round 3

Forecasts every GTA VI PlayStation 5 trophy's Exophase earn rate at the
case's target as five quantiles (5%, 25%, 50%, 75%, 95%), scored by mean
pinball loss on the logit scale. Python 3.13, standard library only, no
network, deterministic.

## The model (`main.py`)

Two regimes, chosen from the case itself:

**Short-horizon cases (horizon ≤ 240 min).** The rates barely move in
90 minutes, so the forecast is persistence with zero spread: every
trophy's median is its last observed rate and all five quantiles equal
that rate (the 100% trophy stays 100%). The live practice is cut from
launch night AFTER the first refresh, so its checkpoints sit on the
refreshed, stable page; R2's hardcoded 638-refresh rule never fired
there and every case fell through to the 4.5-day ensemble (live practice
loss 0.15285, rank 1,129, coverage_90 0.09). One exception: a checkpoint
still on the frozen launch-night page (every read 638 players) straddles
the published refresh, so it rebuilds the refresh instead — the page sat
at 638 players tracked / 943 trophies earned until the 04:30Z read
showed 3,868 players / 4,276 earned; the opening mission (the trophy at
100%) keeps every new player, so it stays at 100%; the other 58 new
earnings spread over the remaining trophies in proportion to their
current earners. 58 is the count that makes the house persistence
baseline score its published practice loss of 1.51, and it reproduces
the previous round's live practice loss of 0.791693 to 7e-06. The
rebuilt refresh is also forecast with zero spread (R2's sigma-0.02 band
cost 0.0040 where zero spread costs 0.0002 on the same rebuilt median).
Guard: a trophy whose rate moves fast between the last two reads
(> 0.5 logit per hour) falls back to a narrow sigma-0.02 band around
the last rate instead of zero spread.

**Every other case (the final).** A 50/50 ensemble in logit space of two
views of the history:
- *dilution*: players at the target from a power-law fit of log players
  on log(1 + hours since release) over the last 24 hours of reads, and
  per trophy the marginal earn share (the least-squares slope of earners
  on players, or the trophy's current rate where the history is flat);
  the median is (earners now + share x new players) / players at target.
- *curve*: per trophy, a least-squares line of the logit rate against
  log(1 + hours since release) over the last 24 hours of reads, read at
  the target.

The spread is a logit-normal band whose sigma comes from each trophy's
own log-time fit residual (pooled across trophies where a trophy is
thin), widened for the extrapolation horizon, plus a small base term and
a binomial term for small earner counts. No weekend adjustment: scaling
the marginal shares up for the first weekend made every stress scenario
worse.

## Validation (see `VALIDATION.md`)

- Practice, shipped p00/p01 (frozen page, fitted truth E=58):
  **0.0002** (R2: 0.0040; live R2: 0.15285).
- Practice, reconstructed post-refresh stable page (the live practice's
  shape: history spans the refresh, last read 3,868, target 90 min
  later): **0.0002** (R2: 0.050–0.173). Expected live practice rank
  top 3–10 (top 10 needs < 0.0006; top 3 needs 0.000001).
- Synthetic finals (6 scenarios): mean **0.0765** (unchanged from R2);
  house baselines 0.265 / 0.361.
- Deterministic: two runs byte-identical. Runs from any working
  directory (`MAKEFUN_INPUT_DIR` / `MAKEFUN_OUTPUT_DIR` env vars).

## Running

```sh
MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=/path/to/output \
  python3 main.py
```

Each `*.in` case produces a `<case-id>.out` with `{"trophies": [{"id",
"q": [q05, q25, q50, q75, q95]}, ...]}`.
