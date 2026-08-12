# Backend parity and cutover gate

This document applies only to `midas-trading + Cloudflare`. The AliCloud Midas project is a read-only reference until a separately approved cutover.

## Implemented production capabilities

- Registered-user automatic strategies: isolated managed and intelligent accounts, independent capital/settings/positions/history/statistics, scheduled mark-to-market and exits.
- Virtual trading: cash markets, perpetual positions, funding settlement, liquidation/risk scan, conditional orders, account equity curves.
- Alerts and notifications: user rules, edge-trigger/cooldown state, in-app inbox, Telegram/Feishu delivery, quiet hours and configurable economic-event reminders.
- Economic calendar: official Fed/BEA schedules plus deterministic central-bank/macroeconomic rules, bilingual display and cached source-health status.
- Backtesting and Chan analysis: persisted SMA crossover runs with explicit commission/slippage assumptions; fractals, strokes, segments, pivots and structure summary.
- Administration: users, visits, academy, reports, weekly dispatch, support, migration checks, virtual strategy operations and two independent Binance Square accounts.

## Cutover blockers still requiring real production evidence

The following are operational gates, not missing menu pages:

1. Run at least seven consecutive days of scheduled jobs without stuck dispatches, duplicate economic reminders or unexplained circuit trips.
2. Compare calendar event times against their official sources and monitor whether actual/forecast/previous values need a licensed data provider. The current free-source implementation prioritizes reliable schedules; it does not fabricate release values.
3. Run automatic strategies in forward-test mode long enough to validate signal quality, drawdown and execution assumptions. They are usable simulations, not a promise of strategy profitability.
4. Install and smoke-test the independent legacy Binance Square credential, then stop only the old Square scheduler before enabling the new legacy account card.
5. Export and checksum user identities, map Google subject/email identities, rehearse rollback, and only then move the domain. Watchlists and old simulated trades remain optional by product decision.

Domain migration is permitted only after all five gates have explicit evidence and the old runtime remains available for rollback.
