# Source Coverage

This project deliberately separates direct integrations from indirect discovery. It does not bypass logins, CAPTCHAs, robots, rate limits, or private APIs. Coverage depends on the sources and feeds you configure.

## Working Direct Integrations

| Source | Method | Configuration | Publication date quality |
|---|---|---|---|
| Greenhouse company boards | Public Greenhouse Job Board API | `sources.greenhouse[].board` | Source-provided update timestamp |
| Lever company boards | Public Lever Postings API | `sources.lever[].board` | Source-provided created timestamp |
| Ashby company boards | Public Ashby posting API | `sources.ashby[].board` | Source-provided published timestamp |
| Hacker News Who Is Hiring | Public HN Algolia API | `discovery.hackernews.enabled` | Comment creation timestamp |

## Indirect Discovery

These sources are covered through Google Alerts RSS feeds you create, optional SerpApi Google searches, or both. The monitor reads the RSS/API outputs only; it does not scrape Google result pages or the target sites.

| Source | Recommended method | Notes |
|---|---|---|
| LinkedIn Jobs | Google Alerts RSS / optional SerpApi | Direct automated access commonly requires account/session controls. |
| Indeed Canada | Google Alerts RSS / optional SerpApi | Use `site:ca.indeed.com/viewjob` queries. |
| ZipRecruiter | Google Alerts RSS / optional SerpApi | Search-result snippets may need manual review. |
| Simplify Jobs | Google Alerts RSS / optional SerpApi | Good fit for new-grad searches. |
| Glassdoor | Google Alerts RSS / optional SerpApi | Direct scraping is not used. |
| Wellfound | Google Alerts RSS / optional SerpApi | Prefer company board links when found. |
| Y Combinator Jobs | Google Alerts RSS / optional SerpApi | Separate from HN Who Is Hiring. |
| Work at a Startup | Google Alerts RSS / optional SerpApi | Configure targeted alerts. |
| Canada Job Bank | Google Alerts RSS / optional SerpApi | Add direct API only if a documented public API is configured later. |
| TechJobs.ca | Google Alerts RSS / optional SerpApi | Configure targeted alerts. |
| Communitech Jobs | Google Alerts RSS / optional SerpApi | Configure targeted alerts. |
| Eluta.ca | Google Alerts RSS / optional SerpApi | Configure targeted alerts. |
| Google Jobs | Cross-web Google Alerts / optional SerpApi | Google Jobs is a search UI, not a public feed. |
| Dice | Google Alerts RSS / optional SerpApi | Configure targeted alerts. |

## Manual Configuration Required

- Google Alerts RSS URLs are account-specific and must be added to `config.yaml` or GitHub Actions secrets.
- SerpApi is optional, paid or quota-limited, and disabled by default.
- Company boards for Greenhouse, Lever, and Ashby require board tokens/slugs.
- Supabase requires a Postgres connection string in `DATABASE_URL` or `SUPABASE_DB_URL`.
- Telegram requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## Unsupported Claims

The system does not claim comprehensive coverage of all postings on LinkedIn, Indeed, Glassdoor, Google Jobs, or other restricted sites. It reports what configured permitted feeds/APIs return, marks unknown publication dates as unknown, and uses the first discovery time only as a monitoring timestamp.
