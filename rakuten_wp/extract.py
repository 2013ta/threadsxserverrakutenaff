"""楽天商品ページ（HTML）と楽天市場商品検索APIから、価格・レビュー・商品画像を取り出す。

楽天の商品ページは価格やレビューをJavaScriptで後から描画することが多く、
静的HTMLに出てこない場合がある。そのため以下の順で試し、どれでも取れなければ None を返す。

価格:   JSON-LD(offers.price) → itemprop="price" → meta(product:price:amount) →
        価格用クラス名のセレクター → 埋め込みJSONの価格キー
レビュー: JSON-LD(aggregateRating) → itemprop(ratingValue/reviewCount) →
        レビュー用クラス名のセレクター → 埋め込みJSONのレビューキー
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from bs4 import BeautifulSoup

ITEM_SEARCH_API = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

# 商品ページで価格が入っていることがあるクラス名（ページの改修で変わるため複数持つ）
PRICE_SELECTORS = [
    "[itemprop=price]",
    ".price2",
    ".price--OX_YW",
    "[class*=price--]",
]
RATING_SELECTORS = [
    "[itemprop=ratingValue]",
    ".revRvwUserEntryAvg",
    "[class*=rating-value]",
    "[class*=review-score]",
]
REVIEW_COUNT_SELECTORS = [
    "[itemprop=reviewCount]",
    ".revEntryAnchor",
    "[class*=review-count]",
    "[class*=reviewCount]",
]
EMBEDDED_PRICE_KEYS = ["taxIncludedPrice", "itemPrice", "price"]
EMBEDDED_RATING_KEYS = ["reviewAverage", "ratingValue", "averageRating"]
EMBEDDED_COUNT_KEYS = ["reviewCount", "ratingCount", "reviewTotal"]


@dataclass
class ItemFacts:
    price: Optional[int] = None
    review_average: Optional[float] = None
    review_count: Optional[int] = None
    price_source: Optional[str] = None
    review_source: Optional[str] = None
    image_url: Optional[str] = None


def _to_int(text: Any) -> Optional[int]:
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text).split(".")[0])
    return int(digits) if digits else None


def _to_float(text: Any) -> Optional[float]:
    if text is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(text))
    if not m:
        return None
    value = float(m.group())
    return value if 0 < value <= 5 else None


def _attr_or_text(el) -> str:
    return el.get("content") or el.get("value") or el.get_text(" ", strip=True)


def _walk(obj: Any) -> Iterable[dict]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _json_ld(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            blocks.extend(_walk(json.loads(tag.string or "")))
        except (json.JSONDecodeError, TypeError):
            continue
    return blocks


def _embedded_value(html: str, keys: list[str]) -> Optional[str]:
    """<script>内の JSON 風テキストから "key": 値 を探す。"""
    for key in keys:
        m = re.search(rf'"{key}"\s*:\s*"?([\d.,]+)"?', html)
        if m:
            return m.group(1)
    return None


def extract_price(html: str) -> tuple[Optional[int], Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for block in _json_ld(soup):
        offers = block.get("offers")
        for offer in offers if isinstance(offers, list) else [offers]:
            if isinstance(offer, dict) and _to_int(offer.get("price")):
                return _to_int(offer["price"]), "json-ld"
    meta = soup.find("meta", attrs={"property": "product:price:amount"})
    if meta and _to_int(meta.get("content")):
        return _to_int(meta["content"]), "meta"
    for selector in PRICE_SELECTORS:
        for el in soup.select(selector):
            value = _to_int(_attr_or_text(el))
            if value:
                return value, f"selector:{selector}"
    value = _to_int(_embedded_value(html, EMBEDDED_PRICE_KEYS))
    if value:
        return value, "embedded-json"
    return None, None


def extract_review(html: str) -> tuple[Optional[float], Optional[int], Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for block in _json_ld(soup):
        rating = block.get("aggregateRating")
        if isinstance(rating, dict):
            avg = _to_float(rating.get("ratingValue"))
            count = _to_int(rating.get("reviewCount") or rating.get("ratingCount"))
            if avg or count:
                return avg, count, "json-ld"
    avg = count = None
    source = None
    for selector in RATING_SELECTORS:
        el = soup.select_one(selector)
        if el and _to_float(_attr_or_text(el)):
            avg, source = _to_float(_attr_or_text(el)), f"selector:{selector}"
            break
    for selector in REVIEW_COUNT_SELECTORS:
        el = soup.select_one(selector)
        if el and _to_int(_attr_or_text(el)):
            count, source = _to_int(_attr_or_text(el)), source or f"selector:{selector}"
            break
    if avg or count:
        return avg, count, source
    avg = _to_float(_embedded_value(html, EMBEDDED_RATING_KEYS))
    count = _to_int(_embedded_value(html, EMBEDDED_COUNT_KEYS))
    if avg or count:
        return avg, count, "embedded-json"
    return None, None, None


def extract_image(html: str) -> Optional[str]:
    """商品画像のURL。og:image → JSON-LD(image) の順で探す。"""
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"property": "og:image"})
    if meta and meta.get("content", "").startswith("http"):
        return meta["content"]
    for block in _json_ld(soup):
        image = block.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")
        if isinstance(image, str) and image.startswith("http"):
            return image
    return None


def large_image_url(url: str, size: int = 600) -> str:
    """APIの画像URLは ?_ex=128x128 の小さいサムネイルなので、アイキャッチ向けの大きさに差し替える。"""
    if "_ex=" in url:
        return re.sub(r"_ex=\d+x\d+", f"_ex={size}x{size}", url)
    return f"{url}{'&' if '?' in url else '?'}_ex={size}x{size}"


def facts_from_html(html: str) -> ItemFacts:
    price, price_source = extract_price(html)
    avg, count, review_source = extract_review(html)
    return ItemFacts(price, avg, count, price_source, review_source, extract_image(html))


def facts_from_api(item_code: str, application_id: str, session=None) -> ItemFacts:
    """楽天市場商品検索APIで価格・レビューを取る。item_code は "rakuten24:e535922h" の形式。"""
    import requests

    http = session or requests
    resp = http.get(
        ITEM_SEARCH_API,
        params={"applicationId": application_id, "itemCode": item_code, "format": "json"},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("Items") or []
    if not items:
        return ItemFacts()
    item = items[0].get("Item", items[0])
    count = _to_int(item.get("reviewCount"))
    avg = _to_float(item.get("reviewAverage")) if count else None
    images = item.get("mediumImageUrls") or []
    first = images[0] if images else None
    image = first.get("imageUrl") if isinstance(first, dict) else first
    return ItemFacts(
        price=_to_int(item.get("itemPrice")),
        review_average=avg,
        review_count=count or None,
        price_source="api",
        review_source="api" if count else None,
        image_url=large_image_url(image) if image else None,
    )


def merge(*facts: ItemFacts) -> ItemFacts:
    """先に渡したものを優先して、欠けている項目だけ後ろで埋める。"""
    out = ItemFacts()
    for f in facts:
        if out.price is None and f.price is not None:
            out.price, out.price_source = f.price, f.price_source
        if out.review_count is None and out.review_average is None and (f.review_count or f.review_average):
            out.review_average, out.review_count, out.review_source = (
                f.review_average,
                f.review_count,
                f.review_source,
            )
        if out.image_url is None and f.image_url:
            out.image_url = f.image_url
    return out


def item_code_from_url(url: str) -> Optional[str]:
    m = re.search(r"item\.rakuten\.co\.jp/([^/]+)/([^/?#]+)", url)
    return f"{m.group(1)}:{m.group(2)}" if m else None
