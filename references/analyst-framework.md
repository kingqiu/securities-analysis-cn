# Analyst Framework

Use this reference when improving recommendation logic, report sections, or prompts.

## Recommendation Contract

The report should not ask an LLM to invent a buy/sell call directly. The deterministic model should first produce:

- rating: strong buy, buy, cautious buy, hold, watch, or avoid
- rating horizon: normally 6-12 months
- fair value range: bear, base, and bull scenarios
- trading plan: buy zone, watch zone, take-profit zone, and review stop
- position plan: staged entry, observation, or staged exit guidance
- core evidence: valuation, quality, growth, funds/technical, and risk
- rebuttal conditions: what would invalidate the thesis

The LLM may explain this structure in professional language, but must not change the rating, target prices, or risk level.

## Buy/Sell Zone Principles

Avoid wording such as "best buy point" or "best sell point". Use trading-plan language:

- Safety-margin buy zone: price is below intrinsic/fair value with enough downside buffer.
- Watch zone: thesis is acceptable, but price does not offer enough margin of safety.
- Take-profit zone: price approaches base-to-bull fair value, so expected return declines.
- Review stop: not a guaranteed stop-loss order; it is a price or fundamental trigger to re-check the thesis.
- Position plan: keep it conservative and scenario-based. Use staged entry or staged exit language instead of all-in/all-out instructions.

For ordinary users, always explain that a buy zone is a probability-weighted plan, not a precise prediction.

## Stock Scoring Pillars

Recommended weights for A-share single-stock reports:

- Valuation and margin of safety: historical PE percentile, industry PE percentile, base-case upside.
- Business quality: ROE, cash-flow conversion, gross margin, leverage, audit opinion.
- Growth and catalysts: revenue growth, profit growth, earnings forecast, industry policy or cycle.
- Funds and technicals: moving-average structure, main-money flow, margin balance, shareholder count.
- Risk penalty: pledge ratio, high leverage, negative cash conversion, high valuation, bear-case downside.

The final recommendation should explain both the score and the most important overrides. For example, a high-quality company can still be "hold" if valuation is too expensive.

## Peer Comparison Principles

Peer comparison should distinguish:

- Direct peers: similar business model, products, customers, and pricing power.
- Industry leaders: highest market cap, revenue, profit, ROE, or market share.
- Valuation anchors: peers that the market consistently prices at a premium.
- Risk references: peers with similar business but weaker cash flow, leverage, or governance.

Do not rely only on the exchange industry label. If data permits, include at least one industry leader and explain why the target is cheaper or more expensive than the leader.

## Current Peer Model Implementation

`peer_model.py` expects `industry_peers.peers` to include, when available:

- `ts_code`, `name`
- `mv_bn` or `total_mv`
- `pe_ttm`, `pb`
- `roe`, `gross_margin`
- `rev_growth`, `profit_growth`

The model labels peers as:

- Market-cap leader: top peers by market value.
- Quality benchmark: highest available ROE among peer representatives.
- Valuation anchor: lowest positive PE among peer representatives.
- Direct comparable: same-industry representative without a special role.

When interpreting a target company:

- A valuation discount is only attractive if quality and growth are not structurally weaker.
- A valuation premium needs support from superior ROE, growth, market position, or cash-flow quality.
- A smaller company versus the leader needs a clear share-gain or niche-strength argument.
