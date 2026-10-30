# 楽天アフィリエイト → WordPress（Xserver）記事自動作成

楽天の商品URLから価格・レビューを集め、ルール（パターン1）に沿った記事テキスト・HTML・
WordPress REST API リクエストを作る。既定では出力のみで、`--post` を付けたときだけ投稿する。

## 価格・レビューの取得順
楽天の商品ページは価格やレビューを JavaScript で後から描画するため、静的HTMLに出ないことがある。

1. 楽天市場商品検索API（`RAKUTEN_APP_ID` があるとき）：`itemPrice` / `reviewCount` / `reviewAverage`
2. 商品ページHTML：JSON-LD → itemprop → meta → 価格・レビュー用クラス名 → 埋め込みJSON
3. どれでも取れない場合のフォールバック
   - 価格：「価格はお得な変動があるためリンク先でご確認ください」
   - レビュー：レビュー由来の一文を入れない（本文にレビュー表現があればルール違反として止める）

## アイキャッチ画像とカテゴリ
トップページの記事カードが「NO IMAGE」「未分類」になるのを防ぐため、`--post` 時に次も行う。

- 商品画像：楽天API の `mediumImageUrls`（600x600 に拡大）→ 商品ページの og:image / JSON-LD の順で探し、
  WordPress のメディアにアップロードしてアイキャッチ（`featured_media`）に設定する。
  article.json の `image_url` で手動指定も可。画像が取れない・アップに失敗した場合はアイキャッチなしで投稿を続ける。
- カテゴリ：`--category 名前`（複数可）＞ article.json の `categories` ＞ 環境変数 `WP_CATEGORY`。
  WordPress に無い名前は自動で作成する。
- X / Threads 用：`social.json` に本文・アフィリンク・商品画像URL（投稿後は WordPress 側の画像URLと記事URLも）を書き出す。

※ API のエンドポイント・パラメータはアプリID発行時に楽天ウェブサービスの最新仕様と照合すること。

## 使い方
```sh
pip install -r requirements.txt
export RAKUTEN_APP_ID=...          # 任意
export RAKUTEN_AFFILIATE_ID=...    # 未設定ならプレースホルダーのリンク
python -m rakuten_wp.cli examples/savas_protein.json --html page.html --out out
# 投稿（下書き）
export WP_USER=... WP_APP_PASSWORD=...
python -m rakuten_wp.cli examples/savas_protein.json --category "サプリ・健康" --post   # 投稿先は arauyo.com（WP_DOMAIN で変更可）
```
