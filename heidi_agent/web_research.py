"""Respectful HTML discovery and company-page reading. Public pages only."""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from urllib.parse import urljoin, urlsplit, parse_qs
from urllib.robotparser import RobotFileParser
import ipaddress
import re
import time
import httpx
from bs4 import BeautifulSoup
from .storage import domain_of, normalize_url

USER_AGENT='HeidiResearchCaseStudy/1.0 (+public business research; contact: local user)'
SKIP_DOMAINS=('linkedin.com','facebook.com','instagram.com','twitter.com','x.com',
              'youtube.com','tiktok.com','google.com','maps.google','wikipedia.org',
              't.co','wa.me','whatsapp.com','xing.com','kununu.com','immobilienscout24.de')
SKIP_EXTENSIONS=('.pdf','.png','.jpg','.jpeg','.zip','.doc','.docx','.xlsx','.xls',
                 '.svg','.xml','.ics','.webp','.gif','.exe','.css','.js')
PAGE_TERMS=('leistung','service','ueber','über','team','kontakt','contact',
            'impressum','about','verwaltung','referenz','portfolio','unternehmen')


def safe_url(raw):
    try:
        p=urlsplit(raw)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
            return False
        host=p.hostname.lower()
        if host in ('localhost','localhost.localdomain') or host.endswith(('.local','.internal')):
            return False
        if any(host==x or host.endswith('.'+x) for x in SKIP_DOMAINS):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        if p.path.lower().endswith(SKIP_EXTENSIONS):
            return False
        return True
    except Exception:
        return False


def root_url(url):
    p=urlsplit(url)
    return f'{p.scheme}://{p.netloc}/'


@dataclass
class Page:
    page_id: int
    url: str
    text: str
    html: str = ''

class WebReader:
    def __init__(self, timeout=15, delay=1.0):
        self.client=httpx.Client(follow_redirects=True, timeout=timeout,
                                  headers={'User-Agent':USER_AGENT,'Accept-Language':'de-DE,de;q=0.9,en;q=0.5'})
        self.delay=delay
        self.last={}
        self.robot_cache={}

    def close(self):
        self.client.close()

    def _robots_allowed(self,url):
        origin=root_url(url)
        if origin not in self.robot_cache:
            parser=RobotFileParser()
            try:
                res=self.client.get(urljoin(origin,'robots.txt'))
                if res.status_code==200:
                    parser.parse(res.text.splitlines())
                    self.robot_cache[origin]=parser
                elif res.status_code in (401,403):
                    self.robot_cache[origin]=None
                else:
                    parser.parse([])
                    self.robot_cache[origin]=parser
            except Exception:
                # Respect uncertainty: avoid if robots policy couldn't be checked.
                self.robot_cache[origin]=None
        rp=self.robot_cache[origin]
        return bool(rp and rp.can_fetch(USER_AGENT,url))

    def get(self,url):
        if not safe_url(url):
            raise ValueError('Unsafe or unsupported URL')
        if not self._robots_allowed(url):
            raise PermissionError('robots.txt blocked or unavailable')
        host=domain_of(url)
        spent=time.monotonic()-self.last.get(host,0)
        if spent<self.delay:
            time.sleep(self.delay-spent)
        res=self.client.get(url)
        self.last[host]=time.monotonic()
        if not safe_url(str(res.url)):
            raise ValueError('Redirected to unsupported URL')
        res.raise_for_status()
        if 'html' not in res.headers.get('content-type','text/html').lower():
            raise ValueError('Non-HTML response')
        if len(res.content)>4_500_000:
            raise ValueError('Page too large')
        html=res.text
        soup=BeautifulSoup(html,'html.parser')
        for bad in soup(['script','style','noscript','svg','form','nav','footer']):
            bad.decompose()
        body=soup.body or soup
        text=re.sub(r'\s+',' ',body.get_text(' ',strip=True)).strip()
        if len(text)<65:
            raise ValueError('Too little readable text')
        return str(res.url),html,text[:80000]


def links_from_html(html, base):
    soup=BeautifulSoup(html,'html.parser')
    found=[]
    for a in soup.select('a[href]'):
        href=(a.get('href') or '').strip()
        if href.startswith(('mailto:','tel:','#','javascript:')):
            continue
        full=urljoin(base,href)
        if not safe_url(full):
            continue
        title=a.get_text(' ',strip=True)
        found.append((full,title[:200],a))
    return found


def directory_excerpt(anchor):
    # Keep the smallest parent region containing directory contact details.
    p=anchor
    fallback=anchor.get_text(' ',strip=True)
    for _ in range(6):
        p=p.parent
        if p is None:
            break
        text=re.sub(r'\s+',' ',p.get_text(' ',strip=True))
        if 40<=len(text)<=1150 and any(w in text.lower() for w in ('adresse','telefon','internet','mail','berlin')):
            return text[:1000]
        if 40<=len(text)<=500:
            fallback=text
    return fallback[:750]


# Generic directory discovery: rely on the listing card and link context,
# not on site names or URL paths unique to one directory.
BUSINESS_WORDS = re.compile(
    r'\b(?:gmbh|mbh|ug|ag|e\.?k\.?|hausverwaltung|hausverwalter|'
    r'immobilien(?:management|verwaltung|service)?|property\s+(?:management|solutions)|'
    r'wohnungsverwaltung|wohnungswirtschaft|verwaltungs(?:gesellschaft|büro))\b',
    re.I,
)
SERVICE_WORDS = re.compile(
    r'hausverwaltung|weg.verwal|mietverwaltung|sondereigentum|'
    r'grundstücksverwaltung|immobilienverwaltung|wohnungsverwaltung|'
    r'property\s+management|hausverwalter',
    re.I,
)
ADDRESS_WORDS = re.compile(r'\b\d{5}\s+[A-ZÄÖÜa-zäöüß-]+\b|\b(?:straße|str\.|weg|allee|platz)\s*\d+', re.I)
GENERIC_LINK_TEXT = {
    'kontakt', 'kontakt aufnehmen', 'impressum', 'datenschutz', 'privacy',
    'login', 'anmelden', 'startseite', 'home', 'mehr', 'mehr infos', 'details',
    'ansehen', 'profil', 'profil ansehen', 'website', 'webseite', 'homepage',
    'internet', 'zur webseite', 'zur website', 'weiter', 'zurück',
    'hausverwaltung', 'immobilien', 'berlin', 'route', 'anrufen',
}
BAD_LINK_PARTS = (
    '/impressum', '/datenschutz', '/privacy', '/agb', '/login', '/register',
    '/kontakt', '/contact', '/job', '/karriere', '/cookie', '/hilfe',
    '/suche', '/search', '/branchen/', '/category/', '/kategorie/',
)
CONTAINER_HINTS = re.compile(r'listing|result|treffer|eintrag|entry|card|business|company|firma|anbieter|profile|search-hit', re.I)
NAV_HINTS = re.compile(r'cookie|breadcrumb|social|filter|menu|navigation|topbar|footer|header', re.I)
NEXT_TEXT = {'weiter', 'nächste', 'naechste', 'next', 'next page', 'nächste seite',
             'naechste seite', '>', '»', '→'}


def _clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _attrs_text(node):
    return ' '.join(str(x) for key in ('class', 'id') for x in
                    (node.get(key, []) if isinstance(node.get(key, []), list)
                     else [node.get(key, '')]))


def _navigation_link(a):
    """Ignore global navigation, not listing cards or pagination containers."""
    for p in [a, *list(a.parents)[:8]]:
        if getattr(p, 'name', '') in ('header', 'footer', 'aside'):
            return True
        attrs = _attrs_text(p)
        if NAV_HINTS.search(attrs) and not re.search('pagination|pager', attrs, re.I):
            return True
        if getattr(p, 'name', '') == 'body':
            break
    return False


def _listing_container(anchor):
    """Find nearby text describing a business, not the entire directory page."""
    fallback = anchor
    for parent in list(anchor.parents)[:7]:
        if getattr(parent, 'name', '') in ('body', 'html'):
            break
        text = _clean(parent.get_text(' ', strip=True))
        if not 35 <= len(text) <= 1500:
            continue
        if (SERVICE_WORDS.search(text) or ADDRESS_WORDS.search(text)
                or CONTAINER_HINTS.search(_attrs_text(parent))):
            return parent
        if len(text) <= 550:
            fallback = parent
    return fallback


def _business_name(anchor, region):
    label = _clean(anchor.get_text(' ', strip=True) or anchor.get('title')
                   or anchor.get('aria-label'))
    if label and label.casefold() not in GENERIC_LINK_TEXT and not label.isdigit():
        return label[:200]
    # Some sites put an unlabeled Website / Details link next to the business title.
    if region is not anchor:
        for node in region.select('h2,h3,h4,[itemprop="name"]')[:5]:
            title = _clean(node.get_text(' ', strip=True))
            if title and title.casefold() not in GENERIC_LINK_TEXT:
                return title[:200]
    return ''


def _candidate_from_anchor(link, label, anchor, directory_url, source_domain):
    if _navigation_link(anchor):
        return None
    if link == directory_url or not safe_url(link):
        return None
    parts = urlsplit(link)
    path = parts.path.lower().rstrip('/')
    if any(path.endswith(x) or path.startswith(x) for x in BAD_LINK_PARTS):
        return None
    region = _listing_container(anchor)
    context = _clean(region.get_text(' ', strip=True))[:1000]
    name = _business_name(anchor, region)
    if not name or len(name) < 4 or len(name) > 180:
        return None
    if name.casefold() in GENERIC_LINK_TEXT:
        return None
    link_text = _clean(label).casefold()
    name_like = bool(BUSINESS_WORDS.search(name))
    relevant = bool(SERVICE_WORDS.search(context))
    address = bool(ADDRESS_WORDS.search(context))
    listing_card = bool(CONTAINER_HINTS.search(_attrs_text(region)))
    heading = anchor.parent and anchor.parent.name in ('h2', 'h3', 'h4')
    # Only accept results with enough evidence that this is a listing,
    # never arbitrary external links from the source website.
    evidence = (2 if name_like else 0) + (2 if relevant else 0) + (
        1 if address else 0) + (1 if listing_card else 0) + (1 if heading else 0)
    if evidence < 3:
        return None
    external = domain_of(link) != source_domain
    if not external:
        # Same-site company profiles need stronger evidence than outgoing links.
        if evidence < 4:
            return None
        if link_text in {'website', 'webseite', 'homepage', 'internet'}:
            return None
        # Ignore filters and directory root/category pages. Content evidence
        # is the main criterion; path depth is merely a supporting safeguard.
        if len([segment for segment in path.split('/') if segment]) < 2:
            return None
        return (normalize_url(link), name, context, 'profile', evidence)
    # A link labelled "Website" is useful only when surrounded by an actual listing.
    if link_text in {'website', 'webseite', 'homepage', 'internet', 'zur webseite', 'zur website'}:
        if not (relevant or address or listing_card):
            return None
    return (normalize_url(link), name, context, 'company', evidence)


def profile_page(url, anchor_text, source_domain):
    """Legacy API: conservative generic test based on URL depth and link label.

    Full discovery uses the richer card evidence in _candidate_from_anchor().
    """
    if domain_of(url) != source_domain or not safe_url(url):
        return False
    path = urlsplit(url).path.lower().rstrip('/')
    if any(path.startswith(x) or path.endswith(x) for x in BAD_LINK_PARTS):
        return False
    return (len([p for p in path.split('/') if p]) >= 2
            and bool(BUSINESS_WORDS.search(anchor_text)))


def _page_key(url):
    """Preserve ?page=2 query parameters even if candidate URLs are normalized."""
    p = urlsplit(url)
    return (p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), p.query)


def _pagination_links(html, page_url, directory_url):
    """Find real next/result-page links without knowing individual sites."""
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    origin = domain_of(page_url)
    base_path = urlsplit(directory_url).path.rstrip('/')
    for a in soup.select('a[href],link[rel][href]'):
        href = a.get('href', '')
        link = urljoin(page_url, href)
        if not safe_url(link) or domain_of(link) != origin or link == page_url:
            continue
        parsed = urlsplit(link)
        pth = parsed.path.rstrip('/')
        rel = [str(x).lower() for x in a.get('rel', [])]
        label = _clean(a.get_text(' ', strip=True)).casefold()
        aria = _clean(a.get('aria-label')).casefold()
        pagination_region = any(
            re.search('pagination|pager|page-numbers', _attrs_text(p), re.I)
            for p in [a, *list(a.parents)[:4]]
        )
        page_params = parse_qs(parsed.query)
        has_page_param = any(
            k.casefold() in ('page', 'seite', 'pageno', 'pageindex', 'pg')
            and any(v.isdigit() and int(v) > 1 for v in values)
            for k, values in page_params.items()
        )
        has_page_path = bool(re.search(r'/(?:page|seite)/\d+/?$', pth, re.I))
        is_next = ('next' in rel or label in NEXT_TEXT or aria in NEXT_TEXT)
        is_page_number = bool((pagination_region and label.isdigit()) or
                              has_page_param or has_page_path)
        if not (is_next or is_page_number):
            continue
        # Avoid arbitrary search/city/category detours.
        if pth != base_path and not pth.startswith(base_path + '/'):
            continue
        priority = 0 if is_next else 1
        result.append((priority, link.split('#', 1)[0]))
    return [url for _, url in sorted(result)]


def discover_directory(reader, url, max_profiles=50, max_pages=3):
    """Yield (URL, company name, excerpt, company|profile) from HTML directories.

    max_profiles is the total candidates across at most max_pages result pages.
    Respects WebReader's robots.txt and rate-limit checks; does not bypass JS gates.
    """
    if max_profiles <= 0 or max_pages <= 0:
        return
    pending = deque([url])
    queued = {_page_key(url)}
    seen_pages = set()
    chosen = {}     # normalized company name -> strongest representative candidate
    seen_urls = set()
    page_count = 0
    while pending and page_count < max_pages and len(chosen) < max_profiles:
        page_url = pending.popleft()
        try:
            final, html, text = reader.get(page_url)
        except (httpx.HTTPError, ValueError, PermissionError) as exc:
            if page_count == 0:
                raise
            print(f'[DIRECTORY PAGE SKIP] {page_url}: {str(exc)[:120]}')
            continue
        final_key = _page_key(final)
        if final_key in seen_pages:
            continue
        seen_pages.add(final_key)
        page_count += 1
        source_domain = domain_of(final)
        for link, label, anchor in links_from_html(html, final):
            candidate = _candidate_from_anchor(link, label, anchor, final, source_domain)
            if not candidate:
                continue
            cand_url, name, excerpt, kind, score = candidate
            if cand_url in seen_urls:
                continue
            seen_urls.add(cand_url)
            key = re.sub(r'\W+', '', name.casefold())
            if not key:
                continue
            old = chosen.get(key)
            # Prefer a credible direct website to a directory profile for
            # the same company name, but never merge differently named firms.
            if old is None or (kind == 'company' and old[3] == 'profile'):
                chosen[key] = candidate
            if len(chosen) >= max_profiles:
                break
        if len(chosen) >= max_profiles:
            break
        for next_page in _pagination_links(html, final, url):
            normalized = _page_key(next_page)
            if normalized not in queued and normalized not in seen_pages:
                queued.add(normalized)
                pending.append(next_page)
    for cand_url, name, excerpt, kind, score in chosen.values():
        yield cand_url, name, excerpt, kind


def find_official_website(profile_url, html):
    """Find a likely official company website, not random directory navigation."""
    owner = domain_of(profile_url)
    possible = []
    for link, label, anchor in links_from_html(html, profile_url):
        if domain_of(link) == owner or _navigation_link(anchor):
            continue
        label_lower = _clean(label).casefold()
        priority = 3 if label_lower in {'webseite', 'website', 'homepage', 'internet',
                                        'zur website', 'zur webseite'} else 0
        if re.search(r'(?:webseite|website|homepage|internet)', label_lower):
            priority = max(priority, 2)
        if BUSINESS_WORDS.search(label_lower):
            priority = max(priority, 1)
        if re.search(r'(?:https?://|www\.)[a-z0-9.-]+', label_lower):
            priority = max(priority, 2)
        if anchor.get('itemprop') in ('url', 'sameAs') and priority == 0:
            priority = 1
        if priority:
            possible.append((priority, link))
    possible.sort(reverse=True)
    return root_url(possible[0][1]) if possible else ''


def company_pages(reader,url,max_pages=4,seed_profile=None):
    """Read company home and selected relevant internal pages; directories can be evidence as page 0."""
    pages=[]
    if seed_profile:
        pages.append(Page(0,seed_profile[0],seed_profile[1][:3000],''))
    final,html,text=reader.get(url)
    pages.append(Page(1,final,text[:19000],html))
    origin=domain_of(final)
    candidates=[]
    for link,label,_ in links_from_html(html,final):
        if domain_of(link)!=origin or link==final:
            continue
        if any(word in (link+' '+label).lower() for word in PAGE_TERMS):
            candidates.append(link)
    seen={final}
    for link in candidates:
        if len(pages)-(1 if seed_profile else 0)>=max_pages:
            break
        if link in seen:
            continue
        seen.add(link)
        try:
            resolved,child_html,child_text=reader.get(link)
            pages.append(Page(len(pages)+1,resolved,child_text[:14500],child_html))
        except (httpx.HTTPError,ValueError,PermissionError):
            continue
    return pages
