"""Crawl Acibadem University pages and save structured content to the database.

Run from the Django project root:
    python chat/scrape_acibadem.py

Optional environment variables:
    SCRAPE_MAX_PAGES=80
    SCRAPE_TIMEOUT=20
"""

import os
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "confiq.settings")

import django

django.setup()

import requests
from bs4 import BeautifulSoup

from chat.models import ScrapedPage

BASE_URL = "https://www.acibadem.edu.tr/"
ALLOWED_DOMAINS = {"www.acibadem.edu.tr", "acibadem.edu.tr"}
SKIP_FILE_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".zip",
    ".rar",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
)
CATEGORY_KEYWORDS = {
    "departments": ("bolum", "bölüm", "department", "program", "faculty", "fakulte", "fakülte"),
    "tuition": ("ucret", "ücret", "fee", "fees", "tuition", "burs", "scholarship"),
    "admissions": ("aday", "admission", "apply", "application", "basvuru", "başvuru", "kayit", "kayıt"),
    "academics": ("akademik", "academic", "curriculum", "ders", "course", "education", "egitim", "eğitim"),
    "faculty": ("kadro", "staff", "faculty-members", "academic-staff", "akademik-kadro"),
    "news": ("news", "duyuru", "announcement", "haber", "etkinlik", "event"),
    "campus": ("kampus", "kampüs", "campus", "yerleske", "yerleşke", "ulasim", "ulaşım"),
}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    normalized = parsed._replace(fragment="", params="", query="")
    path = normalized.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    normalized = normalized._replace(path=path)
    return urlunparse(normalized)


def is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc not in ALLOWED_DOMAINS:
        return False
    lowered_path = parsed.path.lower()
    if lowered_path.endswith(SKIP_FILE_EXTENSIONS):
        return False
    return True


def build_session(timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.request_timeout = timeout
    return session


def fetch_page(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=session.request_timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        raise ValueError(f"Skipping non-HTML page: {url}")
    return response.text


def extract_visible_text(soup: BeautifulSoup) -> str:
    for element in soup(["script", "style", "noscript", "iframe"]):
        element.decompose()
    body = soup.body or soup
    text = body.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_headings(soup: BeautifulSoup) -> list[str]:
    headings: list[str] = []
    for selector in ("h1", "h2", "h3"):
        for element in soup.select(selector):
            text = element.get_text(" ", strip=True)
            if text and text not in headings:
                headings.append(text)
    return headings[:30]


def classify_page(url: str, title: str, headings: list[str]) -> str:
    haystack = " ".join([url.lower(), title.lower(), " ".join(heading.lower() for heading in headings)])
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return "general"


def discover_links(soup: BeautifulSoup, current_url: str) -> list[str]:
    links: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        candidate = normalize_url(urljoin(current_url, href))
        if is_allowed_url(candidate):
            links.append(candidate)
    return links


def parse_page(url: str, html: str) -> tuple[str, str, str, list[str], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    headings = extract_headings(soup)
    category = classify_page(url, title, headings)
    content = extract_visible_text(soup)
    links = discover_links(soup, url)
    return title, category, content, headings, links


def save_scraped_page(url: str, title: str, category: str, headings: list[str], content: str) -> ScrapedPage:
    page, created = ScrapedPage.objects.update_or_create(
        url=url,
        defaults={
            "title": title[:255],
            "category": category,
            "headings": "\n".join(headings),
            "content": content,
        },
    )
    print(f"Saved {url} category={category} created={created}")
    return page


def crawl_site(start_url: str, max_pages: int, timeout: int) -> list[str]:
    session = build_session(timeout=timeout)
    queue: deque[str] = deque([normalize_url(start_url)])
    seen: set[str] = set()
    saved_urls: list[str] = []

    while queue and len(saved_urls) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        try:
            html = fetch_page(session, url)
            title, category, content, headings, links = parse_page(url, html)
            save_scraped_page(url, title, category, headings, content)
            saved_urls.append(url)
            print(f"Crawled {len(saved_urls)}/{max_pages}: {url}")
        except Exception as exc:
            print(f"Skipped {url}: {exc}")
            continue

        for link in links:
            if link not in seen and link not in queue:
                queue.append(link)

    return saved_urls


def main() -> None:
    max_pages = int(os.environ.get("SCRAPE_MAX_PAGES", "80"))
    timeout = int(os.environ.get("SCRAPE_TIMEOUT", "20"))
    saved_urls = crawl_site(BASE_URL, max_pages=max_pages, timeout=timeout)
    print(f"Finished crawl. Saved {len(saved_urls)} pages.")


if __name__ == "__main__":
    main()
