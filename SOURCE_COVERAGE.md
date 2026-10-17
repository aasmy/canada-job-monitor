# Source Coverage

## Enabled connections

These public endpoints were tested live on 2026-10-17. Counts include all
listings returned, before filtering; they are not counts of new matching jobs.

| Employer | Integration | Board | Listings returned |
|---|---|---|---|
| Affirm | Greenhouse | affirm | 214 |
| Reddit | Greenhouse | reddit | 146 |
| PointClickCare | Lever | pointclickcare | 79 |
| Wealthsimple | Ashby | wealthsimple | 48 |
| Cohere | Ashby | cohere | 118 |
| 1Password | Ashby | 1password | 74 |
| Jane | Ashby | jane | 21 |

Simplify's public new-grad list returned 547 parsed listings. Employer links
are preferred. Publication dates are unknown: relative list ages are not used
as dates. This covers the published list, not the whole Simplify website.

## The 15 requested websites

| Website | Connection | Status in shipped configuration |
|---|---|---|
| LinkedIn | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_LINKEDIN |
| Indeed Canada | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_INDEED |
| ZipRecruiter | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_ZIPRECRUITER |
| Simplify | Publisher-maintained public GitHub list | Live verified; enabled |
| Glassdoor | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_GLASSDOOR |
| Wellfound | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_WELLFOUND |
| Y Combinator Jobs | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_YCOMBINATOR |
| Work at a Startup | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_WORKATASTARTUP |
| Canada Job Bank | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_JOBBANK |
| TechJobs.ca | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_TECHJOBSCA |
| Communitech | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_COMMUNITECH |
| Eluta | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_ELUTA |
| Google Jobs | Cross-web Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_GOOGLEJOBS; not the Google Jobs UI |
| Dice | Google Alerts RSS | Waiting for GOOGLE_ALERT_RSS_DICE |
| Hacker News Who Is Hiring | HN Algolia API | Live verified; enabled |

Each RSS secret is mapped by the workflow. Until you create and add the
corresponding Google Alert feed, that source is not connected. Logs explicitly
report missing feed configuration. Optional SerpApi remains disabled.

## Date and eligibility handling

Greenhouse update timestamps are not publication dates. Publication remains
unknown unless `first_published` is supplied. Lever qualification sections are
included in description analysis. Unknown Canadian eligibility is excluded by
default; snippets that mention Canada still require manual verification.

## References

- [Greenhouse public Job Board API](https://docs.greenhouse.io/job-board)
- [Lever public Postings API](https://github.com/lever/postings-api)
- [Ashby public job posting API](https://developers.ashbyhq.com/docs/public-job-posting-api)
- [Simplify public new-grad list](https://github.com/SimplifyJobs/New-Grad-Positions)
- [Simplify recommended resources](https://help.simplify.jobs/help/articles/1517186-more-job-resources)

Google Alerts depends on indexing and may miss postings. No login, CAPTCHA,
or access restrictions are bypassed.
