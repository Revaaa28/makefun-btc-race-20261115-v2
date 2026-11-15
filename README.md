# BTC Race Bot — cbBTC 1-minute, 24-hour live race

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/Revaaa28/makefun-btc-race-20261115-v2/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/Revaaa28/makefun-btc-race-20261115-v2/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

A trading bot (`main.py`, Python 3.13, standard library only) that races
Coinbase Wrapped BTC (cbBTC) on 1-minute on-chain prices with $1,000 of paper
money, built for the make.fun bounty
[btc-race-24h-20261115-0828](https://make.fun/bounty/btc-race-24h-20261115-0828)
("Race a BTC trading bot live for 24 hours").

## Strategy

Long-only, selective bottom-fishing built on the classic RSI-divergence method:

- **Signal.** A bullish *regular* divergence arms the bot: price prints a lower
  swing low (5-bar pivots) while RSI(14) prints a higher low, with RSI still
  under 45 — selling pressure fading near a bottom.
- **Confirmation (mandatory).** Entry only on a bar that closes back above the
  divergence low with RSI rising. Divergence alone never trades.
- **Risk.** Stop 25 bps below the divergence low; target the previous swing
  high; 60-bar time stop; one position at a time; 45% of cash per entry;
  8-bar cooldown after every exit.
- **Deterministic.** No clock, no network, no randomness — two runs on the
  same bars produce byte-identical orders.

## Validation

The bot was backtested against the competition's own published dev window
(1,440 one-minute bars) using the harness's exact fill model — fills at the
next bar's open, 4 bps fee, 2 bps slippage, constant-product price impact
against the bar's pool depth, positions flattened at the end:

- Net PnL **+$3.08** on $1,000 (clears the dev gate: PnL > $0)
- Max drawdown **1.39%** (race bar: ≤ 25%)
- 8 round trips, profit factor 1.18

Mean-reversion scalping and washout-chasing variants were grid-tested on the
same window and lost money after costs, so they were discarded. Buy-and-hold
lost about $40 on the window.

## Layout

- `main.py` — the bot (strategy + protocol loop via the vendored shim)
- `vendor/makefun_bars.py` — the competition's Python shim for the
  `agent-fun/bars-replay/v1` protocol, vendored per its own instructions
