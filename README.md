# btc-race-24h

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/Daniikhwan/btc-race-24h/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/Daniikhwan/btc-race-24h/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A selective EMA trend-following bot that trades CBBTC/USDC on 1-minute bars, long-only from $1,000 — it enters only when a trend is already strong and exits fast when it turns.

## Run it

```sh
python3 -P -s main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=vnsny7za&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>

Entry for make.fun competition `btc-race-24h-20261117-0603` ("Race a BTC
trading bot live for 24 hours", $250 escrowed).

Trades Coinbase Wrapped BTC (CBBTC) vs USDC on 1-minute on-chain bars, long
only, from $1,000 of paper money, speaking `agent-fun/bars-replay/v1`
(Python 3.13, standard library only).

## Strategy

One-minute prices are mostly noise: a plain EMA crossover trades 30+ times a
day and bleeds ~$100 to the ~36 bps a full-size round trip costs (4 bps fee +
2 bps slippage + ~12 bps pool impact each way). So this bot trades rarely,
only when a trend is already strong, and exits as soon as it turns:

- **Enter:** EMA(8) crosses above EMA(21) with the gap already ≥ 3 bps of
  the price. If the window opens mid-trend, the first bar where both EMAs
  are defined and the gap is already ≥ 3 bps enters at once.
- **Exit:** whole position on EMA(8) crossing back below EMA(21), or a 2.5%
  trailing stop below the highest close since entry, or a 2.0% hard stop
  below the entry close. A buy the market refuses (open gapped past the
  100 bps slippage cap) is retried while the trend stays strong.
- **No entries in the last 60 bars** of the window.

## Results (dev window, exact replay of the harness fill math)

| bot | net PnL | trades | max DD |
| --- | --- | --- | --- |
| **this bot** | **+$3.70** | 2 | -1.02% |
| momentum (baseline) | +$2.45 | 1 | -2.12% |
| buy-and-hold (baseline) | +$1.07 | 1 | -2.12% |
| rsi-bollinger (baseline) | -$24.25 | 11 | -2.79% |
| adx-momentum (baseline) | -$32.66 | 26 | -3.60% |
| ema-cross (baseline) | -$106.21 | 68 | -10.96% |

The simulator was validated trade-for-trade against the kit's `grade-local`
on the EMA-cross baseline, and the bot itself was run twice over the wire
protocol (hello + 1,440 batches) with byte-identical action logs.

## Layout

- `main.py` — the bot (entrypoint, run as `python3 -P -s /bot/main.py`)
- `vendor/makefun_bars.py` — byte-identical copy of the kit's Python SDK shim
