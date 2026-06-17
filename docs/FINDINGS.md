# Findings & Where I Think We Should Go Next

Hey team, this is my write-up of what I found once I actually dug into our data
and the optimizer. I tried to explain everything from the ground up so we're all
on the same page (and so it's easy to drop into the report later). Numbers are
from our aligned window, **Jan 2008 → Jun 2026 (219 months, 9 assets)**, using
historical-average returns as the placeholder. Fair warning up front: this is all
**in-sample / full-period** for now, it's diagnostics, not a real backtest yet.
The dashboard shows this same page under **Findings**.

---

## First, what are we even building?

The whole thing is a pipeline that turns data into a suggested portfolio:

1. **Pick the assets** (our 9 ETFs across US equity, global equity, bonds, commodities).
2. **Estimate two things** for those assets: how much we expect each to return,
   and how they move together (the covariance).
3. **Feed both into an optimizer** that spits out weights, how much to hold of each.
4. **Check it** against a benchmark and against history.

Right now we've really only built step 3, and even that is running on a
placeholder for step 2. Everything below is me pressure-testing what we have and
laying out what I think we add next.

---

## What "the model" actually is right now

We have exactly one model: a **mean-variance optimizer** (the classic Markowitz
setup from the 1950s). Here's literally how it picks the percentages:

- **Expected return** for each asset = its historical average monthly return,
  annualized. This is a stand-in. It is *not* a forecast, it just assumes the
  future looks like the past, which we know isn't true.
- **Risk** = the sample covariance matrix (how each pair of assets co-moves).
- **The actual optimization**: find the weights that **maximize expected return**
  while holding **portfolio volatility at 10%**, making the **weights add to 100%**,
  and keeping **every asset between 3% and 30%** (we call that the "box").

So the optimizer is technically choosing the weights, but here's the catch I want
everyone to understand: **the 3%/30% box is doing most of the deciding, not the
math.** More on that below.

---

## The assets, plainly

| Asset | Ann. Return | Ann. Vol | Sharpe (return per unit of risk) |
|---|---|---|---|
| SPY (US large cap) | 12.0% | 15.8% | **0.76** |
| AGG (US bonds) | 3.1% | 4.6% | 0.67 |
| VXF (US mid/small) | 11.6% | 20.2% | 0.57 |
| EMB (EM bonds) | 5.6% | 11.4% | 0.49 |
| INTL_BOND | 3.0% | 6.5% | 0.46 |
| EWC (Canada) | 7.8% | 20.1% | 0.39 |
| EFA (intl developed) | 6.2% | 17.7% | 0.35 |
| VWO (EM equity) | 6.2% | 20.4% | 0.30 |
| DBC (commodities) | 3.0% | 19.0% | **0.16** |

Quick read: the US stuff (SPY, AGG, VXF) carried this whole period. Every non-US
equity sleeve has a Sharpe under 0.4, and **DBC is basically dead weight on its
own**, it took on stock-level risk and paid out like a T-bill. I'll defend
keeping DBC anyway, but for a diversification reason, not a return reason (next
section).

One honest caveat: these Sharpes use raw returns, not returns *above cash*. So
they're all a bit flattering. We should subtract a 1-month cash rate before we
quote these in the report, Greg mentioned adding a cash series and this is why
it matters.

---

## Finding #1: our "diversified" portfolio is mostly one bet

I pulled the correlations and the equity sleeves are almost the same asset:

- SPY ↔ VXF: **0.92**
- SPY ↔ EFA: 0.87, EWC ↔ EFA: 0.86, EFA ↔ VWO: 0.86

Five "different" equity exposures basically move as one factor. The only real
diversifiers are the bonds and commodities, AGG ↔ DBC is actually **−0.10**, and
DBC ↔ INTL_BOND is 0.20. This is exactly the "knife-edge" thing Greg warned us
about: when assets are this correlated, the covariance matrix gets unstable and
the optimizer overreacts to tiny differences. That's why it wants to dump
everything into SPY + AGG.

---

## Finding #2: the box is driving, not the optimizer

When I solve at 10% vol I get: **SPY 30%, AGG 30%, INTL_BOND 13%, VXF 12%, and
then EWC / EFA / VWO / EMB / DBC all stuck at 3%.** That means **7 of our 9
assets are sitting exactly on a constraint** (5 at the floor, 2 at the cap). The
optimizer isn't finding some clever interior sweet spot, the 3%/30% box is
deciding almost everything, and the means/covariance just decide the leftovers.

This isn't a bug, it's the well-known weakness of plain mean-variance: it's an
"error maximizer." It trusts the inputs too much and stampedes toward whatever
looks slightly best, so we slap on a box to stop it, and then the box is what's
really choosing.

---

## Finding #3 (the big one): expected returns barely move the portfolio

This is the one I want us to take seriously, because the entire point of the
macro project is to produce better expected-return estimates and feed them in.
So I tested whether the optimizer even listens to them. It does, but only in
ugly, all-or-nothing jumps:

- I cranked **VWO's** expected return from 6% up to 14%. It stayed glued at the
  3% floor the entire way, then **snapped** to ~13% once it crossed SPY's level.
- I dropped **SPY's** expected return from 12% to 6%. It fell off a cliff from
  30% straight down to 3%.

There's a live chart of this on the Optimizer page. The takeaway: a smooth,
nuanced macro forecast gets flattened into near-binary floor/cap decisions. If we
hand this optimizer a thoughtful return view, it'll mostly ignore the nuance.
**We have to fix the optimizer before our macro model can actually express
itself.** That's the core message for the report.

---

## What surprised me in the macro regressions

I ran every asset against every macro factor (one-month lag, both on the raw
levels and on month-to-month changes, with Newey-West standard errors so we don't
fool ourselves on noisy data). 252 regressions, 39 of them significant (about 15%).

A couple of things jumped out:

- **Inflation is the strongest signal by far.** Headline CPI shows up significant
  **12 times**, and always negative, higher inflation last month lines up with
  weaker returns this month across SPY, VXF, EMB, EFA, INTL_BOND. The yield-curve
  term spread (10y minus 3m) is a positive signal for the cyclical stuff (DBC, Canada).
- **Here's the awkward one:** PMI, the indicator our whole macro story is built
  around as a GDP proxy, only shows up significant **3 times**, behind CPI, the
  term spread, and the short rate. I'm not saying we drop PMI, but we should
  probably tell Greg that CPI looks like the stronger return signal in our data,
  and lean on it.
- No single factor explains much month to month (R² around 0.03–0.06). That's
  normal, it means the forecasting power has to come from *combining* factors,
  not any one of them, which points us straight at a proper multi-factor model.

---

## What I think we should do to the optimizer (I did some digging on this)

Plain mean-variance is known to be fragile, so I read up on how actual shops deal
with it. Here's my shortlist, roughly in order of bang-for-buck:

1. **Shrink the covariance (Ledoit-Wolf).** Instead of trusting the raw sample
   matrix, you pull it toward a simpler, more stable structure. It's the standard
   academic fix (Ledoit & Wolf, "Honey, I Shrunk the Sample Covariance Matrix").
   I already wired it in, it cut our matrix's condition number from 284 to 110.
   Cheap, no downside, should be on by default.

2. **Go Black-Litterman for expected returns.** This is the Goldman Sachs
   framework and it's basically built to solve Finding #3. Instead of feeding raw
   forecasts straight in, you start from the market's implied "equilibrium"
   returns and then *tilt* them by our macro views, weighted by how confident we
   are. The output is stable and it moves smoothly with our views instead of
   snapping. If we do one upgrade, I vote this one.

3. **Constrain equity as a group, not asset by asset.** Since our five equity
   sleeves are basically one bet, capping *total equity* (say 55%) makes way more
   sense than a 3–30% box on each. When I tried this with a Sharpe objective it
   pushed our Sharpe from 0.72 up to ~0.79. Easy win and easy to justify.

4. **Add a diversification / turnover penalty.** A small L2 penalty on the weights
   nudges the optimizer to spread out instead of concentrating (I have this in as
   a slider, it raised our "effective number of holdings" from a corner solution
   to ~4.6). Down the line a turnover penalty also keeps us from trading too much,
   which matters once we add transaction costs (Adam flagged this).

5. **A couple of things to keep in our back pocket:** *risk parity* (size
   positions by risk contribution rather than dollars, this is the Bridgewater
   All-Weather idea, and it sidesteps needing good return forecasts at all), and
   *resampled / Michaud optimization* (run the optimizer over many simulated draws
   and average the weights so we're not betting the farm on one noisy estimate).
   I don't think we need these for v1, but they're good to name-check in the report
   as alternatives we considered.

And the unglamorous but important one: **use returns above cash** before we compute
any of this, so our Sharpe ratios are honest.

---

## Data: what I cleaned, what's still rough

I went through the macro file and it needed work:

- It had **~23 duplicate rows for every month** (5,044 rows for what should be ~232
  months). I collapsed those to one clean monthly value each.
- **HY_SPREAD was 85% empty**, too sparse to trust, so I dropped it.
- **Dividend yield was 28% empty**, I filled it by interpolating between the
  points we have (64 months filled), never pulling future data backward.
- A few series were missing a single month; I interpolated those too.

My one rule on filling gaps: only ever carry info *forward* or interpolate
*between* known points, never backfill the past with the future. That keeps us
from accidentally cheating (look-ahead bias) when we backtest.

Still rough, and worth being upfront about with Greg and Adam:

- The macro file is **assembled by hand** right now. It works, but if we get the
  time, a script that pulls straight from FRED/OECD would make the whole thing
  reproducible and trivial to refresh. Not urgent, just the "right" way.
- Our macro data is **US-only**, but a third of our assets aren't (EFA, VWO, EWC).
  Regressing Canadian and EM stocks against US inflation is a stretch, building
  regional macro series is the real fix there.

### On the window, and the splice we already did
Our data starts in 2008 only because of **EMB** (EM bonds didn't exist as an ETF
until Dec 2007). Everything else goes back further. The good news: the splice the
team already built, chaining **PFORX into BNDX** for international bonds, pushed
that sleeve back to late 2007. If we want to reclaim all of 2007 (and capture the
start of the financial crisis), we'd do the same trick on EMB: find a pre-2008 EM
bond proxy and chain-link the returns over the overlap, the way Adam described.
That's the cleanest path to a longer history.

---

## So what would I actually hold right now?

Two reasonable starting portfolios to backtest against the 60/40 ACWI/IGOV
benchmark:

| Sleeve | Plain optimizer | My preferred (shrinkage + Sharpe + equity cap) |
|---|---|---|
| SPY | 30% | 30% |
| AGG | 30% | 30% |
| INTL_BOND | 13% | ~17% |
| VXF | 12% | ~4% |
| EMB | 3% | ~7% |
| EWC / EFA / VWO / DBC | 3% each | 3% each |
| **Profile** | 7.2% return @ 10% vol, Sharpe 0.72 | ~6.5% return @ 8.3% vol, **Sharpe 0.79** |

Both land around a global **50% stocks / 45% bonds / 5% commodities** mix, which
honestly is a sane place to be. The whole point of the macro work is to tilt
*around* this core, but per Finding #3, we need the optimizer upgrades first or
those tilts won't stick.

---

## My proposed next steps

- **Optimizer:** add Black-Litterman, make the equity-group cap and Ledoit-Wolf the
  defaults, and switch to returns-above-cash.
- **Returns model:** build the real multi-factor regression, turn it into an
  expected-return vector, and A/B it against the historical-average baseline.
- **Risk:** build the factor-based covariance (returns explained by macro factors)
  the way Adam pushed for.
- **Backtest:** proper train/test split, both a hold-it-static run and a rolling
  monthly re-estimate, measured against the benchmark.
- **Data:** the FRED/OECD script if we get time, the EMB splice to grab 2007, and
  regional macro so the non-US regressions actually make sense.

Tear this apart in our next meeting, especially Finding #3, since it changes how
much the macro model can even do for us.
