"""Legal/opt-in discovery: Google Alerts RSS, generic RSS and optional SerpApi."""
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs, unquote
import os
import re
import time
import xml.etree.ElementTree as ET
import requests
from .sources import Job, plain, canonicalize_url, parse_datetime, workplace_from_text, due_sources

BOARDS = {
 'linkedin':'linkedin.com/jobs', 'indeed':'indeed.com',
 'ziprecruiter':'ziprecruiter.com', 'simplify':'simplify.jobs',
 'glassdoor':'glassdoor.ca', 'wellfound':'wellfound.com',
 'ycombinator':'ycombinator.com', 'workatastartup':'workatastartup.com',
 'jobbank':'jobbank.gc.ca', 'techjobsca':'techjobs.ca',
 'communitech':'communitech.ca', 'eluta':'eluta.ca',
 'googlejobs':'google.com', 'dice':'dice.com',
 'hackernews':'news.ycombinator.com',
}

def unwrap_link(url):
    """Unwrap Google Alerts target URLs, without visiting the redirect."""
    parsed = urlparse(url)
    if parsed.hostname and ('google.' in parsed.hostname or parsed.hostname.endswith('google.com')):
        qs = parse_qs(parsed.query)
        for key in ('url', 'q'):
            if qs.get(key) and qs[key][0].startswith(('https://','http://')):
                return qs[key][0]
    return url

def detect_source(url):
    host = (urlparse(url).hostname or '').lower().removeprefix('www.')
    for name, domain in BOARDS.items():
        base = domain.split('/')[0]
        if host == base or host.endswith('.'+base):
            return name
    return 'web'

def parse_feed(xml, label='rss'):
    root = ET.fromstring(xml)
    entries = []
    # Handle RSS and Atom (including Google Alerts RSS).
    nodes = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
    for node in nodes:
        def field(*tags):
            for tag in tags:
                el = node.find(tag)
                if el is not None:
                    if el.text and el.text.strip(): return el.text.strip()
                    if el.attrib.get('href'): return el.attrib['href']
            return ''
        title = plain(field('title','{http://www.w3.org/2005/Atom}title'))
        url = unwrap_link(field('link','{http://www.w3.org/2005/Atom}link'))
        summary = plain(field('description','{http://www.w3.org/2005/Atom}summary','{http://www.w3.org/2005/Atom}content'))
        if not title or not url.startswith(('https://','http://')): continue
        # Search results frequently contain a publisher suffix; avoid fabricating company/location.
        source = detect_source(url)
        entries.append(Job(source, canonicalize_url(url), source, title, '', url, summary,
                           parse_datetime(field('pubDate','{http://www.w3.org/2005/Atom}updated')),
                           canonicalize_url(url), workplace_from_text(title, summary)))
    return entries

def google_alert_feeds(config, session):
    if not due_sources(config, "rss"):
        return [], [], 0
    result=[]; errors=[]; successes=0
    for i, entry in enumerate(config.get('discovery',{}).get('rss_feeds',[])):
        name = entry.get('name','feed-'+str(i)) if isinstance(entry,dict) else 'feed-'+str(i)
        url = entry.get('url','') if isinstance(entry,dict) else str(entry)
        if url.startswith('${') and url.endswith('}'):
            url = os.getenv(url[2:-1], '')
        if not url: continue
        if not url.startswith('https://'):
            errors.append(f'{name}: feed URL must use HTTPS'); continue
        try:
            r=session.get(url,timeout=20,headers={'User-Agent':'CanadaJobMonitor/2.0 (personal feed reader)'})
            r.raise_for_status()
            result.extend(parse_feed(r.text,name)); successes+=1
        except (requests.RequestException,ET.ParseError,ValueError) as e:
            errors.append(f'{name}: {type(e).__name__}: {e}')
        time.sleep(0.4)
    return result, errors, successes

def serpapi_search(config, session):
    """Optional bounded Google search via a commercial provider; never scrape Google directly."""
    settings = config.get('discovery',{}).get('serpapi',{})
    if not settings.get('enabled') or not due_sources(config, "serpapi"): return [],[],0
    key = os.getenv('SERPAPI_KEY')
    if not key: return [], ['SerpApi enabled but SERPAPI_KEY secret missing'],0
    queries = settings.get('queries',[])
    # Capped calls/run. Also cap per-day using cached DB budget in main (handled by caller via env).
    count = min(int(settings.get('max_queries_per_run',1)),3,len(queries))
    if count == 0: return [],[],0
    # Rotate based on 15-min UTC bucket, so not always the first query.
    bucket = int(time.time()//900)
    chosen = [queries[(bucket*count+i)%len(queries)] for i in range(count)]
    jobs=[]; errors=[]; successes=0
    for query in chosen:
        try:
            r=session.get('https://serpapi.com/search.json',params={'engine':'google','q':query,'location':'Canada','num':10,'api_key':key},timeout=25)
            r.raise_for_status()
            payload=r.json()
            if payload.get('error'): raise ValueError(payload['error'])
            for item in payload.get('organic_results',[]):
                title=plain(item.get('title','')); url=item.get('link',''); snippet=plain(item.get('snippet',''))
                if not title or not url.startswith('https://'): continue
                source=detect_source(url)
                jobs.append(Job(source,canonicalize_url(url),source,title,'',url,snippet,'',
                                canonicalize_url(url),workplace_from_text(title, snippet)))
            successes+=1
        except (requests.RequestException,ValueError) as e:
            errors.append(f'SerpApi: {type(e).__name__}: {e}')
    return jobs,errors,successes
