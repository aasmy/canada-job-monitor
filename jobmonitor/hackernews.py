"""Hacker News Algolia API: recent Who is Hiring story comments."""
import datetime as dt
import re
import requests
from .sources import Job,plain,parse_datetime,workplace_from_text

def fetch(session, limit=100):
    # Discover latest monthly thread using date sorting; plain search can surface old high-relevance posts.
    data=session.get('https://hn.algolia.com/api/v1/search_by_date',params={'query':'Who is hiring?','tags':'story','hitsPerPage':50},timeout=20).json()
    stories=[x for x in data.get('hits',[]) if re.search(r'^Ask HN: Who is hiring\?',x.get('title',''),re.I)]
    if not stories: return []
    story=max(stories,key=lambda x:x.get('created_at_i',0))
    cutoff=dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=45)
    if int(story.get('created_at_i') or 0) < int(cutoff.timestamp()):
        return []
    parent=story['objectID']
    data=session.get('https://hn.algolia.com/api/v1/search_by_date',params={'tags':f'comment,story_{parent}','hitsPerPage':min(int(limit),100)},timeout=20).json()
    jobs=[]
    for c in data.get('hits',[]):
        content=plain(c.get('comment_text') or '')
        if not content or len(content)<50: continue
        head=content[:170]
        jobs.append(Job('hackernews',c['objectID'],'HN Who is Hiring',head,'',
                        f'https://news.ycombinator.com/item?id={c["objectID"]}',content,
                        parse_datetime(c.get('created_at','')), '', workplace_from_text(content)))
    return jobs
