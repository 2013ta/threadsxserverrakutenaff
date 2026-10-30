"""楽天商品URL → 価格・レビュー・商品画像取得 → 記事・HTML・WordPressリクエストを出力する。

使い方:
  python -m rakuten_wp.cli article.json [--html page.html] [--out out/] [--category 名前] [--post]

article.json には title / body_lines / hashtags / item_url / link_label を書く。
任意で categories（カテゴリ名のリスト）と image_url（商品画像を手で指定）も書ける。
カテゴリは --category ＞ article.json の categories ＞ 環境変数 WP_CATEGORY の順で決める。
--post のときは商品画像を WordPress のメディアに上げてアイキャッチにし、カテゴリも付ける
（WordPress に無いカテゴリ名は作成する）。
X / Threads 投稿用に、本文・リンク・画像URLを social.json にも書き出す。
--html を渡すとその HTML から、RAKUTEN_APP_ID があれば楽天APIから価格・レビューを取り、
取れなければフォールバック（価格の定型文・レビュー表現なし）で組み立てる。
--post を付けたときだけ WordPress に送信する（既定は下書き、出力のみ）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .article import Article
from .extract import ItemFacts, facts_from_api, facts_from_html, item_code_from_url, merge
from .wordpress import build_request, resolve_categories, send, upload_image


def collect_facts(item_url: str, html: str | None) -> ItemFacts:
    found = []
    app_id = os.environ.get("RAKUTEN_APP_ID")
    code = item_code_from_url(item_url)
    if app_id and code:
        try:
            found.append(facts_from_api(code, app_id))
        except Exception as exc:  # API が落ちていても HTML とフォールバックで続ける
            print(f"楽天APIの取得に失敗しました: {exc}", file=sys.stderr)
    if html:
        found.append(facts_from_html(html))
    return merge(*found) if found else ItemFacts()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("article_json")
    p.add_argument("--html", help="保存済みの商品ページHTML")
    p.add_argument("--out", default="out")
    p.add_argument("--status", default="draft", choices=["draft", "publish"])
    p.add_argument("--category", action="append", help="カテゴリ名（複数指定可）")
    p.add_argument("--post", action="store_true", help="WordPress に実際に送信する")
    args = p.parse_args(argv)

    spec = json.loads(Path(args.article_json).read_text(encoding="utf-8"))
    html = Path(args.html).read_text(encoding="utf-8") if args.html else None
    facts = collect_facts(spec["item_url"], html)
    if spec.get("image_url"):
        facts.image_url = spec["image_url"]
    categories = args.category or spec.get("categories") or (
        [os.environ["WP_CATEGORY"]] if os.environ.get("WP_CATEGORY") else []
    )
    article = Article(
        facts=facts,
        affiliate_id=os.environ.get("RAKUTEN_AFFILIATE_ID", "{RAKUTEN_AFFILIATE_ID}"),
        **{k: spec[k] for k in ("title", "body_lines", "hashtags", "item_url", "link_label")},
    )

    print(f"価格: {facts.price or 'なし→フォールバック'}（{facts.price_source or '-'}）")
    print(f"レビュー: ★{facts.review_average or '-'} / {facts.review_count or '-'}件（{facts.review_source or 'なし→レビュー表現なし'}）")
    print(f"商品画像: {facts.image_url or 'なし→アイキャッチなし'}")
    print(f"カテゴリ: {', '.join(categories) or 'なし→WordPressの既定カテゴリ'}")
    problems = article.validate()
    for msg in problems:
        print(f"ルール違反: {msg}", file=sys.stderr)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    request = build_request(article, status=args.status)
    social = {"text": article.post_text(), "link": article.link(), "image_url": facts.image_url}
    plan = {"categories": categories, "featured_image_url": facts.image_url}

    def write_outputs():
        (out / "article.txt").write_text(article.to_text(), encoding="utf-8")
        (out / "article.html").write_text(article.to_html(), encoding="utf-8")
        (out / "request.json").write_text(json.dumps({**request, "plan": plan}, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "social.json").write_text(json.dumps(social, ensure_ascii=False, indent=2), encoding="utf-8")

    write_outputs()
    print(f"出力: {out}/article.txt, article.html, request.json, social.json")

    if args.post:
        if problems:
            print("ルール違反があるため投稿しません", file=sys.stderr)
            return 1
        category_ids = resolve_categories(categories) if categories else None
        media = None
        if facts.image_url:
            try:
                media = upload_image(facts.image_url, title=article.title)
                print(f"アイキャッチ画像を登録しました: id={media['id']} {media['source_url']}")
            except Exception as exc:  # 画像が落ちても記事は投稿する
                print(f"商品画像のアップロードに失敗しました（アイキャッチなしで投稿します）: {exc}", file=sys.stderr)
        request = build_request(
            article, status=args.status, categories=category_ids, featured_media=media and media["id"]
        )
        if media and media.get("source_url"):
            social["wp_image_url"] = media["source_url"]
        result = send(request)
        social["wp_url"] = result.get("link")
        write_outputs()
        print(f"投稿しました: id={result.get('id')} status={result.get('status')} {result.get('link')}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
