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

※ API のエンドポイント・パラメータはアプリID発行時に楽天ウェブサービスの最新仕様と照合すること。

## 使い方
```sh
pip install -r requirements.txt
export RAKUTEN_APP_ID=...          # 任意
export RAKUTEN_AFFILIATE_ID=...    # 未設定ならプレースホルダーのリンク
python -m rakuten_wp.cli examples/savas_protein.json --html page.html --out out
# 投稿（下書き）
export WP_USER=... WP_APP_PASSWORD=...
python -m rakuten_wp.cli examples/savas_protein.json --post   # 投稿先は arauyo.com（WP_DOMAIN で変更可）
```
