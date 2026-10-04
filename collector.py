import urllib.parse
import logging
import feedparser
from typing import List, Set
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from models import NewsArticle

logger = logging.getLogger(__name__)


def clean_html(raw_html: str) -> str:
    """HTMLタグを除去してプレーンテキストにする"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(strip=True)


def collect_product_hunt_items(max_items: int = 10, seen_links: Set[str] = None) -> List[NewsArticle]:
    """Product Huntの最新注目プロダクトフィードからSaaS・AIツールを収集する"""
    if seen_links is None:
        seen_links = set()

    articles: List[NewsArticle] = []
    ph_feed_url = "https://www.producthunt.com/feed"
    logger.info("Product Hunt (最新AI/SaaSプロダクト) を取得中...")

    try:
        feed = feedparser.parse(ph_feed_url)
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue

            title = entry.get("title", "")
            published = entry.get("published", "")
            raw_summary = entry.get("summary", "")
            summary = clean_html(raw_summary)

            article = NewsArticle(
                title=f"[Product Hunt] {title}",
                link=link,
                published=published,
                summary=summary,
                source="Product Hunt",
                is_global=True
            )
            seen_links.add(link)
            articles.append(article)

            if len(articles) >= max_items:
                break
    except Exception as e:
        logger.warning(f"Product Huntフィードの取得中にエラーが発生しました: {e}")

    logger.info(f"Product Huntから {len(articles)} 件の先行プロダクトを収集しました。")
    return articles


def collect_us_google_news(keywords: List[str], max_items: int = 10, seen_links: Set[str] = None) -> List[NewsArticle]:
    """米国のGoogle News (英語) からスモールビジネス向けAI/SaaS動向を収集する"""
    if seen_links is None:
        seen_links = set()

    articles: List[NewsArticle] = []
    for kw in keywords:
        if len(articles) >= max_items:
            break
        logger.info(f"米国ニュースキーワード '{kw}' で検索中...")
        encoded_kw = urllib.parse.quote(kw)
        rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=en-US&gl=US&ceid=US:en"

        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue

                title = entry.get("title", "")
                source = "US Tech News"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source = parts[1].strip()

                published = entry.get("published", "")
                raw_summary = entry.get("summary", "")
                summary = clean_html(raw_summary)

                article = NewsArticle(
                    title=title,
                    link=link,
                    published=published,
                    summary=summary,
                    source=source,
                    is_global=True
                )
                seen_links.add(link)
                articles.append(article)

                if len(articles) >= max_items:
                    break
        except Exception as e:
            logger.warning(f"米国RSSの取得中にエラーが発生しました ({kw}): {e}")

    logger.info(f"米国Techニュースから {len(articles)} 件を収集しました。")
    return articles


def collect_news(
    keywords: List[str],
    max_total_articles: int = 25,
    global_config: dict = None
) -> List[NewsArticle]:
    """
    国内キーワード検索に加え、オプションで海外先行事例（Product Hunt / 米国Tech動向）を統合収集する
    """
    articles: List[NewsArticle] = []
    seen_links: Set[str] = set()

    # 1. 国内ニュースの収集
    for kw in keywords:
        logger.info(f"国内キーワード '{kw}' でニュースを検索中...")
        encoded_kw = urllib.parse.quote(kw)
        # Google News RSS (日本語)
        rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=ja&gl=JP&ceid=JP:ja"

        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue

                title = entry.get("title", "")
                source = "Web News"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source = parts[1].strip()

                published = entry.get("published", "")
                raw_summary = entry.get("summary", "")
                summary = clean_html(raw_summary)

                article = NewsArticle(
                    title=title,
                    link=link,
                    published=published,
                    summary=summary,
                    source=source,
                    is_global=False
                )
                seen_links.add(link)
                articles.append(article)

                if len(articles) >= max_total_articles:
                    break
        except Exception as e:
            logger.warning(f"RSSの取得中にエラーが発生しました ({kw}): {e}")

        if len(articles) >= max_total_articles:
            break

    domestic_count = len(articles)

    # 2. 海外先行事例の収集（有効な場合）
    global_count = 0
    if global_config and global_config.get("enabled", False):
        logger.info("\n--- [海外トレンド・先行SaaS収集] ---")
        max_global = global_config.get("max_articles_to_collect", 10)

        # 2-A: Product Hunt
        if global_config.get("enable_product_hunt", True):
            ph_items = collect_product_hunt_items(max_items=max(3, max_global // 2), seen_links=seen_links)
            articles.extend(ph_items)

        # 2-B: 米国Google News
        us_keywords = global_config.get("us_keywords", ["AI tool for small business", "SMB SaaS AI"])
        if us_keywords:
            us_items = collect_us_google_news(keywords=us_keywords, max_items=max_global, seen_links=seen_links)
            articles.extend(us_items)

        global_count = len(articles) - domestic_count

    logger.info(f"合計 {len(articles)} 件のニュース・先行事例を収集しました (国内: {domestic_count}件, 海外: {global_count}件)")
    return articles
