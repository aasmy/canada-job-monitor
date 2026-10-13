"""Generate a static personal job hub from the monitor database."""
from __future__ import annotations

import argparse
import html
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _connect_rows(db_path: str):
    dsn = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    query = """SELECT company, title, location, remote_status, source, url, canonical_url,
        relevance_score, match_explanation, skills, published_at, first_seen, last_seen,
        notified, eligible
        FROM jobs
        WHERE eligible=1
        ORDER BY first_seen DESC
        LIMIT 500"""
    if dsn:
        import psycopg
        with psycopg.connect(dsn) as db:
            with db.cursor() as cur:
                cur.execute(query)
                jobs = cur.fetchall()
                cur.execute("""SELECT source, configured_status, integration_type, jobs_retrieved,
                    matched_jobs, consecutive_failures, last_success, last_failure, last_error, quota_status
                    FROM source_health ORDER BY source""")
                return jobs, cur.fetchall()
    if not Path(db_path).exists():
        return [], []
    with sqlite3.connect(db_path) as db:
        try:
            jobs = db.execute(query).fetchall()
            try:
                health = db.execute("""SELECT source, configured_status, integration_type, jobs_retrieved,
                    matched_jobs, consecutive_failures, last_success, last_failure, last_error, quota_status
                    FROM source_health ORDER BY source""").fetchall()
            except sqlite3.OperationalError:
                health = []
            return jobs, health
        except sqlite3.OperationalError:
            return [], []


def _freshness(published_at: str, first_seen: str) -> tuple[str, str]:
    raw = published_at or first_seen
    if not raw:
        return "Unknown", "unknown"
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return "Unknown", "unknown"
    hours = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
    if hours <= 24:
        return "24h", "fresh"
    if hours <= 72:
        return "3d", "recent"
    if hours <= 168:
        return "7d", "week"
    return "Older", "older"


def _jobs(rows):
    result = []
    for row in rows:
        company, title, location, remote_status, source, url, canonical_url, score, explanation, skills, published_at, first_seen, last_seen, notified, eligible = row
        fresh_label, fresh_group = _freshness(published_at, first_seen)
        result.append({
            "company": company or "Unknown company",
            "title": title or "Untitled role",
            "location": location or "Location not stated",
            "workplace": remote_status or "Not stated",
            "source": source or "unknown",
            "url": canonical_url or url or "#",
            "score": int(score or 0),
            "why": explanation or "",
            "skills": skills or "",
            "published": published_at or "",
            "firstSeen": first_seen or "",
            "lastSeen": last_seen or "",
            "notified": bool(notified),
            "freshness": fresh_label,
            "freshnessGroup": fresh_group,
        })
    return result


def _health(rows):
    return [{
        "source": row[0] or "unknown",
        "status": row[1] or "unknown",
        "type": row[2] or "unknown",
        "jobs": int(row[3] or 0),
        "matches": int(row[4] or 0),
        "failures": int(row[5] or 0),
        "lastSuccess": row[6] or "",
        "lastFailure": row[7] or "",
        "lastError": row[8] or "",
        "quota": row[9] or "",
    } for row in rows]


def _html(jobs: list[dict], health: list[dict]) -> str:
    data = json.dumps(jobs, ensure_ascii=False).replace("</", "<\\/")
    health_data = json.dumps(health, ensure_ascii=False).replace("</", "<\\/")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Canada Job Hub</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #18212f;
      --muted: #667085;
      --line: #d9dee7;
      --panel: #ffffff;
      --bg: #f5f7fa;
      --red: #c9273a;
      --green: #147a5c;
      --blue: #255f9f;
      --gold: #a45f08;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }}
    header {{ border-bottom: 1px solid var(--line); background: #fff; }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 18px 20px; }}
    .top {{ display: grid; grid-template-columns: 1fr auto; gap: 18px; align-items: center; }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    .sub {{ margin-top: 4px; color: var(--muted); font-size: 14px; }}
    .mark {{ width: 72px; height: 48px; border: 1px solid var(--line); border-radius: 8px; background: linear-gradient(90deg, #fff 0 24%, #c9273a 24% 38%, #fff 38% 62%, #c9273a 62% 76%, #fff 76%); position: relative; }}
    .mark:after {{ content: ""; position: absolute; left: 27px; top: 13px; width: 18px; height: 22px; background: var(--red); clip-path: polygon(50% 0, 60% 30%, 86% 18%, 72% 45%, 100% 48%, 68% 58%, 82% 86%, 50% 68%, 18% 86%, 32% 58%, 0 48%, 28% 45%, 14% 18%, 40% 30%); }}
    .stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }}
    .stat {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .stat b {{ display: block; font-size: 22px; }}
    .stat span {{ color: var(--muted); font-size: 12px; }}
    .controls {{ display: grid; grid-template-columns: minmax(180px, 1fr) repeat(3, minmax(120px, 160px)); gap: 10px; padding-top: 16px; }}
    input, select {{ width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #fff; padding: 10px 11px; color: var(--ink); font: inherit; }}
    main .wrap {{ padding-top: 18px; }}
    .list {{ display: grid; gap: 10px; }}
    .health {{ margin-bottom: 18px; background: #fff; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    .health h2 {{ margin: 0; padding: 13px 14px; font-size: 15px; border-bottom: 1px solid var(--line); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 650; background: #f9fafb; }}
    tr:last-child td {{ border-bottom: 0; }}
    .job {{ background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--blue); border-radius: 8px; padding: 14px; display: grid; grid-template-columns: 1fr auto; gap: 12px; }}
    .job.high {{ border-left-color: var(--green); }}
    .job.review {{ border-left-color: var(--gold); }}
    .title {{ font-size: 16px; font-weight: 750; margin: 0 0 4px; line-height: 1.35; }}
    .meta {{ color: var(--muted); font-size: 13px; display: flex; flex-wrap: wrap; gap: 8px; }}
    .why {{ margin-top: 10px; color: #344054; font-size: 13px; line-height: 1.45; }}
    .skills {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }}
    .pill {{ border: 1px solid var(--line); border-radius: 999px; padding: 4px 8px; font-size: 12px; background: #f9fafb; color: #344054; }}
    .score {{ min-width: 88px; text-align: right; }}
    .score b {{ font-size: 24px; display: block; }}
    .score span {{ color: var(--muted); font-size: 12px; }}
    .apply {{ display: inline-block; margin-top: 10px; color: #fff; background: var(--ink); text-decoration: none; padding: 8px 11px; border-radius: 8px; font-weight: 650; font-size: 13px; }}
    .empty {{ background: #fff; border: 1px dashed var(--line); border-radius: 8px; padding: 30px; text-align: center; color: var(--muted); }}
    footer {{ color: var(--muted); font-size: 12px; padding: 18px 20px 36px; text-align: center; }}
    @media (max-width: 780px) {{
      .top, .job {{ grid-template-columns: 1fr; }}
      .mark {{ display: none; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .controls {{ grid-template-columns: 1fr; }}
      .score {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <div class="top">
        <div>
          <h1>Canada Job Hub</h1>
          <div class="sub">Latest matched software roles from your monitor. Generated {html.escape(generated)}.</div>
        </div>
        <div class="mark" aria-hidden="true"></div>
      </div>
      <section class="stats" aria-label="Job summary">
        <div class="stat"><b id="total">0</b><span>Matched jobs</span></div>
        <div class="stat"><b id="fresh">0</b><span>Published or seen in 24h</span></div>
        <div class="stat"><b id="high">0</b><span>Score 75+</span></div>
        <div class="stat"><b id="review">0</b><span>Needs location review</span></div>
      </section>
      <section class="controls" aria-label="Filters">
        <input id="search" placeholder="Search company, title, skill, location">
        <select id="freshness">
          <option value="">All freshness</option>
          <option value="fresh">24 hours</option>
          <option value="recent">3 days</option>
          <option value="week">7 days</option>
          <option value="older">Older</option>
          <option value="unknown">Unknown</option>
        </select>
        <select id="source"><option value="">All sources</option></select>
        <select id="score">
          <option value="0">Any score</option>
          <option value="60">60+</option>
          <option value="75">75+</option>
          <option value="90">90+</option>
        </select>
      </section>
    </div>
  </header>
  <main><div class="wrap"><section id="health" class="health"></section><section id="list" class="list"></section></div></main>
  <footer>Publication dates are source-provided when available. Unknown dates are not assumed to be recent.</footer>
  <script>
    const jobs = {data};
    const health = {health_data};
    const list = document.getElementById('list');
    const source = document.getElementById('source');
    const controls = ['search', 'freshness', 'source', 'score'].map(id => document.getElementById(id));

    for (const name of [...new Set(jobs.map(j => j.source).filter(Boolean))].sort()) {{
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      source.appendChild(option);
    }}

    function esc(value) {{
      return String(value || '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}
    function render() {{
      const q = document.getElementById('search').value.toLowerCase().trim();
      const f = document.getElementById('freshness').value;
      const s = document.getElementById('source').value;
      const min = Number(document.getElementById('score').value || 0);
      const filtered = jobs.filter(j => {{
        const hay = [j.company, j.title, j.location, j.skills, j.why].join(' ').toLowerCase();
        return (!q || hay.includes(q)) && (!f || j.freshnessGroup === f) && (!s || j.source === s) && j.score >= min;
      }});
      document.getElementById('total').textContent = jobs.length;
      document.getElementById('fresh').textContent = jobs.filter(j => j.freshnessGroup === 'fresh').length;
      document.getElementById('high').textContent = jobs.filter(j => j.score >= 75).length;
      document.getElementById('review').textContent = jobs.filter(j => /review/i.test(j.why)).length;
      if (!filtered.length) {{
        list.innerHTML = '<div class="empty">No matching jobs yet. Add feeds or loosen filters, then let the monitor run.</div>';
        return;
      }}
      list.innerHTML = filtered.map(j => {{
        const cls = j.score >= 75 ? 'high' : (/review/i.test(j.why) ? 'review' : '');
        const skills = (j.skills || '').split(',').map(x => x.trim()).filter(Boolean).slice(0, 8).map(x => `<span class="pill">${{esc(x)}}</span>`).join('');
        return `<article class="job ${{cls}}">
          <div>
            <h2 class="title">${{esc(j.title)}}</h2>
            <div class="meta"><span>${{esc(j.company)}}</span><span>${{esc(j.location)}}</span><span>${{esc(j.workplace)}}</span><span>${{esc(j.source)}}</span><span>${{esc(j.freshness)}}</span></div>
            <p class="why">${{esc(j.why)}}</p>
            <div class="skills">${{skills}}</div>
            <a class="apply" href="${{esc(j.url)}}" target="_blank" rel="noopener">Open application</a>
          </div>
          <div class="score"><b>${{j.score}}</b><span>match score</span></div>
        </article>`;
      }}).join('');
    }}
    function renderHealth() {{
      const target = document.getElementById('health');
      if (!health.length) {{
        target.innerHTML = '<h2>Source health</h2><div class="empty">No persistent source health yet. Run the monitor once with a database configured.</div>';
        return;
      }}
      target.innerHTML = `<h2>Source health</h2><table><thead><tr><th>Source</th><th>Status</th><th>Type</th><th>Jobs</th><th>Matches</th><th>Failures</th><th>Last success</th></tr></thead><tbody>${{health.map(h => `<tr><td>${{esc(h.source)}}</td><td>${{esc(h.status)}}</td><td>${{esc(h.type)}}</td><td>${{h.jobs}}</td><td>${{h.matches}}</td><td>${{h.failures}}</td><td>${{esc(h.lastSuccess || 'none')}}</td></tr>`).join('')}}</tbody></table>`;
    }}
    controls.forEach(control => control.addEventListener('input', render));
    renderHealth();
    render();
  </script>
</body>
</html>"""


def generate(db_path: str, output: str):
    job_rows, health_rows = _connect_rows(db_path)
    jobs = _jobs(job_rows)
    health = _health(health_rows)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_html(jobs, health), encoding="utf8")
    return len(jobs)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="jobs.sqlite3")
    parser.add_argument("--output", default="public/index.html")
    args = parser.parse_args(argv)
    count = generate(args.db, args.output)
    print(f"Generated dashboard with {count} jobs at {args.output}")


if __name__ == "__main__":
    main()
