# 海外注目度だけが高い日本ニュースランキング Streamlit app

## 概要

- 50種類の一般固定ワードで日本関連ニュースを広く検索
- 海外記事タイトルからバズワードを自動抽出し、追加検索
- 国内ニュースで注目されている話題を減点
- AI API、NewsAPI、Google News RSS、有料APIは不使用
- GDELT DOC 2.0 APIのみ使用。APIキー不要

## 実行方法

```bash
pip install -r requirements_overseas_japan_news.txt
streamlit run app_overseas_japan_news.py
```

## 注意

- 記事本文や画像を転載せず、見出し・媒体・URL・国などのメタデータを表示します。
- 商用公開する場合も、各記事の本文コピーではなく、元記事へのリンク表示を基本にしてください。
- GDELTの取得結果は自動収集・自動翻訳由来のため、誤分類やノイズが混じります。
