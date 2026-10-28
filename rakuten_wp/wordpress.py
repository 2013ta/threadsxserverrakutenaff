"""WordPress REST API（POST /wp-json/wp/v2/posts）のリクエスト作成と送信。"""

from __future__ import annotations

import os

from .article import Article


def build_request(article: Article, status: str = "draft", categories=None, tags=None) -> dict:
    domain = os.environ.get("WP_DOMAIN", "{YOUR_DOMAIN}")
    payload = {"title": article.title, "content": article.to_html(), "status": status}
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags
    return {"method": "POST", "url": f"https://{domain}/wp-json/wp/v2/posts", "json": payload}


def send(request: dict, session=None) -> dict:
    """実際に投稿する。WP_USER / WP_APP_PASSWORD が未設定なら送らずに止める。"""
    import requests

    user = os.environ.get("WP_USER")
    password = os.environ.get("WP_APP_PASSWORD")
    if not user or not password or "{" in request["url"]:
        raise RuntimeError("WP_DOMAIN / WP_USER / WP_APP_PASSWORD が未設定のため投稿を中止しました")
    http = session or requests
    resp = http.post(request["url"], json=request["json"], auth=(user, password), timeout=30)
    if resp.status_code in (401, 403):
        raise RuntimeError(f"WordPressの認証に失敗しました（{resp.status_code}）。アプリケーションパスワードを確認してください")
    resp.raise_for_status()
    return resp.json()
