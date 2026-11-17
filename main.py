"""BTC trend-catcher for make.fun btc-race-24h-20261117-0603.

Trades Coinbase Wrapped BTC (CBBTC) against USDC on 1-minute on-chain bars,
long only, starting from 1,000 USDC of paper money. Speaks
agent-fun/bars-replay/v1 through the vendored shim (vendor/makefun_bars.py).

Idea, from backtesting the published dev window (1,440 bars, BTC +0.49%):
one-minute prices are mostly noise -- a plain EMA crossover trades 30+ times
a day and bleeds ~$100 to the ~36 bps a full-size round trip costs (4 bps fee
+ 2 bps slippage + ~12 bps of pool impact each way at the dev window's depth).
So this bot trades rarely, only when a trend is already strong, and gets out
as soon as the trend turns:

  * Entry: the fast EMA(8) of closes crosses above the slow EMA(21) with the
    gap already at least 3 bps of the price -- a cross that arrives with
    momentum behind it, not a drift through the line. (On the dev window only
    one cross in 34 cleared that bar.) If the window opens mid-trend, the
    first bar where both EMAs are defined and the gap is already >= 3 bps
    enters at once instead of waiting for a fresh cross.
  * Exit: the whole position, when EMA(8) crosses back below EMA(21), or when
    the close falls 2.5% below the highest close since entry (trailing stop),
    or 2.0% below the entry close (hard stop, for a fast crash the EMAs lag).
  * No new entries in the last 60 bars: a trade opened there has no time to
    earn back its round-trip cost before the final flatten.
  * One full-size position at a time (the whole cash balance), at most one
    order per reply, max slippage 100 bps (1%) past the close decided on.

Backtest on the dev window (exact replay of the harness fill math, verified
trade-for-trade against `grade-local` on the EMA-cross baseline): net PnL
+$3.70, 2 trades, max drawdown -1.02%. Baselines on the same window:
buy-and-hold +$1.07, momentum +$2.45, rsi-bollinger -$24.25,
adx-momentum -$32.66, ema-cross -$106.21.

Deterministic: the only state is the two EMAs and the entry/peak closes, all
pure functions of the closes seen; no clock, no environment, no randomness.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

FAST_SPAN = 8
SLOW_SPAN = 21
# A cross only counts when the EMA gap at the crossing bar is at least this
# share of the price (basis points). Filters out drift-through crosses.
MIN_GAP_BPS = 3
# Trailing stop: sell when the close falls this far below the highest close
# seen since entry. Hard stop: sell this far below the entry close.
TRAIL_PCT = 0.025
STOP_PCT = 0.020
# No new entries from this batch index on (the window has 1,440 bars).
NO_ENTRY_AFTER = 1380
MAX_SLIPPAGE_BPS = 100


class Ema:
    """One exponential moving average over integer closes.

    Seeded as the mean of its first `span` closes, then each new close moves
    it 2 / (span + 1) of the way there. Float64, fixed operation order, so
    the same bars always give the same value.
    """

    def __init__(self, span):
        self.span = span
        self.alpha = 2.0 / (span + 1)
        self._warm = []
        self.value = None

    def push(self, close):
        if self.value is not None:
            self.value += self.alpha * (close - self.value)
            return self.value
        self._warm.append(close)
        if len(self._warm) == self.span:
            self.value = sum(self._warm) / self.span
        return self.value


class TrendCatcher:
    def __init__(self):
        self.fast = Ema(FAST_SPAN)
        self.slow = Ema(SLOW_SPAN)
        # Gap (fast - slow) after the previous bar, in price units; None until
        # both EMAs are defined on two consecutive bars.
        self.prev_gap = None
        self.entry_close = None
        self.peak_close = None
        # True while a buy sent on the previous bar has not yet filled: the
        # fill is reported a bar later, so an entry rejected (e.g. the open
        # gapped past the slippage cap) is retried while the trend is still
        # strong instead of waiting for a fresh cross.
        self.buy_pending = False

    def on_bar(self, state, close):
        """Decide the orders for one new CBBTC close. Returns a list of orders."""
        fast = self.fast.push(close)
        slow = self.slow.push(close)
        if fast is None or slow is None:
            return []
        gap = fast - slow
        held = state.positions.get(SYMBOL)
        if held is not None:
            self.buy_pending = False
        orders = []
        if held is not None:
            if self.peak_close is None or close > self.peak_close:
                self.peak_close = close
            exit_now = False
            if close <= self.peak_close * (1.0 - TRAIL_PCT):
                exit_now = True
            elif self.entry_close is not None and close <= self.entry_close * (1.0 - STOP_PCT):
                exit_now = True
            elif self.prev_gap is not None and gap < 0 and self.prev_gap >= 0:
                exit_now = True
            if exit_now:
                orders.append(
                    {"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}
                )
                self.entry_close = None
                self.peak_close = None
        else:
            if self.buy_pending and (gap <= 0 or gap < close * MIN_GAP_BPS / 10000.0):
                # The trend faded while the buy was unfilled: drop it.
                self.buy_pending = False
                self.entry_close = None
                self.peak_close = None
            if state.seq < NO_ENTRY_AFTER and not state.warming_up:
                enter = False
                if self.prev_gap is None:
                    # First bar with both EMAs defined: the window may have
                    # opened mid-trend, so enter if it is already strong.
                    enter = gap >= close * MIN_GAP_BPS / 10000.0
                elif gap > 0 and self.prev_gap <= 0:
                    enter = gap >= close * MIN_GAP_BPS / 10000.0
                elif self.buy_pending:
                    # Retry a buy the market refused on the previous bar.
                    enter = True
                if enter and state.cash >= 1_000_000:
                    orders.append(
                        {"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": state.cash,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}
                    )
                    self.entry_close = close
                    self.peak_close = close
                    self.buy_pending = True
        self.prev_gap = gap
        return orders


BOT = TrendCatcher()


def on_batch(state, batch):
    orders = []
    for bar in batch["bars"]:
        if bar["symbol"] != SYMBOL:
            continue
        orders.extend(BOT.on_bar(state, int(bar["c"])))
    return orders


makefun_bars.run(on_batch)
