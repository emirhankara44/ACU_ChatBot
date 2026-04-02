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

# Akademik kadro sayfaları JS ile render ediliyor, Playwright gerektirir
JS_RENDERED_URL_PATTERNS = (
    "/akademik-kadro",
    "/ogretim-uyelerimiz",
)


def is_js_rendered(url: str) -> bool:
    return any(pattern in url for pattern in JS_RENDERED_URL_PATTERNS)


def fetch_page_with_playwright(url: str) -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Sayfanın tam yüklenmesi için bekle
        page.wait_for_timeout(2000)
        html = page.content()
        browser.close()
    return html

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


SKIP_PATH_PREFIXES = (
    "/haberler/",
    "/etkinlikler/",
    "/duyurular/",
    "/en/",
)


def is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc not in ALLOWED_DOMAINS:
        return False
    lowered_path = parsed.path.lower()
    if lowered_path.endswith(SKIP_FILE_EXTENSIONS):
        return False
    if any(lowered_path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
        return False
    return True


def build_session(timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.request_timeout = timeout
    return session


def fetch_page(session: requests.Session, url: str) -> str:
    if is_js_rendered(url):
        return fetch_page_with_playwright(url)
    response = session.get(url, timeout=session.request_timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        raise ValueError(f"Skipping non-HTML page: {url}")
    return response.text


NOISE_LINES = {
    "ana içeriğe atla",
    "tanıtım kataloğu",
    "sanal tur",
    "sor",
    "cevaplayalım",
    "ana sayfa",
    "anasayfa",
}


def extract_visible_text(soup: BeautifulSoup) -> str:
    for element in soup(["script", "style", "noscript", "iframe", "nav", "header", "footer"]):
        element.decompose()
    for element in soup.select(".menu, .navbar, .footer, .header, .sidebar, .cookie, .popup, .banner"):
        element.decompose()
    body = soup.body or soup
    text = body.get_text(separator="\n")
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) > 2 and stripped.lower() not in NOISE_LINES:
            lines.append(stripped)
    return "\n".join(lines)


def extract_headings(soup: BeautifulSoup) -> list[str]:
    headings: list[str] = []
    for selector in ("h1", "h2", "h3"):
        for element in soup.select(selector):
            text = element.get_text(" ", strip=True)
            if text and text not in headings:
                headings.append(text)
    return headings[:30]


CAMPUS_URL_TRIGGERS = ("ulasim", "ulaşım", "iletisim", "iletişim", "kampus", "kampüs", "adres", "yerleske", "yerleşke")


def classify_page(url: str, title: str, headings: list[str]) -> str:
    lower_url = url.lower()
    # Adres/ulaşım sayfaları her zaman campus
    if any(trigger in lower_url for trigger in CAMPUS_URL_TRIGGERS):
        return "campus"
    haystack = " ".join([lower_url, title.lower(), " ".join(heading.lower() for heading in headings)])
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


PRIORITY_URL_KEYWORDS = (
    "iletisim", "contact", "adres", "address", "kampus", "kampüs", "campus",
    "fakulte", "fakülte", "faculty",
    "bolum", "bölüm", "department", "program",
    "akademik-kadro", "academic-staff", "kadro", "ogretim-uyesi", "öğretim-üyesi",
    "lisans", "yuksek-lisans", "doktora",
    "hakkimizda", "hakkında", "about",
)


def is_priority_url(url: str) -> bool:
    lower = url.lower()
    return any(keyword in lower for keyword in PRIORITY_URL_KEYWORDS)


SEED_URLS = [
    "https://www.acibadem.edu.tr/",
    "https://www.acibadem.edu.tr/kayit/iletisim/ulasim",
    "https://www.acibadem.edu.tr/iletisim",
    "https://www.acibadem.edu.tr/universite/iletisim",
    "https://www.acibadem.edu.tr/hakkimizda",
    "https://www.acibadem.edu.tr/akademik",
    # Fakülte ana sayfaları
    "https://www.acibadem.edu.tr/akademik/lisans/tip-fakultesi",
    "https://www.acibadem.edu.tr/akademik/lisans/tip-fakultesi/bolumler",
    "https://www.acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi",
    "https://www.acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler",
    "https://www.acibadem.edu.tr/akademik/lisans/saglik-bilimleri-fakultesi",
    "https://www.acibadem.edu.tr/akademik/lisans/saglik-bilimleri-fakultesi/bolumler",
    "https://www.acibadem.edu.tr/akademik/lisans/eczacilik-fakultesi",
    "https://www.acibadem.edu.tr/akademik/lisans/eczacilik-fakultesi/bolumler",
    "https://www.acibadem.edu.tr/akademik/lisans/dis-hekimligi-fakultesi",
    "https://www.acibadem.edu.tr/akademik/lisans/dis-hekimligi-fakultesi/bolumler",
    "https://www.acibadem.edu.tr/akademik/lisans/hukuk-fakultesi",
    "https://www.acibadem.edu.tr/akademik/lisans/hukuk-fakultesi/bolumler",
    "https://www.acibadem.edu.tr/akademik/lisans/isletme-ve-yonetim-bilimleri-fakultesi",
    "https://www.acibadem.edu.tr/akademik/lisans/isletme-ve-yonetim-bilimleri-fakultesi/bolumler",
    # Enstitüler
    "https://www.acibadem.edu.tr/akademik/lisansustu/fen-bilimleri-enstitusu",
    "https://www.acibadem.edu.tr/akademik/lisansustu/saglik-bilimleri-enstitusu",
    # Akademik kadro - fakülte başına
    "https://www.acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/bilgisayar-muhendisligi/akademik-kadro",
    "https://www.acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/biyomedikal-muhendisligi/akademik-kadro",
    "https://www.acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/molekuler-biyoloji-ve-genetik/akademik-kadro",
    "https://www.acibadem.edu.tr/akademik/lisans/saglik-bilimleri-fakultesi/akademik-kadro",
    "https://www.acibadem.edu.tr/akademik/lisans/eczacilik-fakultesi/akademik-kadro",
    "https://www.acibadem.edu.tr/akademik/lisans/dis-hekimligi-fakultesi/akademik-kadro",
    "https://www.acibadem.edu.tr/akademik/lisans/tip-fakultesi/tip-fakultesi-akademik-kadro-alfabetik-sirayla",
    # Aday öğrenci
    "https://www.acibadem.edu.tr/aday/ogrenci",
    "https://www.acibadem.edu.tr/programlar",
]


def crawl_site(start_url: str, max_pages: int, timeout: int) -> list[str]:
    session = build_session(timeout=timeout)
    priority_queue: deque[str] = deque()
    normal_queue: deque[str] = deque()
    seen: set[str] = set()
    saved_urls: list[str] = []

    for seed in SEED_URLS:
        priority_queue.append(normalize_url(seed))

    while (priority_queue or normal_queue) and len(saved_urls) < max_pages:
        url = priority_queue.popleft() if priority_queue else normal_queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        try:
            html = fetch_page(session, url)
            title, category, content, headings, links = parse_page(url, html)
            save_scraped_page(url, title, category, headings, content)
            saved_urls.append(url)
            print(f"Crawled {len(saved_urls)}/{max_pages}: [{category}] {url}")
        except Exception as exc:
            print(f"Skipped {url}: {exc}")
            continue

        for link in links:
            if link not in seen:
                if is_priority_url(link):
                    priority_queue.append(link)
                else:
                    normal_queue.append(link)

    return saved_urls


def main() -> None:
    max_pages = int(os.environ.get("SCRAPE_MAX_PAGES", "300"))
    timeout = int(os.environ.get("SCRAPE_TIMEOUT", "20"))
    saved_urls = crawl_site(BASE_URL, max_pages=max_pages, timeout=timeout)
    print(f"Finished crawl. Saved {len(saved_urls)} pages.")


if __name__ == "__main__":
    main()
