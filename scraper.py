import re
import base64
import logging
import requests
from typing import Optional
from bs4 import BeautifulSoup
import urllib3

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


def safe_requests_get(
    url: str,
    headers: Optional[dict] = None,
    timeout: int = 10,
    session: Optional[requests.Session] = None,
    allow_redirects: bool = True
) -> requests.Response:
    """
    デフォルトでSSL検証（verify=True）を行い、
    社内プロキシや特殊環境でのSSLError発生時のみ安全にverify=Falseへフォールバックして再試行する
    """
    req_headers = headers or DEFAULT_HEADERS
    client = session or requests

    try:
        return client.get(url, headers=req_headers, timeout=timeout, verify=True, allow_redirects=allow_redirects)
    except requests.exceptions.SSLError as e:
        logger.warning(f"SSL証明書検証に失敗しました ({url[:60]}...): {e}。社内環境フォールバック (verify=False) で再試行します。")
        # 警告ログ抑制
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return client.get(url, headers=req_headers, timeout=timeout, verify=False, allow_redirects=allow_redirects)


def resolve_google_news_url(url: str, session: Optional[requests.Session] = None, timeout: int = 8) -> str:
    """
    Google News RSSのURL（https://news.google.com/rss/articles/...）から
    元記事の実際のWebサイトURLを解決・抽出する
    """
    if not url or "news.google.com" not in url:
        return url

    # 1. Base64 / Protobuf トークンのデコードを試行
    try:
        token = ""
        if "/rss/articles/" in url:
            token = url.split("/rss/articles/")[1].split("?")[0]
        elif "/articles/" in url:
            token = url.split("/articles/")[1].split("?")[0]

        if token:
            # Base64パディング補正
            padded = token + "=" * (-len(token) % 4)
            decoded_bytes = base64.urlsafe_b64decode(padded)
            # バイト列の中から http/https で始まるURLを正規表現で抽出
            match = re.search(rb"https?://[a-zA-Z0-9_\-./%?=&+:~#]+", decoded_bytes)
            if match:
                resolved_url = match.group(0).decode("utf-8", errors="ignore")
                # 解決されたURLが google.com ドメインでないことを確認
                if "google.com" not in resolved_url and resolved_url.startswith("http"):
                    logger.info(f"Google News URLのデコードに成功しました: {resolved_url[:80]}...")
                    return resolved_url
    except Exception as e:
        logger.debug(f"Google News Base64デコード失敗 (フォールバックを試みます): {e}")

    # 2. フォールバック: Google NewsページからリダイレクトURLやaタグを抽出
    try:
        resp = safe_requests_get(url, timeout=timeout, session=session, allow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # <c-wiz> 内や <noscript> 内の外部リンクを探索
            for link_tag in soup.find_all("a", href=True):
                href = link_tag["href"]
                if href.startswith("http") and "google.com" not in href:
                    logger.info(f"HTML解析から元記事URLを取得しました: {href[:80]}...")
                    return href
    except Exception as e:
        logger.debug(f"HTMLからのGoogle News元URL解決に失敗しました: {e}")

    return url


def fetch_article_content(url: str, max_chars: int = 3500, timeout: int = 10) -> Optional[str]:
    """
    指定されたURL（Google NewsのRSSリダイレクトリンクを含む）から元記事URLを解決し、
    記事本文テキストを抽出する。失敗時はNoneを返す。
    """
    if not url or not url.startswith("http"):
        return None

    try:
        session = requests.Session()
        
        # Google News RSS URLの場合は元記事URLを解決
        target_url = resolve_google_news_url(url, session=session, timeout=timeout)
        logger.info(f"記事本文をスクレイピング中: {target_url[:80]}...")

        resp = safe_requests_get(
            target_url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            session=session,
            allow_redirects=True
        )

        if resp.status_code != 200:
            logger.warning(f"記事の取得に失敗しました (Status: {resp.status_code}): {target_url[:80]}")
            return None

        # 文字コードの推定
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text

        if not html or len(html.strip()) < 100:
            logger.warning(f"取得したHTMLが小さすぎます: {target_url[:80]}")
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
            logger.warning(f"抽出された本文テキストが短すぎます ({len(text)}文字): {target_url[:80]}")
            return None

        logger.info(f"記事本文のスクレイピングに成功しました ({len(text[:max_chars])}文字取得)")
        return text[:max_chars]

    except requests.exceptions.Timeout:
        logger.warning(f"記事取得がタイムアウトしました: {url[:80]}")
        return None
    except Exception as e:
        logger.warning(f"記事スクレイピング中にエラーが発生しました ({url[:80]}): {e}")
        return None
