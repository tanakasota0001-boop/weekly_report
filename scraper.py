import re
import logging
import requests
from typing import Optional
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def fetch_article_content(url: str, max_chars: int = 3500, timeout: int = 10) -> Optional[str]:
    """
    指定されたURL（Google NewsのRSSリダイレクトリンクを含む）から記事本文テキストを抽出する。
    失敗時（タイムアウト、403、コンテンツ不足等）はNoneを返す。
    """
    if not url or not url.startswith("http"):
        return None

    try:
        logger.info(f"記事本文をスクレイピング中: {url[:80]}...")
        session = requests.Session()
        resp = session.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            verify=False,
            allow_redirects=True
        )

        if resp.status_code != 200:
            logger.warning(f"記事の取得に失敗しました (Status: {resp.status_code}): {url[:80]}")
            return None

        # 文字コードの推定
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text

        if not html or len(html.strip()) < 100:
            logger.warning(f"取得したHTMLが小さすぎます: {url[:80]}")
            return None

        soup = BeautifulSoup(html, "html.parser")

        # 不要なタグを除去
        unwanted_tags = [
            "script", "style", "noscript", "nav", "footer", "header",
            "aside", "form", "iframe", "svg", "button", "menu"
        ]
        for tag in soup(unwanted_tags):
            tag.decompose()

        # 本文領域を優先的に探す (<article>, <main>, role="main" など)
        content_container = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find(class_=re.compile(r"(article[-_]?body|entry[-_]?content|post[-_]?content|article[-_]?text)", re.I))
            or soup.body
        )

        if not content_container:
            content_container = soup

        # テキスト抽出
        text = " ".join(content_container.stripped_strings)

        # 連続空白・改行の整形
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < 100:
            logger.warning(f"抽出された本文テキストが短すぎます ({len(text)}文字): {url[:80]}")
            return None

        logger.info(f"記事本文のスクレイピングに成功しました ({len(text[:max_chars])}文字取得)")
        return text[:max_chars]

    except requests.exceptions.Timeout:
        logger.warning(f"記事取得がタイムアウトしました: {url[:80]}")
        return None
    except Exception as e:
        logger.warning(f"記事スクレイピング中にエラーが発生しました ({url[:80]}): {e}")
        return None
