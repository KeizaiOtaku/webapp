import re
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st


GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

LANGUAGE_MAP = {
    "指定なし": "",
    "英語": "english",
    "日本語": "japanese",
    "中国語": "chinese",
    "韓国語": "korean",
    "フランス語": "french",
    "ドイツ語": "german",
    "スペイン語": "spanish",
}

MAJOR_MEDIA_DOMAINS = {
    # global wires / finance
    "reuters.com": 8,
    "apnews.com": 7,
    "bloomberg.com": 8,
    "ft.com": 7,
    "wsj.com": 7,
    "cnbc.com": 5,
    "marketwatch.com": 4,
    # global general news
    "bbc.com": 7,
    "bbc.co.uk": 7,
    "cnn.com": 5,
    "nytimes.com": 6,
    "washingtonpost.com": 5,
    "theguardian.com": 5,
    "economist.com": 6,
    "aljazeera.com": 5,
    "dw.com": 5,
    "france24.com": 5,
    # japan / asia-focused
    "japantimes.co.jp": 5,
    "asia.nikkei.com": 7,
    "nikkei.com": 7,
    "mainichi.jp": 4,
    "asahi.com": 4,
    "japantoday.com": 3,
    "scmp.com": 5,
}


def normalize_domain(domain: str) -> str:
    """Return a lowercase domain without a leading www."""
    if not isinstance(domain, str):
        return ""
    domain = domain.lower().strip()
    domain = re.sub(r"^www\.", "", domain)
    return domain


def build_gdelt_query(
    keyword: str,
    raw_query_mode: bool,
    language: str,
    exclude_japanese: bool,
    domain_filter: str,
    country_filter: str,
) -> str:
    """Build a GDELT query string from UI filters.

    In raw query mode, the keyword box is passed mostly as-is so the user can use
    GDELT operators such as OR, exact phrases, domain:, sourcecountry:, etc.
    """
    keyword = keyword.strip()
    if not keyword:
        return ""

    parts: List[str] = []

    if raw_query_mode:
        parts.append(keyword)
    else:
        # Simple mode: keep user phrase as normal text search. Users can still type
        # multiple words such as Japan semiconductor.
        parts.append(keyword)

    if language:
        parts.append(f"sourcelang:{language}")

    if exclude_japanese:
        parts.append("-sourcelang:japanese")

    domain_filter = domain_filter.strip().lower().replace("https://", "").replace("http://", "")
    domain_filter = domain_filter.split("/")[0]
    if domain_filter:
        parts.append(f"domain:{domain_filter}")

    country_filter = country_filter.strip()
    if country_filter:
        # Example accepted forms depend on GDELT's source country parser. Let users
        # enter plain English country names such as unitedstates, japan, unitedkingdom.
        country_filter = country_filter.replace(" ", "")
        parts.append(f"sourcecountry:{country_filter}")

    return " ".join(parts)


@st.cache_data(ttl=60 * 10, show_spinner=False)
def fetch_gdelt_articles(query: str, timespan: str, maxrecords: int, sort: str) -> Tuple[pd.DataFrame, str]:
    """Fetch articles from GDELT DOC 2.0 API and return a DataFrame and request URL."""
    params: Dict[str, object] = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": maxrecords,
        "sort": sort,
        "timespan": timespan,
    }
    response = requests.get(GDELT_DOC_API, params=params, timeout=30)
    request_url = response.url
    response.raise_for_status()
    data = response.json()
    articles = data.get("articles", [])
    df = pd.DataFrame(articles)
    return df, request_url


def add_ranking_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add simple ranking columns for display.

    GDELT does not provide PV or SNS-share counts. This score is a lightweight
    editorial helper: major-media bonus + recency bonus + same-domain coverage bonus.
    """
    if df.empty:
        return df

    out = df.copy()

    for col in ["title", "url", "seendate", "domain", "sourcecountry", "language", "socialimage"]:
        if col not in out.columns:
            out[col] = ""

    out["domain_norm"] = out["domain"].map(normalize_domain)
    domain_counts = out["domain_norm"].value_counts().to_dict()
    out["same_domain_count"] = out["domain_norm"].map(domain_counts).fillna(1).astype(int)
    out["major_media_bonus"] = out["domain_norm"].map(MAJOR_MEDIA_DOMAINS).fillna(0).astype(float)

    parsed_dates = pd.to_datetime(out["seendate"], errors="coerce", utc=True)
    now = pd.Timestamp.now(tz="UTC")
    hours_old = (now - parsed_dates).dt.total_seconds() / 3600
    hours_old = hours_old.fillna(9999)
    out["hours_old"] = hours_old.round(1)

    # Recent articles get up to 10 points. Older than 72h receives little recency boost.
    out["recency_bonus"] = (10 - (out["hours_old"] / 7.2)).clip(lower=0, upper=10).round(2)

    # Same-domain count is weakly useful as an activity proxy, capped to avoid spammy sources dominating.
    out["coverage_bonus"] = out["same_domain_count"].clip(upper=5) * 0.5

    out["simple_score"] = (
        out["major_media_bonus"] + out["recency_bonus"] + out["coverage_bonus"]
    ).round(2)

    return out.sort_values(["simple_score", "seendate"], ascending=[False, False])


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def render_article_cards(df: pd.DataFrame, n_cards: int) -> None:
    show_cols = [
        "seendate",
        "title",
        "domain",
        "sourcecountry",
        "language",
        "simple_score",
        "url",
    ]
    for _, row in df.head(n_cards).iterrows():
        title = str(row.get("title", "無題"))
        url = str(row.get("url", ""))
        domain = str(row.get("domain", ""))
        seendate = str(row.get("seendate", ""))
        sourcecountry = str(row.get("sourcecountry", ""))
        language = str(row.get("language", ""))
        score = row.get("simple_score", "")
        socialimage = str(row.get("socialimage", ""))

        with st.container(border=True):
            cols = st.columns([1, 4]) if socialimage.startswith("http") else [None, None]
            if socialimage.startswith("http"):
                with cols[0]:
                    st.image(socialimage, use_container_width=True)
                main_col = cols[1]
            else:
                main_col = st

            with main_col:
                if url.startswith("http"):
                    st.markdown(f"### [{title}]({url})")
                else:
                    st.markdown(f"### {title}")
                st.caption(
                    f"{seendate} | {domain} | {sourcecountry} | {language} | 簡易スコア: {score}"
                )


def main() -> None:
    st.set_page_config(page_title="GDELTニュース検索", page_icon="🌍", layout="wide")

    st.title("🌍 GDELTニュース検索アプリ")
    st.caption("入力したキーワードで世界中のニュースを検索し、記事一覧をCSVで保存できます。")

    with st.sidebar:
        st.header("検索条件")
        keyword = st.text_input(
            "キーワード",
            value="Japan semiconductor",
            placeholder='例: Japan semiconductor / "Bank of Japan" / Toyota',
        )
        raw_query_mode = st.checkbox(
            "GDELT検索演算子をそのまま使う",
            value=True,
            help='OR、完全一致フレーズ、domain:、sourcecountry: などを自分で書きたい場合はON。',
        )
        language_label = st.selectbox("言語", list(LANGUAGE_MAP.keys()), index=0)
        exclude_japanese = st.checkbox("日本語メディアを除外", value=False)
        domain_filter = st.text_input("ドメインで絞る 任意", value="", placeholder="例: reuters.com")
        country_filter = st.text_input(
            "媒体国で絞る 任意",
            value="",
            placeholder="例: unitedstates / japan / unitedkingdom",
        )
        timespan = st.selectbox(
            "期間",
            ["1h", "3h", "6h", "12h", "24h", "3d", "7d", "30d", "3m", "1y"],
            index=4,
        )
        maxrecords = st.slider("最大取得件数", min_value=10, max_value=250, value=100, step=10)
        sort = st.selectbox("並び順", ["datedesc", "dateasc", "hybridrel"], index=0)
        n_cards = st.slider("カード表示件数", min_value=5, max_value=50, value=15, step=5)
        search_button = st.button("検索する", type="primary", use_container_width=True)

    language = LANGUAGE_MAP[language_label]
    gdelt_query = build_gdelt_query(
        keyword=keyword,
        raw_query_mode=raw_query_mode,
        language=language,
        exclude_japanese=exclude_japanese,
        domain_filter=domain_filter,
        country_filter=country_filter,
    )

    st.subheader("検索クエリ")
    st.code(gdelt_query or "キーワードを入力してください", language="text")

    if not search_button and not keyword:
        st.info("左のサイドバーにキーワードを入力して検索してください。")
        return

    if search_button or keyword:
        if not gdelt_query:
            st.warning("キーワードを入力してください。")
            return

        try:
            with st.spinner("GDELTからニュースを取得しています..."):
                df, request_url = fetch_gdelt_articles(gdelt_query, timespan, maxrecords, sort)
        except requests.HTTPError as exc:
            st.error(f"GDELT APIのHTTPエラーです: {exc}")
            st.caption("検索演算子や期間を少し簡単にすると成功することがあります。")
            return
        except requests.RequestException as exc:
            st.error(f"通信エラーです: {exc}")
            return
        except ValueError as exc:
            st.error(f"JSONの読み取りに失敗しました: {exc}")
            return

        st.caption(f"API URL: {request_url}")

        if df.empty:
            st.warning("記事が見つかりませんでした。キーワード、期間、言語条件を変えてください。")
            return

        ranked = add_ranking_columns(df)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("取得記事数", f"{len(ranked):,}")
        c2.metric("媒体数", f"{ranked['domain_norm'].nunique():,}")
        c3.metric("国数", f"{ranked['sourcecountry'].nunique():,}")
        c4.metric("言語数", f"{ranked['language'].nunique():,}")

        st.download_button(
            "CSVをダウンロード",
            data=dataframe_to_csv_bytes(ranked),
            file_name=f"gdelt_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

        tab_cards, tab_table, tab_domains, tab_about = st.tabs(
            ["記事カード", "一覧テーブル", "媒体集計", "メモ"]
        )

        with tab_cards:
            st.caption("簡易スコア順で表示。PVやSNS拡散数ではありません。")
            render_article_cards(ranked, n_cards)

        with tab_table:
            display_cols = [
                "seendate",
                "title",
                "domain",
                "sourcecountry",
                "language",
                "simple_score",
                "major_media_bonus",
                "recency_bonus",
                "same_domain_count",
                "url",
            ]
            available_cols = [c for c in display_cols if c in ranked.columns]
            st.dataframe(
                ranked[available_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn("url"),
                    "title": st.column_config.TextColumn("title", width="large"),
                },
            )

        with tab_domains:
            domain_summary = (
                ranked.groupby("domain_norm", dropna=False)
                .agg(
                    articles=("url", "count"),
                    avg_score=("simple_score", "mean"),
                    latest_seen=("seendate", "max"),
                    countries=("sourcecountry", lambda s: ", ".join(sorted(set(map(str, s.dropna())))[:5])),
                )
                .reset_index()
                .sort_values(["articles", "avg_score"], ascending=[False, False])
            )
            domain_summary["avg_score"] = domain_summary["avg_score"].round(2)
            st.dataframe(domain_summary, use_container_width=True, hide_index=True)

        with tab_about:
            st.markdown(
                """
                #### 使い方の例
                - `Japan semiconductor`
                - `"Bank of Japan" yen`
                - `(Toyota OR Honda OR Nissan) EV`
                - `Japan -sourcelang:japanese`
                - `domain:reuters.com Japan`

                #### 注意
                - GDELTの検索結果はニュース記事の検索結果であり、PV順・SNS拡散順ではありません。
                - このアプリの「簡易スコア」は、主要媒体ボーナス、直近性、同一媒体の記事数を足した独自の目安です。
                - 本格的な人気ランキングを作るなら、同一トピックのクラスタリング、複数国での掲載数、SNS/Google Trendsなどの外部指標を足すと精度が上がります。
                """
            )


if __name__ == "__main__":
    main()
