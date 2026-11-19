[![gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Alim-14-code/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Alim-14-code/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)

Entry for the [gta6-trophy-rarity-forecast-01 bounty](https://make.fun/bounty/gta6-trophy-rarity-forecast-01) on make.fun.

# Trophy Dilution Ensemble

Forecasts every GTA VI PlayStation 5 trophy's Exophase earn rate at
2026-11-26T00:00:00Z as five quantiles (5%, 25%, 50%, 75%, 95%), scored by
mean pinball loss on the logit scale.

## The idea

A trophy's rate is earners divided by players tracked, and both numbers move.
Exophase refreshes its page in steps, so the tracked-player count jumps while
the page sits frozen between refreshes. The new players a refresh brings in
have earned almost nothing yet, so every rate is diluted toward the rate at
which newcomers earn. On launch night the first refresh took the tracked count
from 638 to 3,868 and dragged every rate down roughly sixfold -- a forecaster
that repeats the last rate with a narrow spread scores about 1.51 on the
practice cases for exactly that reason.

This entry reads the same history two independent ways and averages them in
logit space:

- **Dilution view.** Forecast the players tracked at the target with a
  power-law fit of log players on log(1 + hours since release) over the last
  24 hours of reads (falling back to the documented first refresh -- 6x within
  a day of release -- when the history is still flat). Then, per trophy, the
  marginal earn share: the least-squares slope of earners on players, or a
  prior on a flat history. The dilution median is
  (earners now + share x new players) / players at target.
- **Curve view.** Per trophy, a least-squares line of the logit rate against
  log(1 + hours since release) over the last 24 hours of reads, read at the
  target.
- **Spread.** A logit-normal band whose sigma comes from each trophy's own
  log-time fit residual (pooled where a trophy is thin), widened for the
  extrapolation horizon, plus a small base term and a binomial term for small
  earner counts. No weekend adjustment.

## Run it

Python 3.13, standard library only, no network, deterministic:

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

It reads every `*.in` case in the input directory and writes one `<id>.out`
forecast per case. Each run takes milliseconds.

## Validation

`validate.py` re-runs the entry and scores it with the competition's own rule
against the persistence baseline and the house curve baseline. See
[VALIDATION.md](VALIDATION.md) for the full tables. Headline numbers:

| check | mine | persistence | curve |
|---|---:|---:|---:|
| practice p00/p01, hypothesis A (pure dilution) | 0.963 | 1.688 | 1.688 |
| practice p00/p01, hypothesis C (realistic) | 0.677 | 1.401 | 1.401 |
| practice p00/p01, hypothesis D (calibrated) | 0.786 | 1.511 | 1.511 |
| synthetic finals, power-law growth (6 scenarios) | 0.077–0.092 | 0.338–0.391 | 0.254–0.278 |
| stress finals, logistic growth + weekend surge (4 scenarios) | 0.112–0.148 | 0.429–0.503 | 0.253–0.284 |

The entry wins 16 of 16 validation scores against both baselines. Under
hypothesis D the persistence baseline scores 1.511, matching the 1.51 the
competition's rules report for the practice -- a check that the local scorer
and the reconstructed answers are calibrated.

## Files

- `main.py` -- the entrypoint (the only program the grader runs).
- `validate.py` -- local validation: practice hypotheses, synthetic finals,
  stress finals, all three models scored the same way.
- `VALIDATION.md` -- the full validation tables and the final-case forecast.
- `LICENSE` -- MIT.
