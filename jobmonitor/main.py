from __future__ import annotations

import argparse
import os
import sys

import requests
import yaml

from .sources import collect
from .discovery import google_alert_feeds, serpapi_search
from .hackernews import fetch as fetch_hn
from .simplify import fetch as fetch_simplify
from .filtering import analyze
from .store import connect
from .notify import format_telegram, send_error_notification, send_telegram, send_test_notification


def load_config(path: str) -> dict:
    with open(path, encoding="utf8") as fh:
        return yaml.safe_load(fh) or {}


def discover(config: dict):
    jobs, errors, successes = collect(config)
    session = requests.Session()
    if config.get("discovery", {}).get("simplify_public_list", {}).get("enabled", False):
        try:
            found = fetch_simplify(session)
            jobs += found
            successes += 1
            print(f"Source simplify/public-list: {len(found)} listings")
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"simplify: {type(exc).__name__}")
    for adapter in (google_alert_feeds, serpapi_search):
        found, errs, ok = adapter(config, session)
        jobs += found; errors += errs; successes += ok
    if config.get("discovery", {}).get("hackernews", {}).get("enabled", False):
        try:
            found = fetch_hn(session, config["discovery"]["hackernews"].get("max_comments", 100))
            jobs += found; successes += 1
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"HN: {type(exc).__name__}: {exc}")
    return jobs, errors, successes


def run(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default="jobs.sqlite3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-existing", action="store_true", help="send existing listings on first persistent run")
    parser.add_argument("--test-telegram", action="store_true", help="send a synthetic Telegram test notification and exit")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if args.test_telegram:
        if not token or not chat_id:
            print("Missing Telegram secrets", file=sys.stderr)
            return 1
        try:
            payload = send_test_notification(token, chat_id)
            message_id = payload.get("result", {}).get("message_id", "unknown")
            print(f"Telegram test delivered; message_id={message_id}")
            return 0
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            print(f"Telegram test failed: {exc}", file=sys.stderr)
            return 1

    jobs, errors, successes = discover(config)
    for err in errors:
        print("SOURCE ERROR:", err, file=sys.stderr)
    if not successes:
        print("No configured sources succeeded. Add RSS URLs or company boards.", file=sys.stderr)
        return 1

    matches = [(job, analyze(job, config)) for job in jobs if job.url]
    eligible = [(job, match) for job, match in matches if match.eligible]
    print(f"Fetched {len(jobs)} jobs, {len(eligible)} candidates, {successes} successful sources, {len(errors)} errors")

    if args.dry_run:
        for job, match in sorted(eligible, key=lambda item: item[1].score, reverse=True)[:40]:
            print(f"{match.score:3d} | {match.reason} | {job.title} | {job.best_url()}")
        if eligible:
            print("\nExample Telegram notification:\n")
            print(format_telegram(eligible[0][0], eligible[0][1]))
        return int(bool(errors))

    if not token or not chat_id:
        print("Missing Telegram secrets", file=sys.stderr)
        return 1

    store = connect(args.db)
    by_key = {}
    by_match = {}
    try:
        first_run = store.count_jobs() == 0
        for job, match in matches:
            key = job.stable_id()
            by_key[key] = job
            by_match[key] = match
            store.record(job, match)
        totals = {}
        matched = {}
        for job, match in matches:
            totals[job.source] = totals.get(job.source, 0) + 1
            if match.eligible:
                matched[job.source] = matched.get(job.source, 0) + 1
        direct = {"greenhouse", "lever", "ashby", "hackernews"}
        store.record_source_successes((source, count, matched.get(source, 0), "direct" if source in direct else "indirect")
                                      for source, count in totals.items())
        health_alerts = store.record_source_errors(errors)
        store.commit()

        send_existing = args.include_existing or config.get("monitor", {}).get("send_existing_on_first_run", False)
        if first_run and not send_existing:
            for key in store.pending_notifications(100000):
                store.mark_notified(key)
            store.commit()
            print("Baseline created; no old-job alerts")
            return int(bool(errors))

        limit = min(40, int(config.get("monitor", {}).get("max_notifications_per_run", 20)))
        failed = False
        for key in store.pending_notifications(limit):
            job = by_key.get(key)
            match = by_match.get(key)
            if not job or not match:
                continue
            try:
                payload = send_telegram(token, chat_id, job, match)
                store.mark_notified(key)
                store.commit()
                message_id = payload.get("result", {}).get("message_id", "unknown")
                print(f"Alert delivered message_id={message_id}: {job.title[:90]}")
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                store.mark_notification_failed(key, str(exc))
                store.commit()
                print("Telegram failed:", exc, file=sys.stderr)
                failed = True
                break
        for source, count, error in health_alerts:
            try:
                send_error_notification(token, chat_id, source, count, error)
                print(f"Source warning sent: {source} ({count} failures)")
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                print("Source warning notification failed:", exc, file=sys.stderr)
                failed = True
        return int(failed or bool(errors))
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(run())
