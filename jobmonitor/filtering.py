"""Multi-stage relevance decisions; unknowns are labelled for review, not invented."""
import re
from dataclasses import dataclass, field

SENIORITY = re.compile(r'\b(senior|sr\.?|staff|principal|lead|manager|director|architect)\b', re.I)
INTERNSHIP = re.compile(r'\b(intern(ship)?|co[ -]?op)\b', re.I)
YEARS = re.compile(r'\b(\d{1,2})\s*(?:\+|to\s*\d{1,2}|[-–—�]\s*\d{1,2})?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+|relevant\s+|industry\s+|work\s+)?experience\b|\b(\d{1,2})\s*[-–—�]\s*\d{1,2}\s*(?:years?|yrs?)\b', re.I)
COUNTRY_EXCLUDED = re.compile(r'\b(USA only|United States only|US only|U\.S\. only|India only|Bangalore|UK only|Europe only)\b',re.I)
WORK_AUTH_EXCLUDED = re.compile(r'\b(must be authorized to work in the united states|us work authorization|u\.s\. work authorization|canada not eligible|primarily hiring in the u\.?s\.?)\b', re.I)
SKILLS = ("python", "javascript", "typescript", "react", "node", "django", "flask", "fastapi", "java", "c#", ".net", "sql", "postgres", "aws", "azure", "docker", "kubernetes", "go", "ruby")


@dataclass(frozen=True)
class MatchResult:
    eligible: bool
    reason: str
    score: int
    explanation: str
    skills: tuple[str, ...] = field(default_factory=tuple)
    experience: str = "Not stated"
    freshness: str = "Publication date unknown"


def _contains_any(text, values):
    return any(re.search(r'(?<!\w)' + re.escape(str(x).lower()) + r'(?!\w)', text) for x in values)


def analyze(job, config):
    f = config['filters']
    title = job.title.lower()
    combined = ' '.join((job.location, job.title, job.description)).lower()
    notes = []
    score = 0

    if SENIORITY.search(title) or any(x.lower() in title for x in f.get('exclude_title_keywords',[]) if x.lower() not in {'intern', 'internship', 'co-op', 'coop'}):
        return MatchResult(False, 'seniority/title excluded', 0, 'Excluded because the title indicates seniority or management.')

    internship = bool(INTERNSHIP.search(title))
    if internship and not f.get('include_internships', False):
        return MatchResult(False, 'internship excluded', 0, 'Excluded because internship/co-op roles are disabled in config.')

    if _contains_any(title, f['role_keywords']):
        score += 30; notes.append('role title matches target software roles')
    elif job.source not in {'greenhouse', 'lever', 'ashby', 'simplify'} and _contains_any(combined, f['role_keywords']):
        score += 18; notes.append('description mentions target software roles')
    else:
        return MatchResult(False, 'role mismatch', 0, 'Excluded because neither title nor description matched configured software roles.')

    years = [int(a or b) for a, b in YEARS.findall(combined)]
    max_years = int(f['max_years'])
    if years and min(years) > max_years:
        return MatchResult(False, 'experience above limit', 0, f'Excluded because minimum stated experience is {min(years)} years.')
    if years:
        score += 20; experience = f"{min(years)}-{max(years)} years" if len(set(years)) > 1 else f"{years[0]} years"
        notes.append('experience requirement is within configured range')
    elif re.search(r'\b(new grad|graduate|entry[ -]?level|associate|junior|software engineer i|developer i)\b', combined, re.I):
        score += 22; experience = 'New grad / entry level'
        notes.append('new-grad or entry-level language found')
    else:
        score += 8; experience = 'Not stated'
        notes.append('experience requirement not clearly stated')

    if COUNTRY_EXCLUDED.search(combined) or WORK_AUTH_EXCLUDED.search(combined):
        return MatchResult(False, 'outside Canada', 0, 'Excluded because location or work authorization appears outside Canada.')
    location = job.location.lower()
    if _contains_any(location, f['locations']):
        score += 25; notes.append('location explicitly matches Canada targets')
    elif location.strip() and job.source in {'greenhouse', 'lever', 'ashby', 'simplify'}:
        return MatchResult(False, 'location unconfirmed/outside target', 0,
                           'The employer location does not explicitly include Canada; company boilerplate does not establish eligibility.')
    elif 'remote' in location and 'canada' in combined:
        score += 22; notes.append('remote role appears Canada-eligible')
    elif _contains_any(combined, f['locations']):
        score += 12; notes.append('REVIEW: location inferred from title/snippet/description')
    elif not location.strip() and f.get('allow_unknown_location_as_review',False):
        score += 5; notes.append('REVIEW: location not verified')
    else:
        return MatchResult(False, 'location unconfirmed/outside target', 0, 'Excluded because Canada eligibility could not be verified.')

    skills = tuple(dict.fromkeys(skill for skill in SKILLS if skill in combined))
    if skills:
        score += min(15, 3 * len(skills)); notes.append('technical skills detected: ' + ', '.join(skills[:8]))

    if internship:
        score -= 10; notes.append('internship/co-op role requires manual graduation-fit review')
    score = max(0, min(100, score))
    reason = 'confirmed Canada location' if 'location explicitly matches Canada targets' in notes else next((n for n in notes if n.startswith('REVIEW')), notes[0])
    return MatchResult(score >= int(f.get('minimum_score', 45)), reason, score, '; '.join(notes), skills, experience)


def evaluate(job,config):
    result = analyze(job, config)
    return result.eligible, result.reason
