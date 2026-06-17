import math
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st


# ============================================================
# 基本設定
# ============================================================

APP_VERSION = "2026-06-17-rate-limit-safe"

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

CACHE_TTL_SECONDS = 60 * 30  # 30分キャッシュ

DEFAULT_TIMESPAN = "24h"
DEFAULT_MAXRECORDS_FIXED = 250
DEFAULT_MAXRECORDS_BUZZ = 50

USER_AGENT = "overseas-japan-news-streamlit/1.0"

# 企業名・特定作品名・個人名を含まない固定50語
FIXED_KEYWORDS_50 = [
    "Japan",
    "Japanese",
    "Tokyo",
    "Kyoto",
    "Osaka",
    "Hokkaido",
    "Okinawa",
    "yen",
    "Bank of Japan",
    "Japanese economy",
    "inflation",
    "interest rates",
    "stock market",
    "Nikkei",
    "tourism",
    "travel",
    "overtourism",
    "culture",
    "tradition",
    "anime",
    "manga",
    "video games",
    "J-pop",
    "film",
    "drama",
    "celebrity",
    "music",
    "fashion",
    "food",
    "sushi",
    "ramen",
    "matcha",
    "sake",
    "onsen",
    "shrine",
    "temple",
    "samurai",
    "ninja",
    "earthquake",
    "typhoon",
    "volcano",
    "heatwave",
    "politics",
    "election",
    "prime minister",
    "defense",
    "military",
    "demographics",
    "aging population",
    "birth rate",
]

FIXED_KEYWORDS_JA_50 = [
    "日本",
    "日本人",
    "東京",
    "京都",
    "大阪",
    "北海道",
    "沖縄",
    "円",
    "日銀",
    "日本経済",
    "インフレ",
    "金利",
    "株式市場",
    "日経平均",
    "観光",
    "旅行",
    "オーバーツーリズム",
    "文化",
    "伝統",
    "アニメ",
    "漫画",
    "ゲーム",
    "J-POP",
    "映画",
    "ドラマ",
    "芸能",
    "音楽",
    "ファッション",
    "食",
    "寿司",
    "ラーメン",
    "抹茶",
    "日本酒",
    "温泉",
    "神社",
    "寺",
    "侍",
    "忍者",
    "地震",
    "台風",
    "火山",
    "猛暑",
    "政治",
    "選挙",
    "首相",
    "防衛",
    "軍事",
    "人口",
    "高齢化",
    "出生率",
]

# 単独で日本関連性が強い語
STANDALONE_TERMS = [
    "Japan",
    "Japanese",
    "Tokyo",
    "Kyoto",
    "Osaka",
    "Hokkaido",
    "Okinawa",
    "yen",
    "Bank of Japan",
    "Nikkei",
    "anime",
    "manga",
    "J-pop",
    "sushi",
    "ramen",
    "matcha",
    "sake",
    "onsen",
    "shrine",
    "temple",
    "samurai",
    "ninja",
]

# Japan/Japanese/Tokyoなどとセットにする語
ANCHORED_TERMS = [
    "economy",
    "inflation",
    "interest rates",
    "stock market",
    "tourism",
    "travel",
    "overtourism",
    "culture",
    "tradition",
    "video games",
    "film",
    "drama",
    "celebrity",
    "music",
    "fashion",
    "food",
    "earthquake",
    "typhoon",
    "volcano",
    "heatwave",
    "politics",
    "election",
    "prime minister",
    "defense",
    "military",
    "demographics",
    "aging population",
    "birth rate",
]

MAJOR_MEDIA_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "cnn.com",
    "nytimes.com",
    "washingtonpost.com",
    "theguardian.com",
    "ft.com",
    "bloomberg.com",
    "wsj.com",
    "cnbc.com",
    "forbes.com",
    "economist.com",
    "politico.com",
    "axios.com",
    "npr.org",
    "aljazeera.com",
    "dw.com",
    "france24.com",
    "lemonde.fr",
    "elpais.com",
    "scmp.com",
    "straitstimes.com",
    "abc.net.au",
    "theglobeandmail.com",
    "cbc.ca",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "with", "without",
    "for", "from", "into", "onto", "over", "under", "after", "before", "about",
    "this", "that", "these", "those", "there", "their", "they", "them", "its",
    "his", "her", "she", "him", "you", "your", "our", "ours", "who", "what",
    "when", "where", "why", "how", "new", "news", "says", "said", "say",
    "report", "reports", "reported", "update", "live", "latest", "world",
    "global", "international", "breaking", "watch", "video", "photos",
    "photo", "analysis", "opinion", "explained", "could", "would", "should",
    "may", "might", "will", "can", "one", "two", "first", "last",
    "japan", "japanese", "tokyo", "kyoto", "osaka", "hokkaido", "okinawa",
}

CATEGORY_KEYWORDS = {
    "エンタメ・文化": {
        "anime", "manga", "film", "movie", "drama", "celebrity", "music",
        "fashion", "j-pop", "game", "games", "video", "culture", "tradition",
        "samurai", "ninja", "shrine", "temple", "food", "sushi", "ramen",
        "matcha", "sake", "onsen",
    },
    "経済・金融": {
        "yen", "boj", "bank", "economy", "inflation", "rates", "interest",
        "stock", "market", "nikkei", "bond", "currency", "deflation",
    },
    "政治・外交・防衛": {
        "politics", "election", "prime", "minister", "defense", "military",
        "security", "diplomacy", "china", "korea", "taiwan", "government",
    },
    "災害・気象": {
        "earthquake", "typhoon", "volcano", "heatwave", "flood", "tsunami",
        "weather", "disaster",
    },
    "観光・社会": {
        "tourism", "travel", "overtourism", "tourist", "demographics",
        "aging", "birth", "population", "society",
    },
}


# ============================================================
# GDELTクエリ生成
# ============================================================

def quote_term(term: str) -> str:
    term = term.strip()
    if " " in term or "-" in term:
        return f'"{term}"'
    return term


def make_or_query(terms: List[str]) -> str:
    return " OR ".join(quote_term(t) for t in terms if t.strip())


def build_base_query_en() -> str:
    standalone = make_or_query(STANDALONE_TERMS)
    anchored = make_or_query(ANCHORED_TERMS)
    anchors = '(Japan OR Japanese OR Tokyo OR Kyoto OR Osaka)'
    return f'(({standalone}) OR ({anchors} AND ({anchored})))'


def build_base_query_ja() -> str:
    return f'({make_or_query(FIXED_KEYWORDS_JA_50)})'


def build_overseas_query() -> str:
    base_en = build_base_query_en()
    return f'({base_en}) -sourcecountry:japan'


def build_domestic_query(include_japanese_terms: bool = True) -> str:
    base_en = build_base_query_en()
    if include_japanese_terms:
        base_ja = build_base_query_ja()
        return f'(({base_en}) OR ({base_ja})) sourcecountry:japan'
    return f'({base_en}) sourcecountry:japan'


def sanitize_buzzword_for_query(word: str) -> str:
    word = word.strip()
    word = re.sub(r'["“”]', "", word)
    word = re.sub(r"[:(){}\[\]]", " ", word)
    word = re.sub(r"\s+", " ", word).strip()
    return word


def build_buzz_query(word: str, domestic: bool, include_japanese_anchor: bool = False) -> str:
    word = sanitize_buzzword_for_query(word)
    if not word:
        return ""

    if " " in word:
        w = f'"{word}"'
    else:
        w = word

    if domestic:
        if include_japanese_anchor:
            return f'({w}) sourcecountry:japan'
        return f'({w}) sourcecountry:japan'

    return f'({w}) AND (Japan OR Japanese OR Tokyo OR Kyoto OR Osaka) -sourcecountry:japan'


# ============================================================
# GDELT取得
# ============================================================

def gdelt_request(
    query: str,
    timespan: str = DEFAULT_TIMESPAN,
    maxrecords: int = DEFAULT_MAXRECORDS_FIXED,
    retries: int = 5,
) -> List[Dict]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": int(maxrecords),
        "timespan": timespan,
        "sort": "datedesc",
    }

    last_error = None

    for attempt in range(retries):
        try:
            response = requests.get(
                GDELT_ENDPOINT,
                params=params,
                timeout=30,
                headers={"User-Agent": USER_AGENT},
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait_sec = int(retry_after)
                else:
                    wait_sec = min(75, 3 * (2 ** attempt)) + random.uniform(0, 3)

                time.sleep(wait_sec)
                continue

            response.raise_for_status()
            data = response.json()
            return data.get("articles", []) or []

        except Exception as e:
            last_error = e
            wait_sec = min(60, 2 * (2 ** attempt)) + random.uniform(0, 2)
            time.sleep(wait_sec)

    raise RuntimeError(f"GDELT取得失敗: {last_error}")


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_gdelt_cached(
    query: str,
    timespan: str,
    maxrecords: int,
) -> Tuple[List[Dict], str]:
    try:
        articles = gdelt_request(
            query=query,
            timespan=timespan,
            maxrecords=maxrecords,
        )
        return articles, ""
    except Exception as e:
        return [], str(e)


# ============================================================
# 正規化・判定
# ============================================================

def get_domain(url: str, fallback_domain: str = "") -> str:
    if fallback_domain:
        return str(fallback_domain).lower().strip()

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        domain = domain.replace("www.", "")
        return domain
    except Exception:
        return ""


def is_japan_domain(domain: str) -> bool:
    domain = str(domain).lower().strip()
    if not domain:
        return False

    jp_suffixes = (
        ".jp",
        ".co.jp",
        ".ne.jp",
        ".or.jp",
        ".ac.jp",
        ".go.jp",
        ".ed.jp",
        ".lg.jp",
    )
    return domain.endswith(jp_suffixes)


def is_japan_source(sourcecountry: str, domain: str) -> bool:
    sc = str(sourcecountry or "").lower().strip()

    if sc in {"japan", "jp", "jpn", "ja"}:
        return True

    if "japan" in sc:
        return True

    if is_japan_domain(domain):
        return True

    return False


def parse_gdelt_datetime(value: str):
    if not value:
        return pd.NaT

    s = str(value).strip()

    try:
        if re.fullmatch(r"\d{14}", s):
            return pd.to_datetime(datetime.strptime(s, "%Y%m%d%H%M%S"), utc=True)
        return pd.to_datetime(s, utc=True, errors="coerce")
    except Exception:
        return pd.NaT


def get_first(article: Dict, keys: List[str], default=""):
    for key in keys:
        if key in article and article.get(key) is not None:
            return article.get(key)
    return default


def normalize_article(article: Dict, origin_hint: str, query_label: str) -> Dict:
    url = get_first(article, ["url", "url_mobile"], "")
    title = get_first(article, ["title"], "")
    domain = get_domain(url, get_first(article, ["domain"], ""))
    sourcecountry = get_first(article, ["sourcecountry", "sourceCountry", "source_country"], "")
    language = get_first(article, ["language", "lang"], "")
    seendate_raw = get_first(article, ["seendate", "seenDate", "date"], "")

    detected_domestic = is_japan_source(sourcecountry, domain)

    if origin_hint == "domestic":
        origin = "domestic"
    elif origin_hint == "overseas":
        origin = "domestic" if detected_domestic else "overseas"
    else:
        origin = "domestic" if detected_domestic else "overseas"

    return {
        "title": str(title or "").strip(),
        "url": str(url or "").strip(),
        "domain": domain,
        "sourcecountry": str(sourcecountry or "").strip(),
        "language": str(language or "").strip(),
        "seendate": parse_gdelt_datetime(seendate_raw),
        "seendate_raw": str(seendate_raw or ""),
        "origin": origin,
        "query_label": query_label,
        "socialimage": get_first(article, ["socialimage"], ""),
    }


def deduplicate_articles(rows: List[Dict]) -> List[Dict]:
    seen = set()
    out = []

    for row in rows:
        url = row.get("url", "")
        title = row.get("title", "")
        domain = row.get("domain", "")

        key = url if url else f"{domain}::{title}"
        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        out.append(row)

    return out


# ============================================================
# バズワード抽出
# ============================================================

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&'’\-.]{2,}|[一-龥ぁ-んァ-ヴー]{2,}")
CAP_PHRASE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9&'’\-.]+(?:\s+[A-Z][A-Za-z0-9&'’\-.]+){0,3}\b"
)


def normalize_token(token: str) -> str:
    token = token.strip().lower()
    token = token.strip(".,!?;:()[]{}\"'“”‘’")
    return token


def title_tokens(title: str) -> set:
    raw_tokens = TOKEN_RE.findall(title or "")
    tokens = set()

    fixed_lower = {normalize_token(x) for x in FIXED_KEYWORDS_50}
    fixed_parts = set()
    for kw in fixed_lower:
        for part in kw.split():
            fixed_parts.add(part)

    for token in raw_tokens:
        t = normalize_token(token)

        if len(t) < 3:
            continue
        if t in STOPWORDS:
            continue
        if t in fixed_parts:
            continue
        if re.fullmatch(r"\d+", t):
            continue

        tokens.add(t)

    return tokens


def is_bad_buzzword(word: str) -> bool:
    w = word.strip()
    wl = normalize_token(w)

    if not w:
        return True

    if len(w) < 3:
        return True

    if wl in STOPWORDS:
        return True

    if wl in {normalize_token(x) for x in FIXED_KEYWORDS_50}:
        return True

    if re.fullmatch(r"\d+", wl):
        return True

    if wl in {
        "monday", "tuesday", "wednesday", "thursday", "friday",
        "saturday", "sunday", "january", "february", "march",
        "april", "june", "july", "august", "september", "october",
        "november", "december",
    }:
        return True

    return False


def extract_buzzwords(articles: List[Dict], top_n: int = 10) -> pd.DataFrame:
    phrase_counter = Counter()
    token_counter = Counter()
    domain_map = {}

    overseas_articles = [a for a in articles if a.get("origin") == "overseas"]

    for article in overseas_articles:
        title = article.get("title", "")
        domain = article.get("domain", "")

        # 固有名詞っぽい大文字フレーズ
        for phrase in CAP_PHRASE_RE.findall(title):
            phrase = phrase.strip()
            phrase = re.sub(r"\s+", " ", phrase)

            if is_bad_buzzword(phrase):
                continue

            words = [normalize_token(x) for x in phrase.split()]
            if all(x in STOPWORDS for x in words):
                continue

            phrase_counter[phrase] += 1
            domain_map.setdefault(phrase, set()).add(domain)

        # 単語
        for token in title_tokens(title):
            if is_bad_buzzword(token):
                continue
            token_counter[token] += 1
            domain_map.setdefault(token, set()).add(domain)

    rows = []

    for word, count in phrase_counter.items():
        domains = domain_map.get(word, set())
        score = count * 2.0 + len(domains) * 1.5
        rows.append({
            "buzzword": word,
            "count": count,
            "unique_domains": len(domains),
            "score": score,
            "type": "phrase",
        })

    for word, count in token_counter.items():
        domains = domain_map.get(word, set())
        score = count * 1.0 + len(domains) * 1.2
        rows.append({
            "buzzword": word,
            "count": count,
            "unique_domains": len(domains),
            "score": score,
            "type": "token",
        })

    if not rows:
        return pd.DataFrame(columns=["buzzword", "count", "unique_domains", "score", "type"])

    df = pd.DataFrame(rows)
    df = df.sort_values(["score", "unique_domains", "count"], ascending=False)
    df = df.drop_duplicates(subset=["buzzword"])
    return df.head(top_n).reset_index(drop=True)


# ============================================================
# クラスタリング・スコアリング
# ============================================================

def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def infer_category(tokens: set, title: str) -> str:
    text = " ".join(tokens).lower() + " " + (title or "").lower()

    best_category = "その他"
    best_hits = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best_hits = hits
            best_category = category

    return best_category


def cluster_articles(
    overseas_rows: List[Dict],
    domestic_rows: List[Dict],
    similarity_threshold: float = 0.28,
) -> List[Dict]:
    clusters = []

    # 海外記事でクラスタを作る
    sorted_overseas = sorted(
        overseas_rows,
        key=lambda x: x.get("seendate") if pd.notna(x.get("seendate")) else pd.Timestamp.min.tz_localize("UTC"),
        reverse=True,
    )

    for article in sorted_overseas:
        tokens = title_tokens(article.get("title", ""))

        if not tokens:
            continue

        assigned = False

        for cluster in clusters:
            sim = jaccard(tokens, cluster["tokens"])
            overlap = len(tokens & cluster["tokens"])

            if sim >= similarity_threshold or overlap >= 3:
                cluster["overseas_articles"].append(article)
                cluster["tokens"] |= tokens
                assigned = True
                break

        if not assigned:
            clusters.append({
                "tokens": set(tokens),
                "overseas_articles": [article],
                "domestic_articles": [],
            })

    # 国内記事を近い海外クラスタに割り当てる
    for article in domestic_rows:
        tokens = title_tokens(article.get("title", ""))

        if not tokens:
            continue

        best_idx = None
        best_sim = 0.0
        best_overlap = 0

        for i, cluster in enumerate(clusters):
            sim = jaccard(tokens, cluster["tokens"])
            overlap = len(tokens & cluster["tokens"])

            if sim > best_sim or overlap > best_overlap:
                best_idx = i
                best_sim = sim
                best_overlap = overlap

        if best_idx is not None and (best_sim >= 0.18 or best_overlap >= 2):
            clusters[best_idx]["domestic_articles"].append(article)

    return clusters


def is_major_media(domain: str) -> bool:
    domain = str(domain or "").lower().replace("www.", "")
    if domain in MAJOR_MEDIA_DOMAINS:
        return True

    # サブドメイン対策
    for major in MAJOR_MEDIA_DOMAINS:
        if domain.endswith("." + major):
            return True

    return False


def score_cluster(cluster: Dict, domestic_penalty_alpha: float = 0.7) -> Dict:
    overseas_articles = cluster["overseas_articles"]
    domestic_articles = cluster["domestic_articles"]

    overseas_domains = {a.get("domain", "") for a in overseas_articles if a.get("domain")}
    domestic_domains = {a.get("domain", "") for a in domestic_articles if a.get("domain")}
    overseas_countries = {
        a.get("sourcecountry", "")
        for a in overseas_articles
        if a.get("sourcecountry") and not is_japan_source(a.get("sourcecountry"), a.get("domain"))
    }

    major_count = sum(1 for a in overseas_articles if is_major_media(a.get("domain", "")))

    dates = [
        a.get("seendate")
        for a in overseas_articles
        if pd.notna(a.get("seendate"))
    ]

    now = pd.Timestamp.now(tz="UTC")
    if dates:
        newest = max(dates)
        hours_old = max(0.0, (now - newest).total_seconds() / 3600)
        freshness_bonus = max(0.0, 6.0 - hours_old / 6.0)
    else:
        freshness_bonus = 0.0

    representative = overseas_articles[0]
    category = infer_category(cluster["tokens"], representative.get("title", ""))

    # エンタメ・文化は国内で話題になってから海外波及することも多いため、
    # 国内減点をやや弱める。
    category_penalty_multiplier = 1.0
    if category == "エンタメ・文化":
        category_penalty_multiplier = 0.55
    elif category == "観光・社会":
        category_penalty_multiplier = 0.75

    overseas_score = (
        8.0 * math.log1p(len(overseas_articles))
        + 4.5 * math.log1p(len(overseas_domains))
        + 3.5 * math.log1p(len(overseas_countries))
        + 5.0 * math.log1p(major_count)
        + freshness_bonus
    )

    domestic_penalty = category_penalty_multiplier * domestic_penalty_alpha * (
        7.0 * math.log1p(len(domestic_articles))
        + 2.0 * math.log1p(len(domestic_domains))
    )

    final_score = overseas_score - domestic_penalty

    countries_str = ", ".join(sorted([c for c in overseas_countries if c]))[:200]
    domains_str = ", ".join(sorted(list(overseas_domains))[:8])

    return {
        "score": round(final_score, 2),
        "overseas_score": round(overseas_score, 2),
        "domestic_penalty": round(domestic_penalty, 2),
        "category": category,
        "representative_title": representative.get("title", ""),
        "representative_url": representative.get("url", ""),
        "representative_domain": representative.get("domain", ""),
        "overseas_articles": len(overseas_articles),
        "domestic_articles": len(domestic_articles),
        "overseas_domains": len(overseas_domains),
        "domestic_domains": len(domestic_domains),
        "overseas_countries": len(overseas_countries),
        "major_media_articles": major_count,
        "countries": countries_str,
        "domains": domains_str,
        "tokens": " / ".join(sorted(list(cluster["tokens"]))[:12]),
        "cluster": cluster,
    }


def build_ranking(
    rows: List[Dict],
    domestic_penalty_alpha: float,
    min_score: float,
    exclude_domestic_heavy: bool,
    domestic_ratio_limit: float,
) -> pd.DataFrame:
    overseas_rows = [r for r in rows if r.get("origin") == "overseas"]
    domestic_rows = [r for r in rows if r.get("origin") == "domestic"]

    clusters = cluster_articles(overseas_rows, domestic_rows)
    scored = [score_cluster(c, domestic_penalty_alpha) for c in clusters]

    if not scored:
        return pd.DataFrame()

    df = pd.DataFrame(scored)

    if exclude_domestic_heavy:
        ratio = df["domestic_articles"] / df["overseas_articles"].clip(lower=1)
        df = df[~((df["domestic_articles"] >= 3) & (ratio >= domestic_ratio_limit))]

    df = df[df["score"] >= min_score]
    df = df.sort_values(
        ["score", "overseas_articles", "overseas_domains", "overseas_countries"],
        ascending=False,
    ).reset_index(drop=True)

    df.insert(0, "rank", range(1, len(df) + 1))
    return df


# ============================================================
# 収集処理
# ============================================================

def polite_sleep(seconds: float):
    if seconds <= 0:
        return
    time.sleep(seconds + random.uniform(0, 0.5))


def collect_news(
    timespan: str,
    maxrecords_fixed: int,
    maxrecords_buzz: int,
    max_buzzword_queries: int,
    sleep_sec: float,
    include_japanese_domestic_terms: bool,
) -> Dict:
    errors = []
    all_rows = []

    overseas_query = build_overseas_query()
    domestic_query = build_domestic_query(include_japanese_terms=include_japanese_domestic_terms)

    overseas_articles, err = fetch_gdelt_cached(
        overseas_query,
        timespan,
        maxrecords_fixed,
    )
    if err:
        errors.append(f"海外固定クエリ: {err}")

    for a in overseas_articles:
        all_rows.append(normalize_article(a, origin_hint="overseas", query_label="fixed_overseas"))

    polite_sleep(sleep_sec)

    domestic_articles, err = fetch_gdelt_cached(
        domestic_query,
        timespan,
        maxrecords_fixed,
    )
    if err:
        errors.append(f"国内固定クエリ: {err}")

    for a in domestic_articles:
        all_rows.append(normalize_article(a, origin_hint="domestic", query_label="fixed_domestic"))

    all_rows = deduplicate_articles(all_rows)

    buzz_df = extract_buzzwords(
        [r for r in all_rows if r.get("origin") == "overseas"],
        top_n=max(1, max_buzzword_queries * 3),
    )

    selected_buzzwords = []
    if not buzz_df.empty and max_buzzword_queries > 0:
        selected_buzzwords = buzz_df["buzzword"].head(max_buzzword_queries).tolist()

    # バズワード追加検索
    for buzz in selected_buzzwords:
        q_over = build_buzz_query(buzz, domestic=False)
        if q_over:
            polite_sleep(sleep_sec)
            articles, err = fetch_gdelt_cached(
                q_over,
                timespan,
                maxrecords_buzz,
            )
            if err:
                errors.append(f"海外バズワード「{buzz}」: {err}")
            for a in articles:
                all_rows.append(normalize_article(a, origin_hint="overseas", query_label=f"buzz_overseas:{buzz}"))

        q_dom = build_buzz_query(buzz, domestic=True)
        if q_dom:
            polite_sleep(sleep_sec)
            articles, err = fetch_gdelt_cached(
                q_dom,
                timespan,
                maxrecords_buzz,
            )
            if err:
                errors.append(f"国内バズワード「{buzz}」: {err}")
            for a in articles:
                all_rows.append(normalize_article(a, origin_hint="domestic", query_label=f"buzz_domestic:{buzz}"))

    all_rows = deduplicate_articles(all_rows)

    return {
        "rows": all_rows,
        "errors": errors,
        "buzz_df": buzz_df,
        "selected_buzzwords": selected_buzzwords,
        "overseas_query": overseas_query,
        "domestic_query": domestic_query,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# Streamlit UI
# ============================================================

st.set_page_config(
    page_title="海外で相対的に注目される日本ニュース",
    page_icon="🌏",
    layout="wide",
)

st.title("🌏 海外で相対的に注目される日本ニュース")
st.caption(
    "固定50ワード + バズワード自動抽出で、海外メディアでは目立つが日本国内メディアでは相対的に小さい話題をランキング化します。"
)

with st.sidebar:
    st.header("設定")

    with st.form("settings_form"):
        timespan = st.selectbox(
            "対象期間",
            ["12h", "24h", "48h", "72h", "7d"],
            index=1,
        )

        light_mode = st.checkbox(
            "軽量モード",
            value=True,
            help="GDELTの429を避けるため、最初はON推奨です。",
        )

        if light_mode:
            maxrecords_fixed = st.slider("固定クエリの最大取得件数", 50, 250, 120, 10)
            maxrecords_buzz = st.slider("バズワード1件あたり最大取得件数", 20, 100, 40, 10)
            max_buzzword_queries = st.slider("追加検索するバズワード数", 0, 8, 3, 1)
            sleep_sec = st.slider("GDELTアクセス間隔 秒", 1.0, 8.0, 3.0, 0.5)
        else:
            maxrecords_fixed = st.slider("固定クエリの最大取得件数", 50, 250, 250, 10)
            maxrecords_buzz = st.slider("バズワード1件あたり最大取得件数", 20, 150, 70, 10)
            max_buzzword_queries = st.slider("追加検索するバズワード数", 0, 12, 6, 1)
            sleep_sec = st.slider("GDELTアクセス間隔 秒", 1.0, 10.0, 2.5, 0.5)

        domestic_penalty_alpha = st.slider(
            "国内注目度の減点係数",
            0.0,
            1.5,
            0.7,
            0.05,
            help="大きくすると、日本国内でも多く報じられている話題が下がります。",
        )

        min_score = st.slider(
            "表示する最低スコア",
            -30.0,
            50.0,
            -5.0,
            1.0,
        )

        exclude_domestic_heavy = st.checkbox(
            "国内過熱トピックを除外",
            value=True,
            help="国内記事数が海外記事数に対して多すぎるクラスタを除外します。",
        )

        domestic_ratio_limit = st.slider(
            "国内記事数 / 海外記事数 の除外倍率",
            1.0,
            10.0,
            3.0,
            0.5,
        )

        include_japanese_domestic_terms = st.checkbox(
            "国内検索に日本語50ワードも使う",
            value=True,
            help="国内注目度の検出を強めます。クエリは長くなりますが、リクエスト回数は増えません。",
        )

        submitted = st.form_submit_button("ニュースを取得・ランキング化")

    if st.button("キャッシュをクリア"):
        st.cache_data.clear()
        st.session_state.pop("last_result", None)
        st.success("キャッシュをクリアしました。")

    st.markdown("---")
    st.caption(f"App version: {APP_VERSION}")
    st.caption("データ出典: GDELT Project DOC 2.0 API")


if submitted:
    with st.spinner("GDELTから取得中です。429対策のため、アクセス間隔を入れています。"):
        result = collect_news(
            timespan=timespan,
            maxrecords_fixed=maxrecords_fixed,
            maxrecords_buzz=maxrecords_buzz,
            max_buzzword_queries=max_buzzword_queries,
            sleep_sec=sleep_sec,
            include_japanese_domestic_terms=include_japanese_domestic_terms,
        )

        ranking_df = build_ranking(
            rows=result["rows"],
            domestic_penalty_alpha=domestic_penalty_alpha,
            min_score=min_score,
            exclude_domestic_heavy=exclude_domestic_heavy,
            domestic_ratio_limit=domestic_ratio_limit,
        )

        result["ranking_df"] = ranking_df
        st.session_state["last_result"] = result


result = st.session_state.get("last_result")

if result is None:
    st.info("左サイドバーの設定を確認して、「ニュースを取得・ランキング化」を押してください。")
    st.markdown("### このアプリの仕組み")
    st.markdown(
        """
- 固定50ワードを1つずつ検索せず、海外用・国内用の大きなクエリにまとめてGDELTへ投げます。
- 海外記事タイトルから、固有名詞っぽいバズワードを自動抽出します。
- 上位数件のバズワードだけ追加検索します。
- 海外記事数、海外媒体数、海外国数、大手媒体数を加点します。
- 日本国内メディアで多く報じられている話題は減点します。
- AIの従量課金APIは使っていません。
        """
    )
    st.stop()


rows = result["rows"]
ranking_df = result["ranking_df"]
errors = result["errors"]
buzz_df = result["buzz_df"]
selected_buzzwords = result["selected_buzzwords"]

overseas_count = sum(1 for r in rows if r.get("origin") == "overseas")
domestic_count = sum(1 for r in rows if r.get("origin") == "domestic")

col1, col2, col3, col4 = st.columns(4)
col1.metric("取得記事数", len(rows))
col2.metric("海外記事", overseas_count)
col3.metric("国内記事", domestic_count)
col4.metric("ランキング件数", 0 if ranking_df is None else len(ranking_df))

if errors:
    with st.expander("GDELT取得エラー・警告", expanded=True):
        st.warning(
            "一部のGDELT取得でエラーが出ました。429の場合は軽量モード、取得件数削減、アクセス間隔増加、キャッシュ利用を試してください。"
        )
        for e in errors:
            st.code(e)

with st.expander("実際に使ったGDELTクエリ"):
    st.markdown("#### 海外固定クエリ")
    st.code(result["overseas_query"])
    st.markdown("#### 国内固定クエリ")
    st.code(result["domestic_query"])

if buzz_df is not None and not buzz_df.empty:
    with st.expander("自動抽出されたバズワード"):
        st.dataframe(buzz_df, use_container_width=True)
        st.caption(f"追加検索に使ったバズワード: {', '.join(selected_buzzwords) if selected_buzzwords else 'なし'}")

st.markdown("## ランキング")

if ranking_df is None or ranking_df.empty:
    st.warning("ランキング対象がありません。対象期間を広げるか、最低スコアを下げてください。")
    st.stop()

display_columns = [
    "rank",
    "score",
    "category",
    "representative_title",
    "representative_domain",
    "overseas_articles",
    "domestic_articles",
    "overseas_domains",
    "domestic_domains",
    "overseas_countries",
    "major_media_articles",
    "overseas_score",
    "domestic_penalty",
    "countries",
]

st.dataframe(
    ranking_df[display_columns],
    use_container_width=True,
    hide_index=True,
)

csv_df = ranking_df.drop(columns=["cluster"], errors="ignore")
csv_bytes = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

st.download_button(
    label="ランキングCSVをダウンロード",
    data=csv_bytes,
    file_name="overseas_japan_news_ranking.csv",
    mime="text/csv",
)

st.markdown("## 上位トピック詳細")

top_n_detail = min(20, len(ranking_df))

for _, row in ranking_df.head(top_n_detail).iterrows():
    title = row["representative_title"]
    score = row["score"]
    category = row["category"]

    with st.expander(f'#{int(row["rank"])}｜{score}点｜{category}｜{title}'):
        st.markdown(f"**代表見出し:** {title}")

        if row.get("representative_url"):
            st.markdown(f'[代表記事を開く]({row["representative_url"]})')

        st.markdown(
            f"""
**海外記事数:** {row["overseas_articles"]}  
**国内記事数:** {row["domestic_articles"]}  
**海外媒体数:** {row["overseas_domains"]}  
**国内媒体数:** {row["domestic_domains"]}  
**海外国数:** {row["overseas_countries"]}  
**大手海外媒体記事数:** {row["major_media_articles"]}  
**海外スコア:** {row["overseas_score"]}  
**国内減点:** {row["domestic_penalty"]}  
**抽出トークン:** {row["tokens"]}
            """
        )

        cluster = row["cluster"]

        overseas_articles = cluster.get("overseas_articles", [])
        domestic_articles = cluster.get("domestic_articles", [])

        st.markdown("### 海外関連記事")
        for a in overseas_articles[:10]:
            t = a.get("title", "")
            u = a.get("url", "")
            d = a.get("domain", "")
            c = a.get("sourcecountry", "")
            if u:
                st.markdown(f"- [{t}]({u})  \n  `{d}` / `{c}`")
            else:
                st.markdown(f"- {t}  \n  `{d}` / `{c}`")

        if domestic_articles:
            st.markdown("### 国内関連記事")
            for a in domestic_articles[:10]:
                t = a.get("title", "")
                u = a.get("url", "")
                d = a.get("domain", "")
                if u:
                    st.markdown(f"- [{t}]({u})  \n  `{d}`")
                else:
                    st.markdown(f"- {t}  \n  `{d}`")
        else:
            st.caption("このクラスタに近い国内関連記事は少ない、または検出されていません。")

st.markdown("---")
st.caption(
    "データ出典: GDELT Project DOC 2.0 API。"
    "本サイトはGDELTが提供するニュースメタデータをもとに、"
    "海外メディアにおける日本関連ニュースの掲載傾向を独自に集計・ランキング化しています。"
    "記事本文・画像・見出し等の権利は各配信元に帰属します。"
)
st.caption(
    "注: 国内注目度はSNSバズ度ではなく、GDELT上で日本国内メディアと判定された記事数・媒体数にもとづく近似値です。"
)
