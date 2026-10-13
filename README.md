# Canada Job Monitor

Automated Python job monitor for junior/new-grad software roles in Canada. It discovers jobs from permitted public APIs, Google Alerts RSS, optional SerpApi Google results, and Hacker News; filters and scores them; stores persistent history in Supabase/PostgreSQL or SQLite; and sends Telegram alerts without duplicate notifications.

## Architecture

- `jobmonitor/sources.py`: direct public board adapters for Greenhouse, Lever, and Ashby.
- `jobmonitor/discovery.py`: Google Alerts RSS parsing, source detection, URL canonicalization, optional SerpApi search.
- `jobmonitor/hackernews.py`: date-sorted HN Algolia integration for the current monthly Who Is Hiring thread.
- `jobmonitor/filtering.py`: multi-stage deterministic filtering, experience/location checks, skill extraction, relevance score and explanation.
- `jobmonitor/store.py`: SQLite local storage and PostgreSQL/Supabase storage via `DATABASE_URL`.
- `jobmonitor/notify.py`: Telegram HTML formatting and delivery confirmation.
- `jobmonitor/dashboard.py`: static Job Hub generator for GitHub Pages.
- `.github/workflows/monitor.yml`: 15-minute scheduled GitHub Actions monitor with concurrency protection.
- `.github/workflows/tests.yml`: CI test workflow.

## Supported Sources

Working direct integrations:

- Greenhouse company boards
- Lever company boards
- Ashby company boards
- Hacker News Who Is Hiring through HN Algolia

Indirect discovery through Google Alerts RSS or optional SerpApi:

- LinkedIn Jobs, Indeed Canada, ZipRecruiter, Simplify Jobs, Glassdoor, Wellfound, Y Combinator Jobs, Work at a Startup, Canada Job Bank, TechJobs.ca, Communitech Jobs, Eluta.ca, Google Jobs, Dice

See [SOURCE_COVERAGE.md](SOURCE_COVERAGE.md) for the exact coverage policy. The monitor does not scrape Google search result pages, bypass CAPTCHAs, use logged-in sessions, or claim complete coverage of restricted job boards.

## Local Setup on Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m jobmonitor.main --dry-run
```

Dry-run discovers and scores jobs but does not write notification state or send Telegram messages.

Send a Telegram self-test locally:

```powershell
$env:TELEGRAM_BOT_TOKEN="your-token"
$env:TELEGRAM_CHAT_ID="your-chat-id"
python -m jobmonitor.main --test-telegram
```

Generate the local hub:

```powershell
python -m jobmonitor.dashboard --output public/index.html
```

Open `public/index.html` in your browser to inspect the dashboard locally.

## Configuration

Edit `config.yaml`.

Company boards:

```yaml
sources:
  greenhouse:
    - company: Example Co
      board: exampleco
  lever:
    - company: Example Startup
      board: examplestartup
  ashby:
    - company: Example AI
      board: exampleai
```

Google Alerts RSS:

```yaml
discovery:
  rss_feeds:
    - name: linkedin-alert
      url: ${GOOGLE_ALERT_RSS_1}
```

Create alerts at [Google Alerts](https://www.google.com/alerts), choose RSS delivery, then add the feed URL directly or through a GitHub secret. Suggested searches are in [ALERTS_SETUP.md](ALERTS_SETUP.md).

Optional SerpApi:

```yaml
discovery:
  serpapi:
    enabled: true
    max_queries_per_run: 1
```

Set `SERPAPI_KEY`. This can incur cost quickly at 15-minute cadence, so the default config polls SerpApi less often than RSS and caps queries per run.

Filters live under `filters`: locations, role keywords, excluded seniority titles, `max_years`, internship inclusion, and `minimum_score`.

## Telegram

1. Message `@BotFather` in Telegram.
2. Run `/newbot` and save the bot token.
3. Send any message to your new bot.
4. Open `https://api.telegram.org/bot<TOKEN>/getUpdates`.
5. Copy the `chat.id`.

Required secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Example notification:

```text
New Job Found

Company: Example Company
Position: Junior Software Developer
Location: Vancouver, BC
Workplace: Hybrid
Experience: 0-2 years
Match Score: 92/100
Published: Published within 24 hours
Discovered: Just now
Source: Greenhouse
Skills: python, javascript, react
Application: https://example.com/careers/job-123

Why: role title matches target software roles; experience requirement is within configured range; location explicitly matches Canada targets
```

## Supabase/PostgreSQL

1. Create a Supabase project.
2. Open Project Settings, Database, Connection string.
3. Use the pooled or direct Postgres URL with SSL enabled.
4. Add it as a GitHub Actions secret named `DATABASE_URL` or `SUPABASE_DB_URL`.

The app creates the `jobs` table and indexes automatically. If no Postgres URL is configured, it uses `jobs.sqlite3` locally. GitHub Actions can commit that SQLite file as a fallback, but Supabase is the recommended production store.

## GitHub Actions Deployment

1. Push this repository to a private GitHub repository.
2. Add GitHub Actions secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DATABASE_URL` or `SUPABASE_DB_URL`
   - `GOOGLE_ALERT_RSS_1`, `GOOGLE_ALERT_RSS_2`, etc. if referenced in config
   - `SERPAPI_KEY` only if SerpApi is enabled
3. Enable Actions.
4. Run `Tests` manually once.
5. Run `Telegram self-test` manually once. If it succeeds, the workflow log shows a Telegram `message_id` without printing secrets.
6. Run `Canada job monitor` manually once to create the initial baseline. Existing eligible jobs are marked as already notified unless `monitor.send_existing_on_first_run` is true or you pass `--include-existing`.
7. In repository Settings, Pages, set the source to **GitHub Actions**.
8. The monitor workflow generates and deploys the Job Hub after each run. The Pages URL appears in the workflow summary and usually looks like `https://YOUR-USER.github.io/YOUR-REPO/`.
9. The scheduled workflow runs at minutes `7,22,37,52` UTC every hour. GitHub may delay or skip scheduled jobs, so this is best-effort 15-minute monitoring.

Important privacy note: standard GitHub Pages sites may be public depending on your GitHub plan and repository settings. If you do not want job leads visible publicly, use a private Pages option, deploy the generated `public/index.html` to a private host, or keep the hub local.

## Persistence and Deduplication

Stored fields include stable job ID, duplicate key, company, title, location, workplace, description, publication timestamp, first/last seen timestamps, source, application URL, canonical URL, score, explanation, skills, eligibility, notification status, notification time, and delivery error.

Deduplication uses stable external IDs and a conservative company/title/location key. It avoids merging unrelated jobs solely because titles look similar. A Telegram alert is marked delivered only after the Telegram API returns `ok: true`.

The dashboard also displays source health from the persistent database: integration type, configured status, jobs retrieved, matched jobs, consecutive failures, last success, and recent errors. A source warning Telegram message is sent after repeated failures, with rate limiting so temporary outages do not flood you.

## Testing

```powershell
python -m unittest discover -s tests -v
```

Tests mock or use local data for filtering, feed parsing, canonical URLs, deduplication, publication-date handling, and Telegram formatting. Live credentials are not required.

## Troubleshooting

- `Missing Telegram secrets`: add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- Telegram test workflow succeeds but no job alerts arrive: the first monitor run creates a baseline and intentionally suppresses old listings. Set `monitor.send_existing_on_first_run: true`, run with `--include-existing`, or wait for a newly discovered eligible job.
- `No configured sources succeeded`: add Google Alerts RSS feeds, company boards, or keep HN enabled.
- Too many weak review jobs: set `allow_unknown_location_as_review: false` or raise `minimum_score`.
- No Google results: verify the RSS feed URL is HTTPS and still valid.
- Supabase connection failures: check `sslmode=require`, password escaping, pooler host/port, and IP restrictions.
- Duplicate alerts: confirm production runs share the same Supabase database or committed SQLite file.

## Limitations

Google Alerts and SerpApi depend on Google indexing and quotas. Direct company boards only cover companies you configure. Some postings do not expose reliable publication dates; those remain `Publication date unknown` and are not treated as freshly posted. This tool discovers and alerts; it does not apply for jobs.
