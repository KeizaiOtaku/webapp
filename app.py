# -*- coding: utf-8 -*-
"""
海外注目度だけが高い日本ニュースランキング Streamlit app

- 無料・オープンな GDELT DOC 2.0 API のみを使用します。APIキー不要。
- Google News RSS / NewsAPI / AI API / LLM従量課金は使用しません。
- 50種類の一般固定ワード + 海外記事タイトルからのバズワード自動抽出で検索範囲を拡張します。
- 国内ニュースで注目されている話題は減点し、「海外で相対的に目立つ日本ニュース」を上位表示します。

実行:
    pip install -r requirements.txt
    streamlit run app_overseas_japan_news.py
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

import pandas as pd
import requests
import streamlit as st

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# -----------------------------------------------------------------------------
# 1. 50 fixed general keywords: no company names, no specific titles, no people.
# -----------------------------------------------------------------------------
FIXED_KEYWORDS: List[Dict[str, str]] = [
    {"en": "Japan", "jp": "日本", "category": "general"},
    {"en": "Japanese", "jp": "日本人", "category": "general"},
    {"en": "Tokyo", "jp": "東京", "category": "general"},
    {"en": "Kyoto", "jp": "京都", "category": "travel_culture"},
    {"en": "Osaka", "jp": "大阪", "category": "general"},
    {"en": "Hokkaido", "jp": "北海道", "category": "travel_culture"},
    {"en": "Okinawa", "jp": "沖縄", "category": "travel_culture"},
    {"en": "yen", "jp": "円", "category": "economy"},
    {"en": "Bank of Japan", "jp": "日銀", "category": "economy"},
    {"en": "Japanese economy", "jp": "日本経済", "category": "economy"},
    {"en": "inflation", "jp": "インフレ", "category": "economy"},
    {"en": "interest rates", "jp": "金利", "category": "economy"},
    {"en": "stock market", "jp": "株式市場", "category": "economy"},
    {"en": "Nikkei", "jp": "日経平均", "category": "economy"},
    {"en": "tourism", "jp": "観光", "category": "travel_culture"},
    {"en": "travel", "jp": "旅行", "category": "travel_culture"},
    {"en": "overtourism", "jp": "オーバーツーリズム", "category": "travel_culture"},
    {"en": "culture", "jp": "文化", "category": "travel_culture"},
    {"en": "tradition", "jp": "伝統", "category": "travel_culture"},
    {"en": "anime", "jp": "アニメ", "category": "entertainment"},
    {"en": "manga", "jp": "漫画", "category": "entertainment"},
    {"en": "video games", "jp": "ゲーム", "category": "entertainment"},
    {"en": "J-pop", "jp": "J-POP", "category": "entertainment"},
    {"en": "film", "jp": "映画", "category": "entertainment"},
    {"en": "drama", "jp": "ドラマ", "category": "entertainment"},
    {"en": "celebrity", "jp": "芸能", "category": "entertainment"},
    {"en": "music", "jp": "音楽", "category": "entertainment"},
    {"en": "fashion", "jp": "ファッション", "category": "entertainment"},
    {"en": "food", "jp": "食", "category": "travel_culture"},
    {"en": "sushi", "jp": "寿司", "category": "travel_culture"},
    {"en": "ramen", "jp": "ラーメン", "category": "travel_culture"},
    {"en": "matcha", "jp": "抹茶", "category": "travel_culture"},
    {"en": "sake", "jp": "日本酒", "category": "travel_culture"},
    {"en": "onsen", "jp": "温泉", "category": "travel_culture"},
    {"en": "shrine", "jp": "神社", "category": "travel_culture"},
    {"en": "temple", "jp": "寺", "category": "travel_culture"},
    {"en": "samurai", "jp": "侍", "category": "travel_culture"},
    {"en": "ninja", "jp": "忍者", "category": "travel_culture"},
    {"en": "earthquake", "jp": "地震", "category": "disaster"},
    {"en": "typhoon", "jp": "台風", "category": "disaster"},
    {"en": "volcano", "jp": "火山", "category": "disaster"},
    {"en": "heatwave", "jp": "猛暑", "category": "disaster"},
    {"en": "politics", "jp": "政治", "category": "politics"},
    {"en": "election", "jp": "選挙", "category": "politics"},
    {"en": "prime minister", "jp": "首相", "category": "politics"},
    {"en": "defense", "jp": "防衛", "category": "politics"},
    {"en": "military", "jp": "軍事", "category": "politics"},
    {"en": "demographics", "jp": "人口", "category": "society"},
    {"en": "aging population", "jp": "高齢化", "category": "society"},
    {"en": "birth rate", "jp": "出生率", "category": "society"},
]

STRONG_JAPAN_TERMS = {
    "Japan", "Japanese", "Tokyo", "Kyoto", "Osaka", "Hokkaido", "Okinawa", "yen",
    "Bank of Japan", "Japanese economy", "Nikkei", "anime", "manga", "J-pop",
    "sushi", "ramen", "matcha", "sake", "onsen", "samurai", "ninja",
}

CATEGORY_DOMESTIC_PENALTY = {
    "entertainment": 0.30,
    "travel_culture": 0.40,
    "economy": 0.65,
    "politics": 0.75,
    "disaster": 0.70,
    "society": 0.60,
    "general": 0.55,
    "buzz": 0.50,
}

MAJOR_MEDIA_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "cnn.com", "nytimes.com",
    "theguardian.com", "ft.com", "bloomberg.com", "wsj.com", "washingtonpost.com",
    "politico.com", "dw.com", "france24.com", "aljazeera.com", "abc.net.au",
    "cbc.ca", "scmp.com", "straitstimes.com", "channelnewsasia.com", "rfi.fr",
    "lemonde.fr", "elpais.com", "spiegel.de", "economist.com", "forbes.com",
    "hollywoodreporter.com", "variety.com", "deadline.com", "ign.com", "gamespot.com",
}

COMMON_TERMS = {
    "japan", "japanese", "tokyo", "kyoto", "osaka", "hokkaido", "okinawa", "news",
    "new", "latest", "update", "updates", "world", "today", "report", "reports",
    "says", "said", "after", "before", "over", "under", "from", "into", "with",
    "without", "about", "could", "would", "should", "will", "may", "might", "first",
    "last", "more", "most", "best", "top", "video", "live", "watch", "photos",
    "analysis", "explained", "guide", "review", "opinion", "press", "agency",
    "reuters", "associated press", "ap news", "bbc", "cnn", "guardian", "bloomberg",
}

# -----------------------------------------------------------------------------
# 2. Utilities
# -----------------------------------------------------------------------------

def normalize_domain(url_or_domain: str) -> str:
    if not url_or_domain:
        return ""
    value = str(url_or_domain).strip().lower()
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc
    value = value.replace("www.", "")
    return value.split(":")[0]


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    text = str(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_gdelt_date(value: Any) -> Optional[pd.Timestamp]:
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        # Typical: 20260617123000 or 20260617123000.000
        s2 = re.sub(r"\D", "", s)[:14]
        if len(s2) >= 8:
            fmt = "%Y%m%d%H%M%S" if len(s2) >= 14 else "%Y%m%d"
            return pd.to_datetime(datetime.strptime(s2[:14] if len(s2) >= 14 else s2[:8], fmt), utc=True)
    except Exception:
        pass
    try:
        return pd.to_datetime(s, utc=True, errors="coerce")
    except Exception:
        return None


def is_japan_source(sourcecountry: Any, domain: str = "") -> bool:
    v = str(sourcecountry or "").strip().lower()
    if v in {"japan", "ja", "jp", "jpn"}:
        return True
    # Fallback only when metadata is missing. Keep conservative.
    d = normalize_domain(domain)
    return d.endswith(".jp") or d.endswith("co.jp") or d.endswith("or.jp") or d.endswith("ne.jp")


def category_for_term(term: str) -> str:
    t = term.lower()
    for item in FIXED_KEYWORDS:
        if item["en"].lower() == t or item["jp"].lower() == t:
            return item["category"]
    return "buzz"


def quote_if_needed(term: str) -> str:
    term = term.strip()
    if not term:
        return term
    if " " in term or "-" in term:
        return f'"{term}"'
    return term


def build_fixed_query(term: str) -> str:
    """Make broad Japan-related query without relying on sourcecountry filters."""
    if term in STRONG_JAPAN_TERMS:
        return quote_if_needed(term)
    return f'({quote_if_needed(term)} AND (Japan OR Japanese OR Tokyo))'


def build_buzz_query(term: str) -> str:
    term = term.strip()
    return f'({quote_if_needed(term)} AND (Japan OR Japanese OR Tokyo OR anime OR manga OR yen))'


def title_tokens(title: str) -> set:
    t = title.lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^a-z0-9一-龯ぁ-んァ-ヶー]+", " ", t)
    toks = {x for x in t.split() if len(x) >= 3 and x not in COMMON_TERMS}
    return toks


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))

# -----------------------------------------------------------------------------
# 3. GDELT fetcher
# -----------------------------------------------------------------------------

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_gdelt(query: str, timespan: str, maxrecords: int, sort: str = "datedesc") -> pd.DataFrame:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": int(max(1, min(maxrecords, 250))),
        "timespan": timespan,
        "sort": sort,
    }
    url = f"{GDELT_ENDPOINT}?{urlencode(params)}"
    headers = {"User-Agent": "overseas-japan-news-ranker/1.0; contact=your-email@example.com"}
    try:
        resp = requests.get(url, timeout=30, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        return pd.DataFrame([{"_error": str(e), "_query": query}])

    arts = payload.get("articles", []) if isinstance(payload, dict) else []
    rows = []
    for a in arts:
        if not isinstance(a, dict):
            continue
        rows.append({
            "title": clean_text(a.get("title")),
            "url": clean_text(a.get("url")),
            "domain": normalize_domain(a.get("domain") or a.get("url")),
            "language": clean_text(a.get("language")),
            "sourcecountry": clean_text(a.get("sourcecountry")),
            "seendate": clean_text(a.get("seendate")),
            "socialimage": clean_text(a.get("socialimage")),
            "query": query,
        })
    return pd.DataFrame(rows)


def fetch_many_queries(
    queries: List[str],
    timespan: str,
    maxrecords: int,
    max_calls: int,
    sleep_sec: float,
    progress_label: str,
) -> pd.DataFrame:
    frames = []
    unique_queries = []
    for q in queries:
        if q not in unique_queries:
            unique_queries.append(q)
    unique_queries = unique_queries[:max_calls]

    progress = st.progress(0, text=progress_label)
    total = max(1, len(unique_queries))
    for i, q in enumerate(unique_queries, start=1):
        frames.append(fetch_gdelt(q, timespan, maxrecords))
        progress.progress(i / total, text=f"{progress_label}: {i}/{total}")
        if sleep_sec > 0 and i < total:
            time.sleep(sleep_sec)
    progress.empty()

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if "_error" in df.columns:
        errors = df[df["_error"].notna()] if "_error" in df else pd.DataFrame()
        if not errors.empty:
            st.warning(f"一部のGDELT取得でエラー: {errors['_error'].dropna().head(3).tolist()}")
        df = df[df.get("url", pd.Series(dtype=str)).notna()].copy()
    if df.empty:
        return df
    df["title"] = df["title"].fillna("").astype(str)
    df["url"] = df["url"].fillna("").astype(str)
    df = df[df["url"].str.len() > 0]
    df = df.drop_duplicates(subset=["url"]).copy()
    df["domain"] = df["domain"].map(normalize_domain)
    df["seen_ts"] = df["seendate"].map(parse_gdelt_date)
    df["is_domestic"] = df.apply(lambda r: is_japan_source(r.get("sourcecountry"), r.get("domain")), axis=1)
    df["is_overseas"] = ~df["is_domestic"]
    df["major_media"] = df["domain"].isin(MAJOR_MEDIA_DOMAINS)
    return df

# -----------------------------------------------------------------------------
# 4. Buzzword extraction
# -----------------------------------------------------------------------------

def extract_buzzwords(df: pd.DataFrame, top_n: int = 25) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["term", "count", "domain_count", "score"])

    overseas = df[df["is_overseas"]].copy()
    counts: Counter[str] = Counter()
    domains_by_term: Dict[str, set] = defaultdict(set)

    fixed_lower = {x["en"].lower() for x in FIXED_KEYWORDS} | {x["jp"].lower() for x in FIXED_KEYWORDS}

    for _, row in overseas.iterrows():
        title = clean_text(row.get("title"))
        domain = normalize_domain(row.get("domain"))
        if not title:
            continue

        candidates: List[str] = []

        # Capitalized phrases: useful for names, titles, events, places.
        candidates += re.findall(
            r"\b(?:[A-Z][A-Za-z0-9&'’.-]{2,}\s+){0,4}[A-Z][A-Za-z0-9&'’.-]{2,}\b",
            title,
        )
        # ALL CAPS / mixed product-like terms, but avoid single-letter noise.
        candidates += re.findall(r"\b[A-Z][A-Z0-9&.-]{2,}\b", title)
        # Japanese/Korean/Chinese chunks if they appear in title.
        candidates += re.findall(r"[一-龯ぁ-んァ-ヶー]{3,}", title)

        for cand in candidates:
            cand = re.sub(r"\s+", " ", cand).strip(" -–—:;,.!?()[]{}'\"")
            low = cand.lower()
            if len(cand) < 3 or len(cand) > 70:
                continue
            if low in COMMON_TERMS or low in fixed_lower:
                continue
            if any(low == c or low.startswith(c + " ") for c in COMMON_TERMS):
                continue
            # Too generic: all words common/generic.
            words = re.findall(r"[A-Za-z0-9一-龯ぁ-んァ-ヶー]+", low)
            if not words or all(w in COMMON_TERMS for w in words):
                continue
            # Avoid pure media domain names.
            if domain and low.replace(" ", "") in domain.replace(".", ""):
                continue
            counts[cand] += 1
            domains_by_term[cand].add(domain)

    rows = []
    for term, cnt in counts.items():
        domain_count = len(domains_by_term[term])
        if cnt < 2 and domain_count < 2:
            continue
        score = cnt + 1.5 * domain_count
        rows.append({"term": term, "count": cnt, "domain_count": domain_count, "score": score})

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["score", "domain_count", "count"], ascending=False).head(top_n).reset_index(drop=True)
    return out

# -----------------------------------------------------------------------------
# 5. Clustering and scoring
# -----------------------------------------------------------------------------

def cluster_articles(df: pd.DataFrame, sim_threshold: float = 0.28) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    df = df.copy().reset_index(drop=True)
    df["tokens"] = df["title"].map(title_tokens)
    clusters: List[Dict[str, Any]] = []
    cluster_ids: List[int] = []

    # More recent and title-rich articles first.
    df = df.sort_values(["seen_ts", "title"], ascending=[False, True], na_position="last").reset_index(drop=True)

    for idx, row in df.iterrows():
        toks = row["tokens"]
        best_id = None
        best_score = 0.0
        for cid, c in enumerate(clusters):
            s = jaccard(toks, c["tokens"])
            if s > best_score:
                best_score = s
                best_id = cid
        if best_id is not None and best_score >= sim_threshold:
            cluster_ids.append(best_id)
            clusters[best_id]["tokens"] |= toks
        else:
            cluster_ids.append(len(clusters))
            clusters.append({"tokens": set(toks)})

    df["cluster_id"] = cluster_ids
    return df


def infer_cluster_category(group: pd.DataFrame) -> str:
    text = " ".join((group["query"].fillna("") + " " + group["title"].fillna("")).tolist()).lower()
    category_score = Counter()
    for item in FIXED_KEYWORDS:
        en = item["en"].lower()
        jp = item["jp"].lower()
        if en in text or jp in text:
            category_score[item["category"]] += 1
    if not category_score:
        return "buzz"
    return category_score.most_common(1)[0][0]


def compute_rankings(df: pd.DataFrame, min_overseas_articles: int, min_overseas_ratio: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    clustered = cluster_articles(df)
    rows = []

    for cid, g in clustered.groupby("cluster_id"):
        overseas = g[g["is_overseas"]]
        domestic = g[g["is_domestic"]]
        if overseas.empty:
            continue

        overseas_articles = int(overseas["url"].nunique())
        domestic_articles = int(domestic["url"].nunique())
        if overseas_articles < min_overseas_articles:
            continue

        overseas_domains = int(overseas["domain"].nunique())
        domestic_domains = int(domestic["domain"].nunique()) if not domestic.empty else 0
        overseas_countries = int(overseas["sourcecountry"].replace("", pd.NA).dropna().nunique())
        major_count = int(overseas["major_media"].sum())
        category = infer_cluster_category(g)
        penalty_coef = CATEGORY_DOMESTIC_PENALTY.get(category, 0.55)

        # Recency: latest article gets modest boost.
        latest = overseas["seen_ts"].dropna().max()
        recency_bonus = 0.0
        if pd.notna(latest):
            hours_old = max(0.0, (pd.Timestamp.now(tz="UTC") - latest).total_seconds() / 3600)
            recency_bonus = max(0.0, 3.0 - hours_old / 12.0)

        overseas_score = (
            5.0 * math.log1p(overseas_articles)
            + 2.2 * overseas_domains
            + 2.0 * overseas_countries
            + 2.5 * major_count
            + recency_bonus
        )
        domestic_penalty = (
            5.0 * math.log1p(domestic_articles)
            + 1.6 * domestic_domains
        )
        final_score = overseas_score - penalty_coef * domestic_penalty
        overseas_ratio = overseas_articles / max(1, domestic_articles)

        # Emphasize “海外だけ高い”; keep broad but remove obviously domestic-heavy clusters.
        if overseas_ratio < min_overseas_ratio and domestic_articles >= overseas_articles:
            continue

        rep = overseas.sort_values(["major_media", "seen_ts"], ascending=[False, False], na_position="last").iloc[0]
        example_titles = overseas["title"].dropna().drop_duplicates().head(5).tolist()
        example_links = overseas[["title", "domain", "sourcecountry", "url", "seendate"]].drop_duplicates("url").head(10).to_dict("records")

        rows.append({
            "rank_title": rep["title"],
            "category": category,
            "final_score": round(final_score, 2),
            "overseas_score": round(overseas_score, 2),
            "domestic_penalty": round(penalty_coef * domestic_penalty, 2),
            "domestic_penalty_coef": penalty_coef,
            "overseas_articles": overseas_articles,
            "domestic_articles": domestic_articles,
            "overseas_ratio": round(overseas_ratio, 2),
            "overseas_domains": overseas_domains,
            "overseas_countries": overseas_countries,
            "major_media_articles": major_count,
            "latest_seen": str(latest) if pd.notna(latest) else "",
            "representative_domain": rep["domain"],
            "representative_country": rep["sourcecountry"],
            "representative_url": rep["url"],
            "example_titles": example_titles,
            "example_links": example_links,
            "cluster_id": cid,
        })

    ranking = pd.DataFrame(rows)
    if not ranking.empty:
        ranking = ranking.sort_values(["final_score", "overseas_articles", "overseas_domains"], ascending=False).reset_index(drop=True)
        ranking.insert(0, "rank", range(1, len(ranking) + 1))
    return ranking, clustered.drop(columns=["tokens"], errors="ignore")

# -----------------------------------------------------------------------------
# 6. Streamlit UI
# -----------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="海外注目の日本ニュースランキング", layout="wide")
    st.title("海外注目度だけが高い日本ニュースランキング")
    st.caption("50固定ワード + バズワード自動抽出 / GDELTのみ / AI従量課金なし")

    with st.sidebar:
        st.header("取得設定")
        hours = st.selectbox("対象期間", [6, 12, 24, 48, 72, 168], index=2, format_func=lambda x: f"直近{x}時間")
        maxrecords = st.slider("1クエリあたり最大記事数", 20, 250, 120, 10)
        max_fixed_calls = st.slider("固定ワード検索の最大API呼び出し", 20, 100, 70, 5)
        use_jp_queries = st.checkbox("国内減点補強用に日本語ワードも検索", value=True)
        buzz_top_n = st.slider("抽出するバズワード数", 5, 50, 25, 5)
        use_buzz_search = st.checkbox("抽出バズワードで追加検索", value=True)
        max_buzz_calls = st.slider("バズワード追加検索の最大API呼び出し", 0, 50, 20, 5)
        min_overseas_articles = st.slider("最低海外記事数", 1, 10, 2, 1)
        min_overseas_ratio = st.slider("海外/国内 最低比率", 0.0, 10.0, 2.0, 0.5)
        sleep_sec = st.slider("API呼び出し間隔 秒", 0.0, 2.0, 0.15, 0.05)
        run = st.button("ニュースを収集・ランキング化", type="primary")

    st.info(
        "このアプリは記事本文を転載せず、GDELTが返す見出し・URL・媒体・国などのメタデータをランキング化します。"
        "公開運用時は各ニュース媒体の本文や画像の再利用を避け、元記事リンクへの誘導に留めるのが安全です。"
    )

    fixed_table = pd.DataFrame(FIXED_KEYWORDS)
    with st.expander("固定ワード50種類を見る"):
        st.dataframe(fixed_table, use_container_width=True, hide_index=True)

    if not run:
        st.stop()

    timespan = f"{hours}h"
    fixed_queries: List[str] = []
    for item in FIXED_KEYWORDS:
        fixed_queries.append(build_fixed_query(item["en"]))
        if use_jp_queries:
            fixed_queries.append(item["jp"])

    df_fixed = fetch_many_queries(
        fixed_queries,
        timespan=timespan,
        maxrecords=maxrecords,
        max_calls=max_fixed_calls,
        sleep_sec=sleep_sec,
        progress_label="固定ワード検索中",
    )

    if df_fixed.empty:
        st.error("記事を取得できませんでした。対象期間を広げるか、API呼び出し数を増やしてください。")
        st.stop()

    buzz_df = extract_buzzwords(df_fixed, top_n=buzz_top_n)

    df_all = df_fixed.copy()
    if use_buzz_search and not buzz_df.empty and max_buzz_calls > 0:
        buzz_queries = [build_buzz_query(t) for t in buzz_df["term"].head(max_buzz_calls).tolist()]
        df_buzz = fetch_many_queries(
            buzz_queries,
            timespan=timespan,
            maxrecords=maxrecords,
            max_calls=max_buzz_calls,
            sleep_sec=sleep_sec,
            progress_label="バズワード追加検索中",
        )
        if not df_buzz.empty:
            df_all = pd.concat([df_all, df_buzz], ignore_index=True).drop_duplicates(subset=["url"])
            df_all["seen_ts"] = df_all["seendate"].map(parse_gdelt_date)
            df_all["is_domestic"] = df_all.apply(lambda r: is_japan_source(r.get("sourcecountry"), r.get("domain")), axis=1)
            df_all["is_overseas"] = ~df_all["is_domestic"]
            df_all["major_media"] = df_all["domain"].isin(MAJOR_MEDIA_DOMAINS)

    ranking, article_df = compute_rankings(
        df_all,
        min_overseas_articles=min_overseas_articles,
        min_overseas_ratio=min_overseas_ratio,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("取得記事数", f"{len(df_all):,}")
    c2.metric("海外記事数", f"{int(df_all['is_overseas'].sum()):,}")
    c3.metric("国内記事数", f"{int(df_all['is_domestic'].sum()):,}")
    c4.metric("ユニーク媒体数", f"{df_all['domain'].nunique():,}")

    tab1, tab2, tab3, tab4 = st.tabs(["ランキング", "バズワード", "全記事", "CSVダウンロード"])

    with tab1:
        if ranking.empty:
            st.warning("条件を満たすランキング候補がありません。対象期間、最低海外記事数、海外/国内比率を緩めてください。")
        else:
            st.subheader("海外だけで相対的に目立つ日本ニュース")
            display_cols = [
                "rank", "rank_title", "category", "final_score", "overseas_articles",
                "domestic_articles", "overseas_ratio", "overseas_domains", "overseas_countries",
                "major_media_articles", "representative_domain", "representative_country", "representative_url",
            ]
            st.dataframe(ranking[display_cols], use_container_width=True, hide_index=True)

            for _, row in ranking.head(20).iterrows():
                with st.expander(f"#{int(row['rank'])} {row['rank_title']}  / score={row['final_score']}"):
                    st.write(
                        f"カテゴリ: **{row['category']}** / 海外記事: **{row['overseas_articles']}** / "
                        f"国内記事: **{row['domestic_articles']}** / 海外/国内比: **{row['overseas_ratio']}** / "
                        f"海外媒体: **{row['overseas_domains']}** / 海外国数: **{row['overseas_countries']}**"
                    )
                    st.write("代表・関連リンク:")
                    for link in row["example_links"]:
                        title = clean_text(link.get("title")) or "article"
                        domain = clean_text(link.get("domain"))
                        country = clean_text(link.get("sourcecountry"))
                        url = clean_text(link.get("url"))
                        st.markdown(f"- [{title}]({url})  — `{domain}` / `{country}`")

    with tab2:
        st.subheader("海外記事タイトルから抽出したバズワード候補")
        if buzz_df.empty:
            st.write("バズワード候補は見つかりませんでした。")
        else:
            st.dataframe(buzz_df, use_container_width=True, hide_index=True)

    with tab3:
        show_cols = ["title", "domain", "sourcecountry", "language", "is_overseas", "is_domestic", "seendate", "query", "url"]
        st.dataframe(df_all[show_cols], use_container_width=True, hide_index=True)

    with tab4:
        st.download_button(
            "ランキングCSVをダウンロード",
            data=ranking.drop(columns=["example_titles", "example_links"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
            file_name="overseas_japan_news_ranking.csv",
            mime="text/csv",
        )
        st.download_button(
            "全記事CSVをダウンロード",
            data=df_all.to_csv(index=False).encode("utf-8-sig"),
            file_name="overseas_japan_news_articles.csv",
            mime="text/csv",
        )
        st.download_button(
            "バズワードCSVをダウンロード",
            data=buzz_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="overseas_japan_news_buzzwords.csv",
            mime="text/csv",
        )

    with st.expander("スコア式"):
        st.code(
            """
海外スコア = 5*log(1+海外記事数) + 2.2*海外媒体数 + 2.0*海外国数 + 2.5*大手媒体記事数 + 新着ボーナス
国内減点 = カテゴリ別係数 * (5*log(1+国内記事数) + 1.6*国内媒体数)
最終スコア = 海外スコア - 国内減点

カテゴリ別の国内減点係数:
- entertainment: 0.30  # エンタメは国内起点で海外波及しやすいので弱め
- travel_culture: 0.40
- economy: 0.65
- politics: 0.75
- disaster: 0.70
- society: 0.60
- general: 0.55
- buzz: 0.50
            """.strip(),
            language="text",
        )


if __name__ == "__main__":
    main()
