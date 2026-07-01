# Dashboard Chart Forecast Spec

## Goal

Dashboard chart forecasting is a generic time-series visualization capability. It must work for LTV, payment, ARPU, ROI, LT, revenue, cost, conversion, traffic, inventory, and other metrics without hardcoding any business metric name or datasource fixture.

## Product Rules

- Forecasting is enabled per chart through `chart.forecast`.
- The runtime path must be datasource-agnostic and metric-name-agnostic.
- Forecast input is the rendered chart time series: one time/numeric x-axis, one or more metric y-axis fields, and an optional series field.
- For multi-metric charts, each metric curve is forecast independently after the chart renderer normalizes metrics into series.
- Forecast values render as same-color dashed line segments connected from the last actual point. Actual values remain solid.
- When one chart contains multiple curves whose actual data ends on different x-axis positions, all forecast curves extend to the same final forecast x value: the latest actual x value across the whole chart plus the configured forecast periods.
- Percentage-like metrics are clamped to `0..100`; non-negative historical metrics are clamped at `0`.
- Business constraints such as ROI budget caps, LTV maturity windows, retention denominators, or payable user definitions belong in Data Skills, metadata, SQL, or future forecast-service configuration, not hidden frontend branches.

## Model Selection

Default mode is `auto`. Auto mode fits conservative candidate models on historical points, validates on a recent holdout window, and chooses the lowest validation error with a small complexity penalty. It favors damped trend and smoothing models so short/noisy dashboard series do not turn into visually misleading polynomial or growth curves. The more aggressive curve families remain available for explicit user selection.

Current chart-side candidates:

- Damped trend: weighted recent trend blended with whole-window slope, with outlier-limited changes and gradual mean reversion.
- Linear: stable growth/decline.
- Polynomial: inflection or acceleration/deceleration, only when enough points exist.
- Exponential: multiplicative growth/decay with positive values.
- Logarithmic: fast early growth then saturation-like slowing.
- Power: scale-law-like curves with positive values.
- Reciprocal: decreasing curves approaching a baseline.
- Logistic: bounded S-curve growth.
- Gompertz: slow start, rapid middle phase, late saturation.
- Holt-Winters-style smoothing: trend plus simple additive weekly/monthly seasonality when the x-axis granularity and point count support it.

Deferred server-side candidates:

- ARIMA/SARIMA for stationary or seasonally differenced series.
- ARCH/GARCH for volatility forecasting.
- VAR/VECM for multivariate coupled metrics.
- Kalman/state-space models for latent dynamic systems.
- Weibull/reliability models for survival/lifetime style forecasts.

These heavier models should be implemented in a backend forecast service or Python runtime, not as ad hoc frontend chart logic.

## Configuration

`chart.forecast`:

```json
{
  "enabled": true,
  "method": "auto",
  "periods": 7,
  "historyWindow": 0
}
```

- `enabled`: turns forecast rendering on/off.
- `method`: `auto`, `linear`, `polynomial`, `exponential`, `logarithmic`, `power`, `reciprocal`, `logistic`, `gompertz`, or `holt_winters`.
- `periods`: number of future x-axis periods to render, currently capped at 60.
  In multi-curve charts this is measured from the latest actual x value in the whole chart, so late-maturing curves with earlier last actual points forecast extra intermediate points until they reach the common final x value.
- `historyWindow`: most recent point count used for fitting. `0` means use all chart data currently loaded.

## Known Boundary

The current implementation forecasts from the data already loaded into the chart. If a chart displays only the last 7 days but should train on 90 or 180 days, add a backend forecast path that can execute a separate history query or transform the existing SQL into a training-history query while preserving datasource permissions and semantic-layer rules.
