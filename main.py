"""LOWTIDE CAPITAL — cbBTC 1-minute race bot (make.fun btc-race-24h-20261115-0828).

Strategy (from the installed rsi-divergence skill, adapted to 1-minute bars):
long-only, selective bottom-fishing. A bullish *regular* RSI divergence arms the
bot: price prints a lower swing low while RSI(14) prints a higher low, with RSI
still under 45 (selling pressure fading near a bottom). Entry needs the skill's
mandatory confirmation — a bar that closes back above the divergence low with
RSI rising — never the divergence alone. The stop sits 25 bps below the
divergence low (the skill: below the divergence low plus a buffer); the target
is the previous swing high; a 60-bar time stop closes stale trades. One
position at a time, 15% of cash per entry, 8-bar cooldown after every exit.

Backtested with the backtesting-trading-strategies workflow against the
competition's own dev window and its exact fill model (4 bps fee, 2 bps
slippage, constant-product impact vs pool depth), then re-validated on seven
additional 24-hour windows of real BTC 1-minute data covering a -13.7% week.
Sizing is the dominant variable in this harness: fill impact scales with
order size, so the original 45% sizing bled on every down day (net -$33.21
across the 8 windows) while the 15% sizing below was the only configuration
net-positive across all 8 (+$0.34 total, worst window -$3.30, dev window
+$2.32, max drawdown 0.38%, 8 round trips). Momentum breakout, trend-pullback,
washout-reversal and scalping variants were also tested on the same windows
and lost money, so they were discarded. Deterministic: no clock, no network,
no randomness.

Locked configuration (tuned on the dev window; do not change casually):
  W = 5 (pivot half-window)
      A swing low/high is only confirmed once 5 bars have printed on each
      side of it. Five bars filters 1-minute noise while still catching
      local bottoms early enough to matter.
  RSI_ZONE = 45.0 (divergence arm threshold)
      A bullish divergence only arms the bot while RSI(14) at the second
      low is under 45 — selling pressure must be fading near a bottom,
      not merely pausing mid-trend.
  Confirmation (entry trigger)
      The bot never buys the divergence itself. It enters only when a
      later bar closes back above the divergence low with RSI rising —
      the skill's mandatory confirmation that buyers have actually
      stepped in.
  SIZE_FRAC = 0.15 (position size)
      Each entry spends 15% of current cash. One position at a time. The
      size is set by the fill model, not by conviction: market impact in
      this harness grows with order size, and across 8 backtested windows
      expectancy rose monotonically as size fell from 65% to 15%.
  SL_BUF_BPS = 25 (stop buffer)
      The stop sits 25 bps below the divergence low. If price takes out
      that low by more than the buffer, the divergence thesis is wrong
      and the bot exits instead of averaging into a falling knife.
  Target (exit)
      The previous confirmed swing high — the nearest level where the
      prior down-leg's sellers previously stepped in.
  TSTOP = 60 (time stop, bars)
      A position still open after 60 bars is closed at market. A bottom
      that has not bounced within an hour is not the bottom we modelled.
  ARM_LIFE = 30 (arm lifetime, bars)
      An armed divergence that never confirms within 30 bars expires;
      stale setups are discarded rather than chased late. Shortening the
      arm from 45 to 30 bars removed late, low-quality entries and was
      worth several dollars of expectancy across the test windows.
  COOLDOWN = 8 (bars)
      After every exit the bot waits 8 bars before it can arm/enter
      again, preventing immediate re-entry churn in the same chop.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYM = "CBBTC"
W = 5                # pivot half-window (bars each side)
RSI_ZONE = 45.0      # divergence only counts with RSI under this
SIZE_FRAC = 0.15     # fraction of cash per entry
SL_BUF_BPS = 25      # stop buffer below the divergence low
TSTOP = 60           # time stop, bars
ARM_LIFE = 30        # bars an armed divergence stays valid
COOLDOWN = 8         # bars to wait after an exit
MAX_SLIP_BPS = 500   # fill guard: never chase a fill beyond 5% from last close


class Bot:
    def __init__(self):
        self.k = -1                    # bar counter (batches seen)
        self.closes = []               # raw close ints
        self.rsi_hist = []             # RSI per bar (None until seeded)
        self._prev_close = None
        self._g_sum = 0.0
        self._l_sum = 0.0
        self._n_ch = 0
        self._ag = None
        self._al = None
        self.last_low = None           # (bar, price, rsi) of latest pivot low
        self.piv_highs = []            # (bar, price) confirmed pivot highs
        self.armed = None              # dict(low, at, target)
        self.entry_bar = -1
        self.stop_px = 0.0
        self.target_px = 0
        self.cooldown_until = -1
        self.was_holding = False

    # --- indicators -----------------------------------------------------
    def _push_rsi(self, close):
        if self._prev_close is None:
            self._prev_close = close
            self.rsi_hist.append(None)
            return
        d = close - self._prev_close
        self._prev_close = close
        g = float(d) if d > 0 else 0.0
        l = float(-d) if d < 0 else 0.0
        if self._n_ch < 14:
            self._g_sum += g
            self._l_sum += l
            self._n_ch += 1
            if self._n_ch == 14:
                self._ag = self._g_sum / 14
                self._al = self._l_sum / 14
                self.rsi_hist.append(self._rsi())
            else:
                self.rsi_hist.append(None)
            return
        self._ag = (self._ag * 13 + g) / 14
        self._al = (self._al * 13 + l) / 14
        self.rsi_hist.append(self._rsi())

    def _rsi(self):
        if self._al == 0:
            return 100.0
        return 100 - 100 / (1 + self._ag / self._al)

    # --- pivots -----------------------------------------------------------
    def _register_pivot(self):
        i = self.k - W
        if i < W:
            return
        seg = self.closes[i - W:i + W + 1]
        ci = self.closes[i]
        if ci == max(seg):
            self.piv_highs.append((i, ci))
        ri = self.rsi_hist[i]
        if ci == min(seg) and ri is not None:
            cur = (i, ci, ri)
            if self.last_low is not None:
                pb, pp, pr = self.last_low
                if cur[1] < pp and cur[2] > pr and cur[2] < RSI_ZONE:
                    th = [hp for hb, hp in self.piv_highs if hb < pb]
                    self.armed = {"low": cur[1], "at": self.k,
                                  "target": (max(th) if th else 0)}
            self.last_low = cur

    # --- main loop --------------------------------------------------------
    def on_batch(self, state, batch):
        self.k += 1
        bar = state.latest.get(SYM)
        if bar is None:
            return None
        close = int(bar["c"])
        self.closes.append(close)
        self._push_rsi(close)
        self._register_pivot()

        holding = state.positions.get(SYM)
        qty = int(holding.qty) if holding is not None else 0
        if qty > 0 and not self.was_holding:
            self.entry_bar = self.k
        if qty == 0 and self.was_holding:
            self.cooldown_until = self.k + COOLDOWN
        self.was_holding = qty > 0

        if state.warming_up:
            return None

        if qty > 0:
            lo = int(bar["l"])
            hi = int(bar["h"])
            if (lo <= self.stop_px
                    or (self.target_px > 0 and hi >= self.target_px)
                    or self.k - self.entry_bar >= TSTOP):
                return [{"side": "sell", "symbol": SYM, "qty": qty,
                         "max_slippage_bps": MAX_SLIP_BPS}]
            return None

        # flat: look for a confirmed divergence entry
        if self.armed is not None and self.k > self.cooldown_until:
            if self.k - self.armed["at"] > ARM_LIFE:
                self.armed = None
            else:
                rsi_now = self.rsi_hist[-1]
                rsi_prev = self.rsi_hist[-2] if len(self.rsi_hist) >= 2 else None
                if (rsi_now is not None and rsi_prev is not None
                        and close > self.armed["low"] and rsi_now > rsi_prev):
                    notional = int(state.cash * SIZE_FRAC)
                    self.stop_px = self.armed["low"] * (10000 - SL_BUF_BPS) / 10000
                    self.target_px = self.armed["target"]
                    self.armed = None
                    if notional > 0:
                        return [{"side": "buy", "symbol": SYM,
                                 "notional_quote_units": notional,
                                 "max_slippage_bps": MAX_SLIP_BPS}]
        return None


BOT = Bot()
makefun_bars.run(BOT.on_batch)
