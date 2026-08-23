# Strategy notes (fill in as decisions are made)

Keep this file as the plain-language source of truth for the methodology —
it's most of what turns directly into the report's "Methodology" section.

## Stock-selection rule
(TODO — e.g. "Rank the eligible universe by a composite of 12-1 month
momentum and 6-month realised volatility, equally weighted z-scores; take
the top 10 names after applying a minimum liquidity filter.")

## Weighting rule
(TODO — e.g. "Score-proportional weighting, renormalised, capped at 25% per
name.")

## Rebalancing rule
(TODO — e.g. "Monthly, on the first trading day of the month. Trades that
would change a position by less than 1% of portfolio value are skipped to
avoid unnecessary transaction costs.")

## Why this is expected to generalise out-of-sample
(TODO — write this BEFORE seeing the out-of-sample result, not after. e.g.
"Momentum and low-volatility are well-documented, non-overfit factors; the
rule has two free parameters (lookback windows) chosen from convention
rather than optimised on this data; no stock-specific overrides.")

## Known limitations / assumptions to disclose in the report
- Universe membership uses current (2026) index constituents applied
  retroactively to 2021-2025 — a disclosed simplification, not survivorship-
  free.
- yfinance data quality for illiquid smallcap names not independently
  verified against a paid data vendor.
- No fundamental/value factor included — price-only composite, by design,
  given the data-sourcing constraints on this timeline.
- (add more as they come up)
