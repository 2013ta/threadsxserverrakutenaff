"""WordPress REST API への投稿・画像アップロード・カテゴリ解決。"""

from __future__ import annotations

import mimetypes
import os
import re
from urllib.parse import urlparse

from .article import Article


def _base() -> str:
    return f"https://{os.environ.get('WP_DOMAIN', 'arauyo.com')}/wp-json/wp/v2"


def _auth() -> tuple[str, str]:
    user = os.environ.get("WP_USER")
    password = os.environ.get("WP_APP_PASSWORD")
    if not user or not password:
        raise RuntimeError("WP_USER / WP_APP_PASSWORD が未設定のため投稿を中止しました")
    return user, password


def _check(resp) -> None:
    if resp.status_code in (401, 403):
        raise RuntimeError(f"WordPressの認証に失敗しました（{resp.status_code}）。アプリケーションパスワードを確認してください")
    resp.raise_for_status()


def build_request(article: Article, status: str = "draft", categories=None, tags=None, featured_media=None) -> dict:
    payload = {"title": article.title, "content": article.to_html(), "status": status}
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags
    if featured_media:
        payload["featured_media"] = featured_media
    return {"method": "POST", "url": f"{_base()}/posts", "json": payload}


def resolve_categories(names: list[str], session=None) -> list[int]:
    """カテゴリ名を ID に変える。WordPress に無い名前は新しく作る。"""
    import requests

    http = session or requests
    auth = _auth()
    ids = []
    for name in names:
        resp = http.get(f"{_base()}/categories", params={"search": name, "per_page": 100}, auth=auth, timeout=30)
        _check(resp)
        found = [c["id"] for c in resp.json() if c.get("name") == name]
        if found:
            ids.append(found[0])
            continue
        resp = http.post(f"{_base()}/categories", json={"name": name}, auth=auth, timeout=30)
        _check(resp)
        ids.append(resp.json()["id"])
    return ids


def _filename(image_url: str, content_type: str) -> str:
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or os.path.splitext(urlparse(image_url).path)[1] or ".jpg"
    ext = ".jpg" if ext == ".jpe" else ext
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.splitext(os.path.basename(urlparse(image_url).path))[0]).strip("-")
    return f"{base or 'rakuten-item'}{ext}"


def upload_image(image_url: str, title: str = "", session=None) -> dict:
    """商品画像をダウンロードして WordPress のメディアに登録する。返り値は {id, source_url}。"""
    import requests

    http = session or requests
    auth = _auth()
    img = http.get(image_url, timeout=30)
    img.raise_for_status()
    content_type = img.headers.get("Content-Type", "image/jpeg")
    if not content_type.startswith("image/"):
        raise RuntimeError(f"商品画像が取得できませんでした（{content_type}）: {image_url}")
    resp = http.post(
        f"{_base()}/media",
        data=img.content,
        headers={
            "Content-Type": content_type,
            "Content-Disposition": f'attachment; filename="{_filename(image_url, content_type)}"',
        },
        auth=auth,
        timeout=60,
    )
    _check(resp)
    media = resp.json()
    if title:
        http.post(f"{_base()}/media/{media['id']}", json={"alt_text": title, "title": title}, auth=auth, timeout=30)
    return {"id": media["id"], "source_url": media.get("source_url")}


def send(request: dict, session=None) -> dict:
    """実際に投稿する。WP_USER / WP_APP_PASSWORD が未設定なら送らずに止める。"""
    import requests

    if "{" in request["url"]:
        raise RuntimeError("投稿先URLが未設定です")
    http = session or requests
    resp = http.post(request["url"], json=request["json"], auth=_auth(), timeout=30)
    _check(resp)
    return resp.json()
