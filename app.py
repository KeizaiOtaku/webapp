import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import requests
import streamlit as st


APP_VERSION = "v1.8-verified-title-filter-access-interval"
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
CACHE_DIR = Path(".gdelt_cache")
CACHE_TTL_SECONDS = 60 * 60  # 1 hour

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
    "reuters.com": 8,
    "apnews.com": 7,
    "bloomberg.com": 8,
    "ft.com": 7,
    "wsj.com": 7,
    "cnbc.com": 5,
    "marketwatch.com": 4,
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
    "japantimes.co.jp": 5,
    "asia.nikkei.com": 7,
    "nikkei.com": 7,
    "mainichi.jp": 4,
    "asahi.com": 4,
    "japantoday.com": 3,
    "scmp.com": 5,
}

BROAD_SINGLE_WORDS = {
    "breaking",
    "news",
    "latest",
    "update",
    "updates",
    "world",
    "today",
}


def init_state() -> None:
    defaults = {
        "last_api_time": 0.0,
        "last_df_json": None,
        "last_request_url": "",
        "last_result_source": "",
        "last_error": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def normalize_domain(domain: str) -> str:
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
    keyword = keyword.strip()
    if not keyword:
        return ""

    parts: List[str] = [keyword]

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
        country_filter = country_filter.replace(" ", "")
        parts.append(f"sourcecountry:{country_filter}")

    # raw_query_mode is kept for UI compatibility. In both modes, GDELT receives a text query.
    # The difference is only the user's expectation/explanation in the UI.
    return " ".join(parts)


def cache_key(query: str, timespan: str, maxrecords: int, sort: str) -> str:
    raw = json.dumps(
        {
            "query": query,
            "timespan": timespan,
            "maxrecords": maxrecords,
            "sort": sort,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def read_disk_cache(key: str, allow_stale: bool = False) -> Tuple[pd.DataFrame, str, bool]:
    path = cache_path(key)
    if not path.exists():
        return pd.DataFrame(), "", False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        created_at = float(payload.get("created_at", 0))
        is_fresh = (time.time() - created_at) <= CACHE_TTL_SECONDS
        if not is_fresh and not allow_stale:
            return pd.DataFrame(), "", False
        df = pd.DataFrame(payload.get("articles", []))
        request_url = str(payload.get("request_url", ""))
        return df, request_url, is_fresh
    except Exception:
        return pd.DataFrame(), "", False


def write_disk_cache(key: str, df: pd.DataFrame, request_url: str) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    payload = {
        "created_at": time.time(),
        "request_url": request_url,
        "articles": df.to_dict(orient="records"),
    }
    cache_path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def fetch_gdelt_articles(query: str, timespan: str, maxrecords: int, sort: str) -> Tuple[pd.DataFrame, str]:
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
    return pd.DataFrame(data.get("articles", [])), request_url


def is_broad_single_word_query(keyword: str) -> bool:
    cleaned = keyword.lower().strip().strip('"\'')
    return cleaned in BROAD_SINGLE_WORDS


def extract_words(text: str) -> List[str]:
    # Remove common GDELT operators so title filtering does not try to match domain:, sourcelang:, etc.
    text = re.sub(r"[-+]?\b(?:domain|sourcelang|sourcecountry|theme|near|repeat)\s*:\s*\S+", " ", text, flags=re.I)
    text = re.sub(r"\b(?:AND|OR|NOT)\b", " ", text, flags=re.I)
    tokens = re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ヶー]+", text)
    return [t.lower() for t in tokens if t.strip()]


def apply_title_filter(df: pd.DataFrame, filter_text: str, match_mode: str) -> pd.DataFrame:
    if df.empty or not filter_text.strip():
        return df

    if "title" not in df.columns:
        return df.iloc[0:0].copy()

    out = df.copy()
    titles = out["title"].fillna("").astype(str).str.lower()
    filter_text_lower = filter_text.strip().lower()

    if match_mode == "フレーズ一致":
        mask = titles.str.contains(re.escape(filter_text_lower), regex=True, na=False)
    else:
        words = extract_words(filter_text)
        if not words:
            return out
        if match_mode == "いずれかの単語":
            mask = pd.Series(False, index=out.index)
            for word in words:
                mask = mask | titles.str.contains(re.escape(word), regex=True, na=False)
        else:  # すべての単語
            mask = pd.Series(True, index=out.index)
            for word in words:
                mask = mask & titles.str.contains(re.escape(word), regex=True, na=False)

    return out[mask].copy()


def add_ranking_columns(df: pd.DataFrame) -> pd.DataFrame:
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
    out["hours_old"] = hours_old.fillna(9999).round(1)
    out["recency_bonus"] = (10 - (out["hours_old"] / 7.2)).clip(lower=0, upper=10).round(2)
    out["coverage_bonus"] = out["same_domain_count"].clip(upper=5) * 0.5
    out["simple_score"] = (out["major_media_bonus"] + out["recency_bonus"] + out["coverage_bonus"]).round(2)

    return out.sort_values(["simple_score", "seendate"], ascending=[False, False])


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def render_article_cards(df: pd.DataFrame, n_cards: int) -> None:
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
            if socialimage.startswith("http"):
                img_col, main_col = st.columns([1, 4])
                with img_col:
                    st.image(socialimage, use_container_width=True)
            else:
                main_col = st

            with main_col:
                if url.startswith("http"):
                    st.markdown(f"### [{title}]({url})")
                else:
                    st.markdown(f"### {title}")
                st.caption(f"{seendate} | {domain} | {sourcecountry} | {language} | 簡易スコア: {score}")


def main() -> None:
    st.set_page_config(page_title="GDELTニュース検索", page_icon="🌍", layout="wide")
    init_state()

    st.title("🌍 GDELTニュース検索アプリ")
    st.caption("入力したキーワードで世界中のニュースを検索し、記事一覧をCSVで保存できます。")
    st.caption(f"アプリ版: {APP_VERSION}")

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
            help="OR、完全一致フレーズ、domain:、sourcecountry: などを自分で書きたい場合はON。",
        )
        language_label = st.selectbox("言語", list(LANGUAGE_MAP.keys()), index=0)
        exclude_japanese = st.checkbox("日本語メディアを除外", value=False)
        domain_filter = st.text_input("ドメインで絞る 任意", value="", placeholder="例: reuters.com")
        country_filter = st.text_input("媒体国で絞る 任意", value="", placeholder="例: unitedstates / japan / unitedkingdom")
        timespan = st.selectbox("期間", ["1h", "3h", "6h", "12h", "24h", "3d", "7d", "30d", "3m", "1y"], index=2)
        maxrecords = st.slider("最大取得件数", min_value=10, max_value=250, value=60, step=10)
        sort = st.selectbox("並び順", ["datedesc", "dateasc", "hybridrel"], index=0)
        n_cards = st.slider("カード表示件数", min_value=5, max_value=50, value=15, step=5)

        st.divider()
        st.header("API負荷対策")
        access_interval_sec = st.slider(
            "APIアクセス最小間隔（秒）",
            min_value=0.0,
            max_value=2.0,
            value=0.5,
            step=0.05,
            format="%.2f",
            help="キャッシュが無い新規検索だけ、この秒数以上あけてGDELT APIへアクセスします。",
        )
        use_cache = st.checkbox("キャッシュを使用する", value=True)
        if st.button("キャッシュを削除", use_container_width=True):
            if CACHE_DIR.exists():
                for path in CACHE_DIR.glob("*.json"):
                    path.unlink(missing_ok=True)
            st.success("キャッシュを削除しました。")

        elapsed = time.time() - float(st.session_state.get("last_api_time", 0.0))
        remaining = max(0.0, access_interval_sec - elapsed)
        st.caption(f"次の新規API送信まで: 約{remaining:.2f}秒")
        st.caption(f"アプリ版: {APP_VERSION}")

        search_button = st.button("検索する", type="primary", use_container_width=True)

    language = LANGUAGE_MAP[language_label]
    gdelt_query = build_gdelt_query(keyword, raw_query_mode, language, exclude_japanese, domain_filter, country_filter)

    st.subheader("検索クエリ")
    st.code(gdelt_query or "キーワードを入力してください", language="text")

    st.subheader("検索結果フィルター（GDELT取得後にアプリ側で絞り込み）")
    filter_col1, filter_col2 = st.columns([1, 2])
    with filter_col1:
        title_filter_enabled = st.checkbox("タイトルに検索ワードを含む記事だけ", value=False)
        title_match_mode = st.selectbox("タイトル一致条件", ["すべての単語", "いずれかの単語", "フレーズ一致"], index=0)
    with filter_col2:
        title_filter_text = st.text_input(
            "タイトル内フィルター語",
            value=keyword,
            help="domain: や -sourcelang: などを含む検索では、ここにタイトル内で一致させたい語だけを書くのがおすすめです。",
        )

    if is_broad_single_word_query(keyword):
        st.warning("検索語が広すぎます。例: `Breaking Japan`、`Breaking earthquake`、`Japan semiconductor` のように具体語を足すと429を避けやすくなります。")

    if not gdelt_query:
        st.info("キーワードを入力して検索してください。")
        return

    current_key = cache_key(gdelt_query, timespan, maxrecords, sort)

    if search_button:
        df = pd.DataFrame()
        request_url = ""
        source = ""

        if use_cache:
            cached_df, cached_url, is_fresh = read_disk_cache(current_key, allow_stale=False)
            if not cached_df.empty:
                df, request_url, source = cached_df, cached_url, "cache"

        if df.empty:
            elapsed = time.time() - float(st.session_state.get("last_api_time", 0.0))
            remaining = access_interval_sec - elapsed
            if remaining > 0:
                st.warning(f"APIアクセス最小間隔のため、あと約{remaining:.2f}秒待ってから検索してください。")
                return

            try:
                with st.spinner("GDELTからニュースを取得しています..."):
                    df, request_url = fetch_gdelt_articles(gdelt_query, timespan, maxrecords, sort)
                st.session_state["last_api_time"] = time.time()
                source = "api"
                if use_cache:
                    write_disk_cache(current_key, df, request_url)
            except requests.HTTPError as exc:
                st.session_state["last_api_time"] = time.time()
                stale_df, stale_url, _ = read_disk_cache(current_key, allow_stale=True)
                if exc.response is not None and exc.response.status_code == 429 and not stale_df.empty:
                    st.warning("GDELT APIが429を返しました。保存済みキャッシュを表示します。")
                    df, request_url, source = stale_df, stale_url, "stale_cache_after_429"
                else:
                    st.error(f"GDELT APIのHTTPエラーです: {exc}")
                    st.caption("最大取得件数を減らす、期間を短くする、検索語を具体化する、アクセス間隔を少し上げる、の順で対処してください。")
                    return
            except requests.RequestException as exc:
                st.error(f"通信エラーです: {exc}")
                return
            except ValueError as exc:
                st.error(f"JSONの読み取りに失敗しました: {exc}")
                return

        st.session_state["last_df_json"] = df.to_json(orient="records", force_ascii=False)
        st.session_state["last_request_url"] = request_url
        st.session_state["last_result_source"] = source

    if not st.session_state.get("last_df_json"):
        st.info("検索条件を設定して「検索する」を押してください。入力変更だけではAPIへアクセスしません。")
        return

    df = pd.read_json(st.session_state["last_df_json"], orient="records")
    request_url = st.session_state.get("last_request_url", "")
    result_source = st.session_state.get("last_result_source", "")

    st.caption(f"結果ソース: {result_source or 'unknown'}")
    if request_url:
        st.caption(f"API URL: {request_url}")

    raw_count = len(df)
    if df.empty:
        st.warning("記事が見つかりませんでした。キーワード、期間、言語条件を変えてください。")
        return

    filtered = apply_title_filter(df, title_filter_text, title_match_mode) if title_filter_enabled else df
    if title_filter_enabled:
        st.info(f"タイトルフィルター後: {len(filtered):,}件 / 取得記事: {raw_count:,}件")

    if filtered.empty:
        st.warning("タイトル条件に一致する記事がありませんでした。タイトル一致条件を緩めるか、タイトル内フィルター語を変えてください。")
        return

    ranked = add_ranking_columns(filtered)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("表示記事数", f"{len(ranked):,}")
    c2.metric("媒体数", f"{ranked['domain_norm'].nunique():,}")
    c3.metric("国数", f"{ranked['sourcecountry'].nunique():,}")
    c4.metric("言語数", f"{ranked['language'].nunique():,}")

    st.download_button(
        "CSVをダウンロード",
        data=dataframe_to_csv_bytes(ranked),
        file_name=f"gdelt_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )

    tab_cards, tab_table, tab_domains, tab_about = st.tabs(["記事カード", "一覧テーブル", "媒体集計", "メモ"])

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
            f"""
            #### この版で入っているもの
            - アプリ版: `{APP_VERSION}`
            - APIアクセス最小間隔: `0.00〜2.00秒 / 0.05秒刻み`
            - 入力変更だけではAPIへアクセスしない設計
            - 1時間のディスクキャッシュ
            - 429時のキャッシュフォールバック
            - タイトル限定フィルター

            #### 検索例
            - `Japan semiconductor`
            - `"Bank of Japan" yen`
            - `(Toyota OR Honda OR Nissan) EV`
            - `Japan -sourcelang:japanese`
            - `domain:reuters.com Japan`

            #### 注意
            - GDELTの検索結果はPV順・SNS拡散順ではありません。
            - 「簡易スコア」は、主要媒体ボーナス、直近性、同一媒体の記事数を足した独自の目安です。
            """
        )


if __name__ == "__main__":
    main()
