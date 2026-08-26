# Social Listening Boundaries

## Current Scope

- Social listening starts from explicit public URLs supplied through task `source_preferences` or `search_plan.social_source_urls`.
- Public social URLs are normalized into `SearchResult` records with `source_type="social"`.
- Social candidates continue through the existing discover, fetch, parse, Source, Evidence, Claim, and Report chain.
- Public social sources currently attach best-effort metadata for platform, sentiment, heat, publish time, and interaction metrics when those values are exposed by the fetched page.

## Compliance Rules

- Do not use login sessions, private APIs, paid API keys, or browser automation for social collection in this MVP path.
- Do not bypass platform access controls, rate limits, robots rules, or deleted/private content boundaries.
- Fetching keeps using the existing `fetch_respect_robots`, user agent, rate limit, retry, timeout, and max-byte controls.
- Host classification only marks likely social sources; successful fetching still depends on public accessibility and robots policy.

## Initially Classified Hosts

- Reddit
- X / Twitter
- Weibo
- Zhihu
- Hacker News
- Product Hunt
- Threads

## Current Metadata Support

- `Source.social_platform` stores the normalized public platform name.
- `Source.published_at` stores a publish time when the fetched page exposes an `article:published_time`, `datePublished`, `publish_date`, `pubdate`, or `<time datetime>` value.
- `Source.sentiment` stores a lightweight rule-based sentiment label: `positive`, `negative`, `neutral`, or `unknown`.
- `Source.heat_score` stores a bounded 0-1 score derived from visible interaction metrics.
- `Source.interaction_metrics_json` stores visible counts such as comments, upvotes/likes, shares, and views.
- `Evidence.locator.social` and `EvidenceOut.social_metadata` carry the same social context for evidence-level display.

## Not Yet Supported

- Platform search APIs or logged-in API integrations.
- Robust NLP sentiment scoring beyond lightweight keyword inference.
- Hidden metrics, deleted/private content, or metrics that require login, paid APIs, browser automation, or bypassing platform controls.
