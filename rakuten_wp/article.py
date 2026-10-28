"""記事テキスト・HTMLの組み立てとルール（パターン1）チェック。"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from .extract import ItemFacts

PRICE_FALLBACK = "価格はお得な変動があるためリンク先でご確認ください"
DISCLAIMER = (
    "※本記事は掲載時点の情報です。価格の変動や売り切れの場合もありますので、"
    "リンク先のショップで商品価格や販売条件などをご確認ください。"
    "本サイトでは価格や情報の正確性を保証しておりません。"
)
MAX_TOTAL = 1200
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕]")


@dataclass
class Article:
    title: str
    body_lines: list[str]
    hashtags: list[str]
    item_url: str
    link_label: str
    facts: ItemFacts = field(default_factory=ItemFacts)
    affiliate_id: str = "{RAKUTEN_AFFILIATE_ID}"
    affiliate_url: str | None = None

    def price_line(self) -> str:
        if self.facts.price:
            return f"価格：{self.facts.price:,}円（税込・掲載時点）"
        return PRICE_FALLBACK

    def review_line(self) -> str | None:
        """レビュー数値が取れたときだけ「レビューでも〜」の一文を返す。取れなければ None（レビュー表現を使わない）。"""
        f = self.facts
        if f.review_average and f.review_count:
            return f"レビューでも★{f.review_average:.2f}（{f.review_count:,}件）と評価されています"
        if f.review_count:
            return f"レビューでも{f.review_count:,}件の声が寄せられています"
        return None

    def link(self) -> str:
        if self.affiliate_url:
            return self.affiliate_url
        return f"https://hb.afl.rakuten.co.jp/hgc/{self.affiliate_id}/?pc={quote(self.item_url, safe='')}"

    def lines(self) -> list[str]:
        lines = list(self.body_lines)
        review = self.review_line()
        if review:
            lines.append(review)
        lines.append(self.price_line())
        return lines

    def post_text(self) -> str:
        """本文＋空行＋ハッシュタグ（1200文字制限の対象）。"""
        return "\n".join(self.lines()) + "\n\n" + " ".join(self.hashtags)

    def to_text(self) -> str:
        return f"{self.post_text()}\n\n▶ {self.link_label}：{self.link()}\n\n{DISCLAIMER}\n"

    def to_html(self) -> str:
        esc = html.escape
        body = "<br>\n".join(esc(line) for line in self.lines())
        return (
            f"<!-- wp:paragraph -->\n<p>{body}</p>\n<!-- /wp:paragraph -->\n\n"
            f"<!-- wp:paragraph -->\n<p>{esc(' '.join(self.hashtags))}</p>\n<!-- /wp:paragraph -->\n\n"
            f'<!-- wp:paragraph -->\n<p><a href="{esc(self.link())}" target="_blank" '
            f'rel="nofollow sponsored noopener">▶ {esc(self.link_label)}</a></p>\n<!-- /wp:paragraph -->\n\n'
            f'<!-- wp:paragraph {{"fontSize":"small"}} -->\n<p class="has-small-font-size">{esc(DISCLAIMER)}</p>\n'
            f"<!-- /wp:paragraph -->\n"
        )

    def validate(self) -> list[str]:
        """ルール違反を文字列で返す。空なら OK。"""
        problems = []
        lines = self.lines()
        body = "\n".join(lines)
        if not lines[0].startswith("【") or "】" not in lines[0]:
            problems.append("冒頭が【】で始まっていません")
        if not 5 <= len(lines) <= 10:
            problems.append(f"本文が{len(lines)}行です（5〜10行）")
        if not 400 <= len(body) <= 1200:
            problems.append(f"本文が{len(body)}文字です（400〜1200文字）")
        emojis = len(EMOJI_RE.findall(body))
        if not 3 <= emojis <= 5:
            problems.append(f"絵文字が{emojis}個です（3〜5個）")
        if not 5 <= len(self.hashtags) <= 6:
            problems.append(f"ハッシュタグが{len(self.hashtags)}個です（5〜6個）")
        if len(self.post_text()) > MAX_TOTAL:
            problems.append(f"ハッシュタグ込みで{len(self.post_text())}文字です（{MAX_TOTAL}文字以内）")
        if self.review_line() is None and "レビュー" in "\n".join(self.body_lines):
            problems.append("レビュー情報が取れていないのに本文にレビュー由来の表現があります")
        return problems
