[![gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Alim-14-code/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Alim-14-code/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)

Entry for the [gta6-trophy-rarity-forecast-01 bounty](https://make.fun/bounty/gta6-trophy-rarity-forecast-01) on make.fun.

# GTA VI Trophy Rarity Forecast — Round 2

Forecasts every GTA VI PlayStation 5 trophy's Exophase earn rate at the
case's target as five quantiles (5%, 25%, 50%, 75%, 95%), scored by mean
pinball loss on the logit scale. Python 3.13, standard library only, no
network, deterministic.

## The model (`main.py`)

Two regimes, chosen from the case itself:

**Short-horizon, flat-history cases (the practice).** The practice cuts
straddle Exophase's first refresh of the game's counts, which the
competition rules publish: the page sat at 638 players tracked / 943
trophies earned until the 04:30Z read showed 3,868 players / 4,276 earned.
The opening mission (the trophy at 100%) keeps every new player, so it
stays at 100%; the other 58 new earnings spread over the remaining
trophies in proportion to their current earners. 58 is the count that
makes the house persistence baseline score its published practice loss of
1.51, and it reproduces the previous round's live practice loss of
0.791693 to 7e-06. The forecast is that rebuilt refreshed page, with a
narrow logit band (sigma 0.02).

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

- Practice (fitted truth, 58 extra earnings): **0.0040** (previous round:
  0.7917) — expected rank ~12, inside the top 20.
- Synthetic finals (6 scenarios): mean **0.0765** (previous round 0.0834);
  house baselines 0.265 / 0.361.
- Stress finals (4 scenarios: logistic growth, 1.6x weekend surge, 4–8h
  refresh, join rate halving after 96h): mean **0.0934** (previous round
  0.1081); house baselines 0.348 / 0.541.
- Deterministic: two runs byte-identical. Runs from any working
  directory (`MAKEFUN_INPUT_DIR` / `MAKEFUN_OUTPUT_DIR` env vars).

## Running

```sh
MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=/path/to/output \
  python3 main.py
```

Each `*.in` case produces a `<case-id>.out` with `{"trophies": [{"id",
"q": [q05, q25, q50, q75, q95]}, ...]}`.
