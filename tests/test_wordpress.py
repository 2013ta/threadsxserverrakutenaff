import pytest

from rakuten_wp import wordpress
from rakuten_wp.article import Article
from rakuten_wp.extract import ItemFacts, facts_from_api, facts_from_html, large_image_url, merge


class Resp:
    def __init__(self, data=None, status=200, content=b"", headers=None):
        self._data, self.status_code, self.content, self.headers = data, status, content, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._data


class FakeWP:
    def __init__(self, existing=()):
        self.categories = {name: i + 1 for i, name in enumerate(existing)}
        self.calls = []

    def get(self, url, params=None, auth=None, timeout=None):
        self.calls.append(("GET", url))
        if url.endswith("/categories"):
            return Resp([{"id": i, "name": n} for n, i in self.categories.items() if params["search"] in n])
        return Resp(content=b"\xff\xd8jpeg", headers={"Content-Type": "image/jpeg"})

    def post(self, url, json=None, data=None, headers=None, auth=None, timeout=None):
        self.calls.append(("POST", url, headers))
        if url.endswith("/categories"):
            self.categories[json["name"]] = 100
            return Resp({"id": 100})
        if url.endswith("/media"):
            assert data == b"\xff\xd8jpeg"
            return Resp({"id": 55, "source_url": "https://arauyo.com/wp-content/uploads/e535922h.jpg"})
        return Resp({"id": 55})


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv("WP_USER", "u")
    monkeypatch.setenv("WP_APP_PASSWORD", "p")
    monkeypatch.delenv("WP_DOMAIN", raising=False)


def test_image_from_og_and_json_ld():
    assert facts_from_html('<meta property="og:image" content="https://img/a.jpg">').image_url == "https://img/a.jpg"
    html = '<script type="application/ld+json">{"@type":"Product","image":["https://img/b.jpg"]}</script>'
    assert facts_from_html(html).image_url == "https://img/b.jpg"


def test_image_from_api_is_enlarged():
    class S:
        def get(self, url, params, timeout):
            return Resp({"Items": [{"Item": {"itemPrice": 1, "mediumImageUrls": [{"imageUrl": "https://thumbnail.image.rakuten.co.jp/x.jpg?_ex=128x128"}]}}]})

    f = facts_from_api("shop:item", "APPID", S())
    assert f.image_url == "https://thumbnail.image.rakuten.co.jp/x.jpg?_ex=600x600"
    assert large_image_url("https://a/b.jpg") == "https://a/b.jpg?_ex=600x600"
    assert merge(ItemFacts(price=2), f).image_url == f.image_url


def test_resolve_categories_reuses_and_creates():
    wp = FakeWP(existing=["サプリ・健康"])
    assert wordpress.resolve_categories(["サプリ・健康", "プロテイン"], wp) == [1, 100]
    assert ("POST", "https://arauyo.com/wp-json/wp/v2/categories", None) in wp.calls


def test_upload_image_and_featured_media():
    wp = FakeWP()
    media = wordpress.upload_image("https://thumbnail.image.rakuten.co.jp/@0_mall/rakuten24/cabinet/e535922h.jpg?_ex=600x600", "ザバス", wp)
    assert media["id"] == 55
    upload = next(c for c in wp.calls if c[1].endswith("/media"))
    assert upload[2]["Content-Disposition"] == 'attachment; filename="e535922h.jpg"'
    article = Article("t", ["【a】"], ["#a"], "https://item.rakuten.co.jp/s/i/", "見る")
    req = wordpress.build_request(article, categories=[1], featured_media=55)
    assert req["json"]["featured_media"] == 55 and req["json"]["categories"] == [1]


def test_upload_rejects_non_image():
    class S(FakeWP):
        def get(self, url, params=None, auth=None, timeout=None):
            return Resp(content=b"<html>", headers={"Content-Type": "text/html"})

    with pytest.raises(RuntimeError):
        wordpress.upload_image("https://x/y.jpg", session=S())
