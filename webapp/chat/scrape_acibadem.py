"""Selenium + BeautifulSoup scraper for Acıbadem University homepage.

This script saves the homepage text to the Django database so the chat LLM can use it.

Run from the Django project root:
    python chat/scrape_acibadem.py
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "confiq.settings")

import django
django.setup()

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

from chat.models import ScrapedPage


def fetch_page_source(url: str, timeout: int = 15) -> str:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return driver.page_source
    finally:
        driver.quit()


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    body = soup.body or soup
    text = body.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def parse_homepage(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else "(no title)"
    content = extract_visible_text(html)

    print(f"Page title: {title}\n")
    print("Top-level links:")
    for a in soup.select("a[href]")[:30]:
        text = a.get_text(strip=True)
        href = a["href"]
        if text:
            print(f"- {text} -> {href}")

    print("\nSample headlines and section titles:")
    for selector in ["h1", "h2", "h3", ".hero__title", ".news-item__title", ".button"]:
        for element in soup.select(selector)[:10]:
            text = element.get_text(strip=True)
            if text:
                print(f"[{selector}] {text}")

    return title, content


def save_scraped_page(url: str, title: str, content: str) -> ScrapedPage:
    page, created = ScrapedPage.objects.update_or_create(
        url=url,
        defaults={"title": title, "content": content},
    )
    print(f"Saved scraped page: {page.url} (created={created})")
    return page


def main() -> None:
    url = "https://www.acibadem.edu.tr/"
    html = fetch_page_source(url)
    title, content = parse_homepage(html)
    save_scraped_page(url, title, content)


if __name__ == "__main__":
    main()
