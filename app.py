import html
import math
import random
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from urllib.parse import unquote, urlparse

import pandas as pd
import requests
import streamlit as st


# ============================================================
# アプリ設定
# ============================================================

APP_VERSION = "2026-06-17-japan-specific-term-ranker"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "overseas-japan-term-ranker-streamlit/1.0"
CACHE_TTL_SECONDS = 60 * 30

# GDELT検索入口はこの2語だけ。
SEARCH_TERMS = ["Japan", "Japanese"]

# 102語。ランキング計算では先頭2語 Japan / Japanese を除外し、残り100語を使う。
# 方針: China / AI / inflation / stock market などの汎用語は除外し、
# 日本固有・日本文化・日本制度・日本企業・日本発IPに寄せる。
JAPAN_SPECIFIC_SEED_102 = [
    # 検索入口。ランキング計算からは除外。
    "Japan",
    "Japanese",

    # 経済・金融・制度・政治・安全保障
    "yen",
    "Bank of Japan",
    "BOJ",
    "Nikkei",
    "TOPIX",
    "Tokyo Stock Exchange",
    "JGB",
    "Japanese government bonds",
    "LDP",
    "Liberal Democratic Party",
    "Japanese Diet",
    "Self-Defense Forces",
    "SDF",
    "JSDF",
    "Okinawa bases",
    "Futenma",
    "Senkaku",
    "Northern Territories",
    "Fukushima",

    # 地名・観光地・地域名
    "Tokyo",
    "Osaka",
    "Kyoto",
    "Hokkaido",
    "Okinawa",
    "Mount Fuji",
    "Shibuya",
    "Shinjuku",
    "Akihabara",
    "Ginza",
    "Hiroshima",
    "Nagasaki",
    "Noto Peninsula",
    "Sapporo",
    "Fukuoka",
    "Nara",
    "Kobe",
    "Yokohama",

    # 交通・旅行・生活文化
    "Shinkansen",
    "bullet train",
    "JR Pass",
    "Japan Rail",
    "Suica",
    "onsen",
    "ryokan",
    "izakaya",
    "konbini",

    # 食文化
    "sushi",
    "ramen",
    "udon",
    "soba",
    "tempura",
    "wagyu",
    "matcha",
    "Japanese sake",
    "nihonshu",
    "shochu",
    "bento",
    "omakase",
    "kaiseki",
    "miso",
    "natto",

    # 伝統文化
    "kimono",
    "yukata",
    "geisha",
    "samurai",
    "ninja",
    "Shinto",
    "torii",
    "matsuri",
    "hanami",
    "sakura",
    "cherry blossoms",
    "kabuki",
    "noh",
    "sumo",

    # ポップカルチャー・スポーツ・人物
    "anime",
    "manga",
    "otaku",
    "cosplay",
    "VTuber",
    "J-pop",
    "idol",
    "seiyuu",
    "Studio Ghibli",
    "Pokemon",
    "Godzilla",
    "Gundam",
    "Hello Kitty",
    "One Piece",
    "Demon Slayer",
    "Dragon Ball",
    "Shohei Ohtani",
    "Ohtani",

    # 日本企業・ブランド
    "Toyota",
    "Honda",
    "Nissan",
    "Sony",
    "Nintendo",
    "PlayStation",
    "Nintendo Switch",
    "SoftBank",
    "Uniqlo",
    "MUJI",
    "Sanrio",
]

assert len(JAPAN_SPECIFIC_SEED_102) == 102, len(JAPAN_SPECIFIC_SEED_102)
RANKING_TERMS = JAPAN_SPECIFIC_SEED_102[2:]

MAJOR_MEDIA_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "cnn.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "ft.com",
    "bloomberg.com", "wsj.com", "cnbc.com", "forbes.com", "economist.com",
    "politico.com", "axios.com", "npr.org", "aljazeera.com", "dw.com",
    "france24.com", "lemonde.fr", "elpais.com", "scmp.com", "straitstimes.com",
    "abc.net.au", "theglobeandmail.com", "cbc.ca",
}

CATEGORY_TERMS = {
    "経済・金融・制度": {
        "yen", "bank of japan", "boj", "nikkei", "topix", "tokyo stock exchange", "jgb",
        "japanese government bonds", "ldp", "liberal democratic party", "japanese diet",
    },
    "政治・安全保障": {
        "self-defense forces", "sdf", "jsdf", "okinawa bases", "futenma", "senkaku",
        "northern territories", "fukushima",
    },
    "地名・観光地": {
        "tokyo", "osaka", "kyoto", "hokkaido", "okinawa", "mount fuji", "shibuya",
        "shinjuku", "akihabara", "ginza", "hiroshima", "nagasaki", "noto peninsula",
        "sapporo", "fukuoka", "nara", "kobe", "yokohama",
    },
    "交通・旅行・生活": {
        "shinkansen", "bullet train", "jr pass", "japan rail", "suica", "onsen", "ryokan",
        "izakaya", "konbini",
    },
    "食文化": {
        "sushi", "ramen", "udon", "soba", "tempura", "wagyu", "matcha", "japanese sake",
        "nihonshu", "shochu", "bento", "omakase", "kaiseki", "miso", "natto",
    },
    "伝統文化": {
        "kimono", "yukata", "geisha", "samurai", "ninja", "shinto", "torii", "matsuri",
        "hanami", "sakura", "cherry blossoms", "kabuki", "noh", "sumo",
    },
    "ポップカルチャー・スポーツ": {
        "anime", "manga", "otaku", "cosplay", "vtuber", "j-pop", "idol", "seiyuu",
        "studio ghibli", "pokemon", "godzilla", "gundam", "hello kitty", "one piece",
        "demon slayer", "dragon ball", "shohei ohtani", "ohtani",
    },
    "企業・ブランド": {
        "toyota", "honda", "nissan", "sony", "nintendo", "playstation", "nintendo switch",
        "softbank", "uniqlo", "muji", "sanrio",
    },
}


# ============================================================
# GDELT取得
# ============================================================

def build_gdelt_query() -> str:
    # GDELTは括弧をORグループにだけ使うのが安全。
    return "(Japan OR Japanese) -sourcecountry:japan"


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_gdelt_articles(query: str, timespan: str, maxrecords: int, sort_mode: str, retry_count: int) -> Tuple[List[dict], str]:
    """GDELT DOC 2.0 ArticleListを取得。エラー時は([], error_message)。"""
    if maxrecords <= 0:
        return [], "取得件数が0なのでGDELT取得をスキップしました。"

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "timespan": timespan,
        "maxrecords": int(maxrecords),
        "sort": sort_mode,
    }
    headers = {"User-Agent": USER_AGENT}

    last_error = ""
    for attempt in range(max(1, retry_count + 1)):
        try:
            resp = requests.get(GDELT_ENDPOINT, params=params, headers=headers, timeout=30)
            content_type = resp.headers.get("Content-Type", "")

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after and str(retry_after).isdigit():
                    wait_sec = min(float(retry_after), 90.0)
                else:
                    wait_sec = min(8.0 * (2 ** attempt) + random.random() * 2.0, 90.0)
                last_error = (
                    "HTTP 429 Too Many Requests: GDELTのレート制限に当たりました。"
                    f"retry_after={retry_after}, next_wait_sec={wait_sec:.1f}, query={query}"
                )
                if attempt < retry_count:
                    time.sleep(wait_sec)
                    continue
                return [], last_error

            if resp.status_code >= 400:
                body = resp.text[:500].replace("\n", " ")
                return [], f"HTTP {resp.status_code}: {body}"

            # GDELTは構文エラー時にstatus=200でtext/htmlを返すことがある。
            if "json" not in content_type.lower():
                body = resp.text[:500].replace("\n", " ")
                return [], (
                    "GDELTがJSON以外を返しました "
                    f"status={resp.status_code}, content_type={content_type}, body={body}"
                )

            data = resp.json()
            articles = data.get("articles", [])
            if not isinstance(articles, list):
                return [], "GDELTレスポンスのarticles形式が想定外です。"
            return articles, ""

        except requests.exceptions.RequestException as e:
            wait_sec = min(4.0 * (2 ** attempt) + random.random(), 60.0)
            last_error = f"RequestException: {type(e).__name__}: {e}"
            if attempt < retry_count:
                time.sleep(wait_sec)
                continue
            return [], last_error
        except ValueError as e:
            return [], f"JSON decode error: {e}"

    return [], last_error or "unknown error"


# ============================================================
# スコアリング
# ============================================================

def canonical_domain(article: dict) -> str:
    domain = str(article.get("domain", "") or "").lower().strip()
    if domain:
        return domain.replace("www.", "")
    url = str(article.get("url", "") or "")
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_major_media(domain: str) -> bool:
    d = (domain or "").lower().replace("www.", "")
    return any(d == m or d.endswith("." + m) for m in MAJOR_MEDIA_DOMAINS)


def normalize_text_for_match(text: str) -> str:
    text = html.unescape(unquote(str(text or ""))).lower()
    # ハイフン/スラッシュ/アンダースコア/ドットを語区切りとして扱う。
    text = re.sub(r"[\u2010-\u2015−–—/_.:;,+()\[\]{}|!?\"'`~@#$%^&*=<>]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_term_for_match(term: str) -> str:
    return normalize_text_for_match(term)


def build_metadata_text(article: dict) -> str:
    """タイトル・URL・GDELTメタデータを結合。本文全文は取得しない。"""
    keys = [
        "title",
        "url",
        "url_mobile",
        "domain",
        "language",
        "sourcecountry",
        "seendate",
        "socialimage",
    ]
    fields = [article.get(k, "") for k in keys]

    # その他のスカラーなGDELTメタデータも薄く含める。
    for k, v in article.items():
        if k in keys:
            continue
        if isinstance(v, (str, int, float)):
            fields.append(str(v))

    return normalize_text_for_match(" ".join(str(x) for x in fields if x))


@st.cache_data(show_spinner=False)
def compiled_term_patterns(terms: Tuple[str, ...]) -> Dict[str, re.Pattern]:
    patterns = {}
    for term in terms:
        norm = normalize_term_for_match(term)
        if not norm:
            continue
        # normalize済みテキストに対し、語境界つきでカウント。
        # 複数語フレーズもスペース区切りで一致。
        pattern = r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])"
        patterns[term] = re.compile(pattern, flags=re.IGNORECASE)
    return patterns


def score_article(article: dict, terms: List[str]) -> dict:
    text = build_metadata_text(article)
    patterns = compiled_term_patterns(tuple(terms))

    total_hits = 0
    matched_terms = []
    term_counts = {}

    for term, pattern in patterns.items():
        count = len(pattern.findall(text))
        if count > 0:
            total_hits += count
            matched_terms.append(term)
            term_counts[term] = count

    domain = canonical_domain(article)
    major = is_major_media(domain)

    # ユーザー指定の主ランキングは「出現回数」。
    # major_media等は同点時の補助にだけ使う。
    return {
        "score": int(total_hits),
        "unique_hits": int(len(matched_terms)),
        "matched_terms": matched_terms,
        "term_counts": term_counts,
        "domain": domain,
        "is_major_media": major,
    }


def detect_category(matched_terms: List[str]) -> str:
    if not matched_terms:
        return "未分類"
    lowered = {normalize_term_for_match(t) for t in matched_terms}
    scores = {}
    for category, terms in CATEGORY_TERMS.items():
        scores[category] = len(lowered & terms)
    best_category, best_score = max(scores.items(), key=lambda x: x[1])
    return best_category if best_score > 0 else "未分類"


def rank_articles(articles: List[dict], max_rank: int = 30) -> pd.DataFrame:
    rows = []
    seen_urls = set()

    for article in articles:
        url = str(article.get("url", "") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        s = score_article(article, RANKING_TERMS)
        if s["score"] <= 0:
            continue

        matched_terms = s["matched_terms"]
        term_counts = s["term_counts"]
        top_terms = sorted(term_counts.items(), key=lambda x: (-x[1], x[0].lower()))
        top_terms_text = ", ".join([f"{k}({v})" for k, v in top_terms[:12]])

        seendate = str(article.get("seendate", "") or "")
        rows.append({
            "score": s["score"],
            "unique_hits": s["unique_hits"],
            "category": detect_category(matched_terms),
            "matched_terms": top_terms_text,
            "title": str(article.get("title", "") or ""),
            "domain": s["domain"],
            "sourcecountry": str(article.get("sourcecountry", "") or ""),
            "language": str(article.get("language", "") or ""),
            "seendate": seendate,
            "is_major_media": s["is_major_media"],
            "url": url,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "rank", "score", "unique_hits", "category", "matched_terms", "title", "domain",
            "sourcecountry", "language", "seendate", "is_major_media", "url"
        ])

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["score", "unique_hits", "is_major_media", "seendate"],
        ascending=[False, False, False, False],
        kind="mergesort",
    ).head(max_rank).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


def summarize_terms(df: pd.DataFrame) -> pd.DataFrame:
    counter = {}
    if df.empty:
        return pd.DataFrame(columns=["term", "count"])
    for text in df["matched_terms"].fillna(""):
        for part in str(text).split(","):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"^(.*)\((\d+)\)$", part)
            if not m:
                continue
            term = m.group(1).strip()
            count = int(m.group(2))
            counter[term] = counter.get(term, 0) + count
    return pd.DataFrame(
        [{"term": k, "count": v} for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0].lower()))]
    )


# ============================================================
# Streamlit UI
# ============================================================

st.set_page_config(
    page_title="海外日本バズ検出ランキング",
    page_icon="🗞️",
    layout="wide",
)

st.title("海外日本バズ検出ランキング")
st.caption(
    "GDELTで Japan / Japanese を含む海外ニュースを1回だけ取得し、"
    "タイトル・URL・GDELTメタデータ中の日本特有100語ヒット数でランキング化します。"
)

with st.sidebar:
    st.header("検索設定")
    timespan_hours = st.slider(
        "対象期間（時間）",
        min_value=1,
        max_value=168,
        value=24,
        step=1,
        help="GDELTのtimespanに使います。24hなら直近24時間。",
    )
    maxrecords = st.slider(
        "GDELT取得件数",
        min_value=0,
        max_value=250,
        value=150,
        step=10,
        help="0にすると取得をスキップします。GDELT DOC APIのArticleListは通常250件程度までが扱いやすいです。",
    )
    ranking_max = st.slider(
        "ランキング最大数",
        min_value=1,
        max_value=30,
        value=30,
        step=1,
    )
    sort_mode = st.selectbox(
        "GDELT取得順",
        options=["hybridrel", "datedesc"],
        index=0,
        help="hybridrelは関連度と新しさの混合、datedescは新しい順です。",
    )
    access_interval = st.slider(
        "取得前の待機秒",
        min_value=0.0,
        max_value=10.0,
        value=0.0,
        step=0.1,
        help="1回取得だけなので通常0でOK。429が出る環境では少し上げてください。",
    )
    retry_count = st.slider(
        "429/通信エラー時のリトライ回数",
        min_value=0,
        max_value=3,
        value=1,
        step=1,
    )
    run_search = st.button("検索・ランキング作成", type="primary")

    st.divider()
    st.caption(f"APP_VERSION: {APP_VERSION}")

query = build_gdelt_query()
timespan = f"{timespan_hours}h"

st.subheader("検索クエリ")
st.code(query, language="text")

with st.expander("日本特有102語リストを見る"):
    st.write("ランキング計算では Japan / Japanese を除外し、残り100語だけをカウントします。")
    seed_df = pd.DataFrame({
        "index": range(1, len(JAPAN_SPECIFIC_SEED_102) + 1),
        "term": JAPAN_SPECIFIC_SEED_102,
        "used_for_ranking": [False, False] + [True] * 100,
    })
    st.dataframe(seed_df, use_container_width=True, hide_index=True)

if run_search:
    if access_interval > 0:
        time.sleep(access_interval)

    with st.spinner("GDELTから海外ニュースを取得しています..."):
        articles, error = fetch_gdelt_articles(
            query=query,
            timespan=timespan,
            maxrecords=maxrecords,
            sort_mode=sort_mode,
            retry_count=retry_count,
        )

    if error:
        st.warning(error)

    st.subheader("取得結果")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("GDELT取得記事数", len(articles))
    c2.metric("ランキング語数", len(RANKING_TERMS))
    c3.metric("ランキング最大数", ranking_max)
    c4.metric("対象期間", timespan)

    if articles:
        ranked_df = rank_articles(articles, max_rank=ranking_max)

        st.subheader("ランキング")
        if ranked_df.empty:
            st.info("取得記事はありましたが、日本特有100語にヒットした記事がありませんでした。取得件数や対象期間を増やしてください。")
        else:
            display_df = ranked_df.copy()
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn("url"),
                    "score": st.column_config.NumberColumn("score", help="日本特有100語の総出現回数"),
                    "unique_hits": st.column_config.NumberColumn("unique_hits", help="ヒットした語の種類数"),
                    "is_major_media": st.column_config.CheckboxColumn("major"),
                },
            )

            csv = ranked_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "ランキングCSVをダウンロード",
                data=csv,
                file_name="overseas_japan_term_ranking.csv",
                mime="text/csv",
            )

            st.subheader("ランキング上位内のヒット語集計")
            term_summary = summarize_terms(ranked_df)
            if not term_summary.empty:
                st.dataframe(term_summary.head(50), use_container_width=True, hide_index=True)

            st.subheader("上位記事カード")
            for _, row in ranked_df.head(10).iterrows():
                with st.container(border=True):
                    st.markdown(f"**#{int(row['rank'])}｜score {int(row['score'])}｜{row['category']}**")
                    st.markdown(f"[{row['title']}]({row['url']})")
                    st.caption(
                        f"{row['domain']} / {row['sourcecountry']} / {row['language']} / {row['seendate']}"
                    )
                    st.write(f"命中語: {row['matched_terms']}")
    else:
        st.info("記事が取得されませんでした。取得件数が0でないか、対象期間が短すぎないか確認してください。")
else:
    st.info("左サイドバーの『検索・ランキング作成』を押すと取得を開始します。")

st.divider()
st.caption(
    "データ出典: GDELT Project DOC 2.0 API。"
    "本アプリは記事本文全文を取得せず、GDELTが返すタイトル・URL・メタデータをもとに独自集計します。"
    "記事本文・画像・見出し等の権利は各配信元に帰属します。"
)
