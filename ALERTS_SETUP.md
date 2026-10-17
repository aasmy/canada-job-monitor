# Connect ALL 15 job websites (Google Alerts discovery)

The default configuration uses named secrets for each waiting source.
After creating each feed, add its URL as a repository Actions secret using
the exact name in SOURCE_COVERAGE.md (for example GOOGLE_ALERT_RSS_LINKEDIN).
The workflow passes all 13 named feed secrets to the monitor. Leave unused
secrets unset; logs report those sources as waiting. Simplify's public list
and the employer watchlist work without these feeds.

**Coverage explained:** the agent does NOT directly crawl all fifteen websites. It *targets* all fifteen through opted-in Google Alerts RSS and optional paid Google search. A target is discoverable only when Google indexes a relevant page and publishes it in an alert. The adapter cannot guarantee every new posting or 15-minute publication latency.

1. Sign in at https://www.google.com/alerts.
2. Create an alert for each of the 15 queries below (or combine sites to reduce maintenance). Select **Show options**: Region **Canada**, Sources **Web**, How often **As-it-happens**, How many **All results**, Deliver to **RSS feed**. Google may not offer all combinations for every account.
3. Copy the RSS feed URL. Paste each under `discovery.rss_feeds` in `config.yaml` as an HTTPS `url`, with a `name` (or put it in a GitHub secret and reference `${GOOGLE_ALERT_RSS_1}`).
4. Run `python -m jobmonitor.main --dry-run` to see detected candidates. RSS results often lack location and experience. Such items are explicitly marked **REVIEW**, not confirmed Canada jobs.
5. Add multiple alerts per site (e.g., one Vancouver and one Canada remote) for better recall.

| Site | Suggested Google Alert query |
|---|---|
| LinkedIn | `site:linkedin.com/jobs/view/ ("software developer" OR "software engineer") (Canada OR Vancouver)` |
| Indeed Canada | `site:ca.indeed.com/viewjob ("software developer" OR "software engineer")` |
| ZipRecruiter | `site:ziprecruiter.com ("software engineer" OR "web developer") Canada` |
| Simplify | `site:simplify.jobs ("new grad" OR "junior") software Canada` |
| Glassdoor | `site:glassdoor.ca/Job/ ("software developer" OR "software engineer") Canada` |
| Wellfound | `site:wellfound.com/jobs ("software engineer" OR "full stack") Canada` |
| Y Combinator Jobs | `site:ycombinator.com/jobs ("software engineer" OR "software developer") Canada` |
| Work at a Startup | `site:workatastartup.com ("software engineer" OR "backend developer") Canada` |
| Canada Job Bank | `site:jobbank.gc.ca ("software developer" OR "software engineer")` |
| TechJobs.ca | `site:techjobs.ca ("software developer" OR "frontend developer")` |
| Communitech Jobs | `site:communitech.ca/jobs ("software developer" OR "software engineer")` |
| Eluta | `site:eluta.ca ("software developer" OR "software engineer") Canada` |
| Google Jobs | Google Jobs is an aggregated results UI, not a standalone feed; use cross-web query `("junior software engineer" OR "new grad software developer") (Canada OR Vancouver) (apply OR careers)` instead. |
| Dice | `site:dice.com ("software developer" OR "software engineer") Canada` |
| Hacker News | `site:news.ycombinator.com/item "Who is hiring" Canada software` (also enable HN Algolia adapter). |

Example configuration:

```yaml
discovery:
  rss_feeds:
    - name: linkedin-google-alert
      url: ${GOOGLE_ALERT_RSS_1}
    - name: simplify-google-alert
      url: ${GOOGLE_ALERT_RSS_2}
  serpapi:
    enabled: false
```

**Important:** Create alerts yourself. We cannot create your Google Alerts from this ZIP; RSS URLs are specific to the alerts you configure. Google Alerts coverage and speed vary. Never treat 'first detected' as 'just posted'.

## Optional SerpApi

- Sign up at https://serpapi.com/ and create the GitHub Actions secret `SERPAPI_KEY`.
- Set `discovery.serpapi.enabled: true` in `config.yaml`.
- **Budget:** one query every 15 minutes = up to **2,880 queries/month**. That exceeds the currently advertised free-tier allowance. To stay near 240 queries per 30 days, run Google search only on a separate daily workflow, or reduce frequency via an explicit schedule/gate. **Do not enable SerpApi at 15-minute cadence on a free plan without adding a quota gate.**
- SerpApi searches rotate across targets, so **one call does not search all fifteen sites**. For comprehensive coverage, configure RSS alerts for each.

## Other source categories

- Greenhouse, Lever, Ashby: supported official/public company board endpoints; configure board tokens in `config.yaml`.
- Hacker News: public Algolia API checks current `Who is hiring?` thread; this is not guaranteed to show all comments because of pagination and relevance.
- LinkedIn and Indeed: do not use logged-in scraping/bots. You can additionally turn on official email alerts in their apps; this project does not read your personal inbox.
