# Binance Square content operations

This document covers the independent `midas-trading + Cloudflare` line only. It does not read credentials from or deploy changes to the AliCloud Midas runtime.

## Product position

The account publishes decision-useful market context for experienced crypto users. Every post should answer at least one of these questions: what changed, why the market cares, and what observable fact would confirm or invalidate the interpretation.

## Content portfolio

The automatic scheduler uses a five-post cycle:

- 40% market analysis: the strongest current mover, system K-line chart, technical context, and 2-4 related cashtags.
- 40% verified industry news: official or licensed feeds, rewritten with source attribution and follow-up checkpoints.
- 20% event intelligence: large exchange-flow signals and token unlocks when an authorized source is configured; otherwise the slot falls back to news or market analysis.

The scheduler runs every 20 minutes from 08:00 through 22:00 China Standard Time. Those 43 possible windows absorb retries and skipped drafts, while a database-enforced ceiling permits at most 40 successful automatic posts per day. If the verified event queue is empty or stale, the slot immediately falls back to the Midas Trading volatility scan instead of publishing filler news.

## Source policy

| Source | Status | Use |
| --- | --- | --- |
| Midas Trading market data | Active | Market ranking, K-line analysis, chart screenshot |
| PANews, Cointelegraph CN/EN, CoinDesk, Decrypt, The Block, Blockworks | Active | Independent RSS/Atom news inputs; facts are rewritten and source-linked |
| DefiLlama | Active, no key | DEX market volume and protocol activity; free public data only |
| OKX Public Trades | Active, no key | Large perpetual-market trade samples for BTC, ETH, SOL, and BNB; never labelled as an on-chain transfer |
| CoinGecko Demo | Connector ready, off by default | Optional trending-asset signal; requires a free Demo key and source attribution |
| CoinGlass | Not enabled | No free API plan; commercial use requires a paid commercial tier |
| Arkham | Not enabled | API access approval, key, and credits are required; no assumed free production allowance |
| Tokenomist | Connector ready, off by default | Requires API key and a commercial redistribution licence flag |
| Whale Alert | Not enabled | Official real-time API requires a paid key and a persistent WebSocket consumer |
| Odaily / Foresight News | Awaiting official feed/API | Do not scrape page HTML in production; enable when an authorized feed is available |

No article body is copied. The system stores only the facts needed for scoring and rewriting, preserves the source URL, and does not present a third-party report as original reporting.

Every ingestion source writes an independent health record. The admin panel shows healthy, failed, and unconfigured sources together with the latest insert count and latency, so a single bad feed cannot silently make the whole content pool appear healthy or stop other sources.

## Ranking and safety

Events are scored on freshness and market impact. Security incidents, regulation, rates, ETF developments, liquidations, listings, unlocks, and whale activity receive higher weights. Source ID uniqueness, event status, a two-hour same-symbol cooldown, and the platform dispatch ledger prevent duplicates while supporting the higher operating cadence.

The AI prompt cannot add facts, promises, or deterministic price calls. The existing compliance gate remains the final block. Tags are appended by deterministic code, not by the model: the related assets come first, then the daily major-asset pool (`BTC`, `ETH`, `SOL`, `BNB`) fills the post to 2-4 unique cashtags.

## Media pipeline

For market-analysis posts only:

1. Cloudflare Browser Run renders the public crypto detail page.
2. The worker captures the element marked `data-social-chart="true"` at 2x scale.
3. The image is uploaded through Binance Square's presigned upload API.
4. The returned image URL is attached to the post and recorded on the draft.

Screenshot or image-upload failure degrades to a vetted text post and is logged; it does not trip the publishing circuit by itself. A post API failure still counts toward the three-failure circuit breaker.

## Operating metrics

Review weekly by content type:

- successful publish rate and image-attachment rate;
- duplicate suppression and source latency;
- views, follows per 1,000 views, saves, shares, and meaningful comments;
- topic and asset concentration;
- source correction rate, user reports, and blocked-content rate.

Scale the formats that create saves and qualified follows, not merely impressions. Stop or downgrade a source immediately if corrections, attribution gaps, or duplicated facts rise.
