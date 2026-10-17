"""Read Simplify's publisher-maintained public new-grad list, not its private APIs."""
from bs4 import BeautifulSoup

from .sources import Job, canonicalize_url, workplace_from_text

PUBLIC_LIST_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"


def parse_list(document: str) -> list[Job]:
    soup = BeautifulSoup(document, "html.parser")
    jobs = []
    for table in soup.find_all("table"):
        company = ""
        for row in table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 4:
                continue
            name = cells[0].get_text(" ", strip=True)
            if name and name not in {chr(0x21b3), chr(0x21aa)}:
                company = name
            title = cells[1].get_text(" ", strip=True)
            location = cells[2].get_text(" ", strip=True)
            if chr(0x1f512) in cells[3].get_text() or chr(0x1f1fa) + chr(0x1f1f8) in title:
                continue
            links = [a.get("href", "") for a in cells[3].find_all("a")]
            links = [url for url in links if url.startswith("https://")]
            if not company or not title or not links:
                continue
            # Prefer the employer's application over the companion Simplify page.
            url = next((url for url in links if "simplify.jobs" not in url), links[0])
            canonical = canonicalize_url(url)
            jobs.append(Job("simplify", canonical, company, title, location, url,
                            "New graduate opportunity listed in Simplify's public new-grad list. " + title,
                            "", canonical, workplace_from_text(location)))
    if not soup.find("table"):
        raise ValueError("Simplify list format changed: no job tables found")
    return jobs


def fetch(session) -> list[Job]:
    response = session.get(PUBLIC_LIST_URL, timeout=30)
    response.raise_for_status()
    return parse_list(response.text)
