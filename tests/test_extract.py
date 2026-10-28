from rakuten_wp.article import PRICE_FALLBACK, Article
from rakuten_wp.extract import ItemFacts, facts_from_api, facts_from_html, item_code_from_url, merge

BODY = ["【強み】" + "あ" * 80 + "🍫", "い" * 80 + "💪", "う" * 80 + "🥤", "え" * 80 + "✨", "お" * 80]
TAGS = ["#a", "#b", "#c", "#d", "#e"]


def make(facts):
    return Article("t", BODY, TAGS, "https://item.rakuten.co.jp/shop/item1/", "楽天で見る", facts)


def test_price_from_json_ld():
    html = '<script type="application/ld+json">{"@type":"Product","offers":{"price":"4,298"},"aggregateRating":{"ratingValue":"4.62","reviewCount":"1234"}}</script>'
    f = facts_from_html(html)
    assert (f.price, f.price_source) == (4298, "json-ld")
    assert (f.review_average, f.review_count) == (4.62, 1234)


def test_price_from_itemprop_and_selectors():
    html = '<span itemprop="price" content="3980"></span><span class="revRvwUserEntryAvg">4.5</span><a class="revEntryAnchor">(321件)</a>'
    f = facts_from_html(html)
    assert (f.price, f.review_average, f.review_count) == (3980, 4.5, 321)


def test_embedded_json():
    html = '<script>window.__INIT__={"taxIncludedPrice":5480,"reviewAverage":"4.3","reviewCount":88}</script>'
    f = facts_from_html(html)
    assert (f.price, f.price_source, f.review_count) == (5480, "embedded-json", 88)


def test_nothing_found_uses_fallback():
    f = facts_from_html("<html><body>商品説明のみ</body></html>")
    a = make(f)
    assert f.price is None and f.review_count is None
    assert a.lines()[-1] == PRICE_FALLBACK
    assert not any("レビュー" in line for line in a.lines())


def test_review_line_and_price_line():
    a = make(ItemFacts(price=4298, review_average=4.62, review_count=1234))
    assert "レビューでも★4.62（1,234件）" in a.to_text()
    assert "4,298円" in a.to_text()


def test_validate_flags_review_words_without_data():
    a = make(ItemFacts())
    a.body_lines = BODY[:-1] + ["レビューでも好評です" + "お" * 80]
    assert any("レビュー" in p for p in a.validate())


def test_api_and_merge():
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"Items": [{"Item": {"itemPrice": 4298, "reviewCount": 10, "reviewAverage": 4.5}}]}

    class S:
        def get(self, url, params, timeout):
            assert params["itemCode"] == "rakuten24:e535922h"
            return Resp()

    api = facts_from_api(item_code_from_url("https://item.rakuten.co.jp/rakuten24/e535922h/"), "APPID", S())
    merged = merge(ItemFacts(), api)
    assert (merged.price, merged.review_count, merged.price_source) == (4298, 10, "api")
