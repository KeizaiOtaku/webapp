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

APP_VERSION = "2026-06-17-fastmode-japan-japanese-only-429-message-fix"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
CACHE_TTL_SECONDS = 60 * 30
USER_AGENT = "overseas-japan-news-streamlit/1.1"

# 高速モード専用: 固定ワードは2種類だけ。
# 目的: 最小限の固定検索で広く拾い、詳細な固有名詞はバズワード自動抽出で補う。
FIXED_KEYWORDS_50 = [
    "Japan",
    "Japanese",
]

# 高速モードでは日本語固定検索は使わない。互換用にだけ残す。
FIXED_KEYWORDS_JA_50 = []

# これらは単独でも日本関連性が強いのでそのまま検索する
STANDALONE_TERMS = {
    "japan",
    "japanese",
}

# 高速モードではJapan/Japaneseだけを固定語にするため、アンカー検索語は使わない。
ANCHOR_WITH_JAPAN_TERMS = set()

MAJOR_MEDIA_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "cnn.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "ft.com",
    "bloomberg.com", "wsj.com", "cnbc.com", "forbes.com", "economist.com",
    "politico.com", "axios.com", "npr.org", "aljazeera.com", "dw.com",
    "france24.com", "lemonde.fr", "elpais.com", "scmp.com", "straitstimes.com",
    "abc.net.au", "theglobeandmail.com", "cbc.ca",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "with", "without",
    "for", "from", "into", "onto", "over", "under", "after", "before", "about",
    "this", "that", "these", "those", "there", "their", "they", "them", "its",
    "his", "her", "she", "him", "you", "your", "our", "who", "what", "when",
    "where", "why", "how", "new", "news", "says", "said", "say", "report",
    "reports", "reported", "update", "live", "latest", "world", "global",
    "international", "breaking", "watch", "video", "photos", "photo", "analysis",
    "opinion", "explained", "could", "would", "should", "may", "might", "will",
    "can", "one", "two", "first", "last", "japan", "japanese", "tokyo", "kyoto",
    "osaka", "hokkaido", "okinawa",
}

CATEGORY_KEYWORDS = {
    "エンタメ・文化": {
        "anime", "manga", "film", "movie", "drama", "celebrity", "music", "fashion",
        "j-pop", "game", "games", "culture", "tradition", "samurai", "ninja", "shrine",
        "temple", "food", "sushi", "ramen", "matcha", "sake", "onsen",
    },
    "経済・金融": {
        "yen", "boj", "bank", "economy", "inflation", "rates", "interest", "stock",
        "market", "nikkei", "bond", "currency", "deflation",
    },
    "政治・外交・防衛": {
        "politics", "election", "prime", "minister", "defense", "military", "security",
        "diplomacy", "china", "korea", "taiwan", "government",
    },
    "災害・気象": {
        "earthquake", "typhoon", "volcano", "heatwave", "flood", "tsunami", "weather", "disaster",
    },
    "観光・社会": {
        "tourism", "travel", "overtourism", "tourist", "demographics", "aging", "birth", "population", "society",
    },
}


# ============================================================
# クエリ生成
# ============================================================

def quote_term(term: str) -> str:
    term = str(term).strip()
    if " " in term or "-" in term:
        return f'"{term}"'
    return term


def chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def gdelt_or_group(terms: List[str]) -> str:
    """GDELT向けORグループ。括弧はOR文だけに使う。"""
    clean_terms = [quote_term(t) for t in terms if str(t).strip()]
    if not clean_terms:
        return ""
    if len(clean_terms) == 1:
        # 単一語を括弧で囲むと、GDELTが
        # "Parentheses may only be used around OR'd statements" を返すことがある。
        return clean_terms[0]
    return "(" + " OR ".join(clean_terms) + ")"


def build_fixed_queries_en(domestic: bool, fixed_chunk_size: int) -> List[Tuple[str, str]]:
    """
    固定2語をGDELT構文エラーが出ない形のクエリにする。

    重要:
    - GDELTは `(<A> AND <B>)` や入れ子括弧に弱い。
    - 括弧は `(A OR B OR C)` のようなOR文だけに使う。
    - 単独では広すぎる語は `Japan tourism` のように括弧なしの暗黙ANDで投げる。
    """
    source_filter = "sourcecountry:japan" if domestic else "-sourcecountry:japan"
    queries: List[Tuple[str, str]] = []

    or_terms: List[str] = []
    anchored_terms: List[str] = []

    for term in FIXED_KEYWORDS_50:
        low = str(term).strip().lower()
        if low in ANCHOR_WITH_JAPAN_TERMS:
            anchored_terms.append(term)
        else:
            or_terms.append(term)

    # 日本関連性が強い語はORでまとめる。括弧の中はORだけなのでGDELT構文に合う。
    chunk_size = max(1, int(fixed_chunk_size))
    for i, chunk in enumerate(chunk_list(or_terms, chunk_size), start=1):
        body = gdelt_or_group(chunk)
        if body:
            label = f"fixed_{'domestic' if domestic else 'overseas'}_or_chunk_{i}"
            queries.append((label, f"{body} {source_filter}"))

    # 広すぎる語は、括弧やAND演算子を使わず、Japanとの暗黙ANDで単独検索する。
    for term in anchored_terms:
        q = f"Japan {quote_term(term)} {source_filter}"
        safe_label = re.sub(r"[^A-Za-z0-9]+", "_", term).strip("_").lower()
        label = f"fixed_{'domestic' if domestic else 'overseas'}_anchored_{safe_label}"
        queries.append((label, q))

    return queries


def build_fixed_chunk_query_en(terms: List[str], domestic: bool) -> str:
    """
    旧関数互換用。collect_newsではbuild_fixed_queries_enを使う。
    ここでもAND/入れ子括弧は使わない。
    """
    source_filter = "sourcecountry:japan" if domestic else "-sourcecountry:japan"
    body = gdelt_or_group(terms)
    return f"{body} {source_filter}" if body else source_filter


def build_fixed_chunk_query_ja(terms: List[str]) -> str:
    body = gdelt_or_group([t for t in terms if str(t).strip()])
    return f"{body} sourcecountry:japan" if body else "sourcecountry:japan"


def sanitize_buzzword_for_query(word: str) -> str:
    word = str(word or "").strip()
    word = re.sub(r'["“”]', "", word)
    word = re.sub(r"[:(){}\[\]]", " ", word)
    word = re.sub(r"\s+", " ", word).strip()
    return word


def build_buzz_query(word: str, domestic: bool) -> str:
    word = sanitize_buzzword_for_query(word)
    if not word:
        return ""
    w = quote_term(word)
    if domestic:
        # 単一語/単一フレーズを括弧で囲まない。
        return f"{w} sourcecountry:japan"
    # GDELTでは `({w}) AND (Japan OR ...)` が構文エラーになりやすい。
    # そのため、括弧なしの暗黙ANDにする。
    return f"{w} Japan -sourcecountry:japan"


# ============================================================
# GDELT取得
# ============================================================

def gdelt_request(
    query: str,
    timespan: str,
    maxrecords: int,
    retries: int = 5,
) -> List[Dict]:
    # 取得件数0は「この検索を実行しない」として扱う。
    if int(maxrecords) <= 0:
        return []

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
                timeout=35,
                headers={"User-Agent": USER_AGENT},
            )

            text = response.text or ""
            text_head = text[:350].replace("\n", " ").replace("\r", " ")
            content_type = response.headers.get("Content-Type", "")

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait_sec = int(retry_after)
                else:
                    wait_sec = min(90, 4 * (2 ** attempt)) + random.uniform(0, 4)

                last_error = RuntimeError(
                    f"HTTP 429 Too Many Requests: GDELTのレート制限に当たりました。"
                    f"retry_after={retry_after}, next_wait_sec={wait_sec:.1f}, "
                    f"query={query}"
                )
                time.sleep(wait_sec)
                continue

            if response.status_code in {500, 502, 503, 504}:
                wait_sec = min(90, 4 * (2 ** attempt)) + random.uniform(0, 4)
                last_error = RuntimeError(
                    f"GDELT一時エラー status={response.status_code}, content_type={content_type}, body={text_head}"
                )
                time.sleep(wait_sec)
                continue

            if not response.ok:
                raise RuntimeError(
                    f"HTTP {response.status_code}, content_type={content_type}, body={text_head}"
                )

            if not text.strip():
                last_error = RuntimeError("GDELTが空レスポンスを返しました")
                time.sleep(min(60, 3 * (2 ** attempt)) + random.uniform(0, 2))
                continue

            try:
                data = response.json()
            except ValueError:
                # 200でもHTML/テキストが返ることがあるので、内容を出して原因を見える化する
                last_error = RuntimeError(
                    f"GDELTがJSON以外を返しました status={response.status_code}, "
                    f"content_type={content_type}, body={text_head}"
                )
                time.sleep(min(60, 3 * (2 ** attempt)) + random.uniform(0, 2))
                continue

            return data.get("articles", []) or []

        except Exception as e:
            last_error = e
            time.sleep(min(60, 3 * (2 ** attempt)) + random.uniform(0, 3))

    raise RuntimeError(str(last_error))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_gdelt_cached(query: str, timespan: str, maxrecords: int) -> Tuple[List[Dict], str]:
    try:
        return gdelt_request(query=query, timespan=timespan, maxrecords=maxrecords), ""
    except Exception as e:
        return [], str(e)


# ============================================================
# 記事正規化
# ============================================================

def get_first(article: Dict, keys: List[str], default=""):
    for key in keys:
        if key in article and article.get(key) is not None:
            return article.get(key)
    return default


def get_domain(url: str, fallback_domain: str = "") -> str:
    if fallback_domain:
        return str(fallback_domain).lower().strip().replace("www.", "")
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_japan_domain(domain: str) -> bool:
    d = str(domain or "").lower().strip()
    return d.endswith((".jp", ".co.jp", ".ne.jp", ".or.jp", ".ac.jp", ".go.jp", ".ed.jp", ".lg.jp"))


def is_japan_source(sourcecountry: str, domain: str) -> bool:
    sc = str(sourcecountry or "").lower().strip()
    return sc in {"japan", "jp", "jpn", "ja"} or "japan" in sc or is_japan_domain(domain)


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
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


# ============================================================
# バズワード抽出
# ============================================================

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&'’\-.]{2,}|[一-龥ぁ-んァ-ヴー]{2,}")
CAP_PHRASE_RE = re.compile(r"\b[A-Z][A-Za-z0-9&'’\-.]+(?:\s+[A-Z][A-Za-z0-9&'’\-.]+){0,3}\b")


def normalize_token(token: str) -> str:
    return str(token or "").strip().lower().strip(".,!?;:()[]{}\"'“”‘’")


def title_tokens(title: str) -> set:
    raw_tokens = TOKEN_RE.findall(title or "")
    tokens = set()
    fixed_parts = set()
    for kw in FIXED_KEYWORDS_50:
        for part in normalize_token(kw).split():
            fixed_parts.add(part)

    for token in raw_tokens:
        t = normalize_token(token)
        if len(t) < 3 or t in STOPWORDS or t in fixed_parts or re.fullmatch(r"\d+", t):
            continue
        tokens.add(t)
    return tokens


def is_bad_buzzword(word: str) -> bool:
    w = str(word or "").strip()
    wl = normalize_token(w)
    if not w or len(w) < 3 or wl in STOPWORDS or re.fullmatch(r"\d+", wl):
        return True
    if wl in {normalize_token(x) for x in FIXED_KEYWORDS_50}:
        return True
    if wl in {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
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

        for phrase in CAP_PHRASE_RE.findall(title):
            phrase = re.sub(r"\s+", " ", phrase.strip())
            if is_bad_buzzword(phrase):
                continue
            if all(normalize_token(x) in STOPWORDS for x in phrase.split()):
                continue
            phrase_counter[phrase] += 1
            domain_map.setdefault(phrase, set()).add(domain)

        for token in title_tokens(title):
            if is_bad_buzzword(token):
                continue
            token_counter[token] += 1
            domain_map.setdefault(token, set()).add(domain)

    rows = []
    for word, count in phrase_counter.items():
        domains = domain_map.get(word, set())
        rows.append({"buzzword": word, "count": count, "unique_domains": len(domains), "score": count * 2.0 + len(domains) * 1.5, "type": "phrase"})
    for word, count in token_counter.items():
        domains = domain_map.get(word, set())
        rows.append({"buzzword": word, "count": count, "unique_domains": len(domains), "score": count * 1.0 + len(domains) * 1.2, "type": "token"})

    if not rows:
        return pd.DataFrame(columns=["buzzword", "count", "unique_domains", "score", "type"])

    return (
        pd.DataFrame(rows)
        .sort_values(["score", "unique_domains", "count"], ascending=False)
        .drop_duplicates(subset=["buzzword"])
        .head(top_n)
        .reset_index(drop=True)
    )


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


def cluster_articles(overseas_rows: List[Dict], domestic_rows: List[Dict], similarity_threshold: float = 0.28) -> List[Dict]:
    clusters = []
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
            clusters.append({"tokens": set(tokens), "overseas_articles": [article], "domestic_articles": []})

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
    d = str(domain or "").lower().replace("www.", "")
    return d in MAJOR_MEDIA_DOMAINS or any(d.endswith("." + major) for major in MAJOR_MEDIA_DOMAINS)


def score_cluster(cluster: Dict, domestic_penalty_alpha: float) -> Dict:
    overseas_articles = cluster["overseas_articles"]
    domestic_articles = cluster["domestic_articles"]
    overseas_domains = {a.get("domain", "") for a in overseas_articles if a.get("domain")}
    domestic_domains = {a.get("domain", "") for a in domestic_articles if a.get("domain")}
    overseas_countries = {
        a.get("sourcecountry", "") for a in overseas_articles
        if a.get("sourcecountry") and not is_japan_source(a.get("sourcecountry"), a.get("domain"))
    }
    major_count = sum(1 for a in overseas_articles if is_major_media(a.get("domain", "")))

    dates = [a.get("seendate") for a in overseas_articles if pd.notna(a.get("seendate"))]
    now = pd.Timestamp.now(tz="UTC")
    if dates:
        newest = max(dates)
        hours_old = max(0.0, (now - newest).total_seconds() / 3600)
        freshness_bonus = max(0.0, 6.0 - hours_old / 6.0)
    else:
        freshness_bonus = 0.0

    representative = overseas_articles[0]
    category = infer_category(cluster["tokens"], representative.get("title", ""))

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
        "countries": ", ".join(sorted([c for c in overseas_countries if c]))[:200],
        "domains": ", ".join(sorted(list(overseas_domains))[:8]),
        "tokens": " / ".join(sorted(list(cluster["tokens"]))[:12]),
        "cluster": cluster,
    }


def build_ranking(rows: List[Dict], domestic_penalty_alpha: float, min_score: float, exclude_domestic_heavy: bool, domestic_ratio_limit: float) -> pd.DataFrame:
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
    df = df.sort_values(["score", "overseas_articles", "overseas_domains", "overseas_countries"], ascending=False).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


# ============================================================
# 収集処理
# ============================================================

def polite_sleep(seconds: float):
    if seconds > 0:
        time.sleep(seconds + random.uniform(0, 0.5))


def collect_news(timespan: str, maxrecords_fixed: int, maxrecords_buzz: int, max_buzzword_queries: int, sleep_sec: float, include_japanese_domestic_terms: bool, fixed_chunk_size: int) -> Dict:
    errors = []
    all_rows = []
    query_log = []

    # 英語固定2語 Japan/Japanese を、GDELT構文に合う安全なクエリへ変換して検索。
    # 括弧はORグループだけに使い、AND/入れ子括弧は使わない。
    for label_over, q_over in build_fixed_queries_en(domestic=False, fixed_chunk_size=fixed_chunk_size):
        query_log.append({"label": label_over, "query": q_over})
        articles, err = fetch_gdelt_cached(q_over, timespan, maxrecords_fixed)
        if err:
            errors.append(f"{label_over}: {err}")
        for a in articles:
            all_rows.append(normalize_article(a, origin_hint="overseas", query_label=label_over))
        polite_sleep(sleep_sec)

    for label_dom, q_dom in build_fixed_queries_en(domestic=True, fixed_chunk_size=fixed_chunk_size):
        query_log.append({"label": label_dom, "query": q_dom})
        articles, err = fetch_gdelt_cached(q_dom, timespan, maxrecords_fixed)
        if err:
            errors.append(f"{label_dom}: {err}")
        for a in articles:
            all_rows.append(normalize_article(a, origin_hint="domestic", query_label=label_dom))
        polite_sleep(sleep_sec)

    # 日本語固定10語はGDELT側で不安定なことがあるため、任意ONにする
    if include_japanese_domestic_terms:
        for i, chunk in enumerate(chunk_list(FIXED_KEYWORDS_JA_50, fixed_chunk_size), start=1):
            q_ja = build_fixed_chunk_query_ja(chunk)
            label_ja = f"fixed_domestic_ja_chunk_{i}"
            query_log.append({"label": label_ja, "query": q_ja})
            articles, err = fetch_gdelt_cached(q_ja, timespan, maxrecords_fixed)
            if err:
                errors.append(f"{label_ja}: {err}")
            for a in articles:
                all_rows.append(normalize_article(a, origin_hint="domestic", query_label=label_ja))
            polite_sleep(sleep_sec)

    all_rows = deduplicate_articles(all_rows)

    buzz_df = extract_buzzwords([r for r in all_rows if r.get("origin") == "overseas"], top_n=max(1, max_buzzword_queries * 3))
    selected_buzzwords = []
    if not buzz_df.empty and max_buzzword_queries > 0:
        selected_buzzwords = buzz_df["buzzword"].head(max_buzzword_queries).tolist()

    for buzz in selected_buzzwords:
        q_over = build_buzz_query(buzz, domestic=False)
        if q_over:
            label = f"buzz_overseas:{buzz}"
            query_log.append({"label": label, "query": q_over})
            polite_sleep(sleep_sec)
            articles, err = fetch_gdelt_cached(q_over, timespan, maxrecords_buzz)
            if err:
                errors.append(f"{label}: {err}")
            for a in articles:
                all_rows.append(normalize_article(a, origin_hint="overseas", query_label=label))

        q_dom = build_buzz_query(buzz, domestic=True)
        if q_dom:
            label = f"buzz_domestic:{buzz}"
            query_log.append({"label": label, "query": q_dom})
            polite_sleep(sleep_sec)
            articles, err = fetch_gdelt_cached(q_dom, timespan, maxrecords_buzz)
            if err:
                errors.append(f"{label}: {err}")
            for a in articles:
                all_rows.append(normalize_article(a, origin_hint="domestic", query_label=label))

    all_rows = deduplicate_articles(all_rows)

    return {
        "rows": all_rows,
        "errors": errors,
        "buzz_df": buzz_df,
        "selected_buzzwords": selected_buzzwords,
        "query_log": query_log,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# Streamlit UI
# ============================================================

st.set_page_config(page_title="海外で相対的に注目される日本ニュース", page_icon="🌏", layout="wide")
st.title("🌏 海外で相対的に注目される日本ニュース")
st.caption("高速モード専用: 固定ワードは Japan / Japanese の2種類だけ。そこからバズワードを幅広く抽出・追加検索してランキング化します。")

with st.sidebar:
    st.header("設定")

    with st.form("settings_form"):
        timespan = st.selectbox("対象期間", ["12h", "24h", "48h", "72h", "7d"], index=1)

        st.info("高速モード専用です。固定検索は海外1回・国内1回だけ行います。")

        maxrecords_fixed = st.slider(
            "固定クエリ1本あたり最大取得件数",
            min_value=0,
            max_value=250,
            value=100,
            step=10,
            help="0にすると固定検索を実行しません。通常は50〜150程度がおすすめです。",
        )
        maxrecords_buzz = st.slider(
            "バズワード1件あたり最大取得件数",
            min_value=0,
            max_value=150,
            value=40,
            step=10,
            help="0にするとバズワード追加検索を実行しません。",
        )
        max_buzzword_queries = st.slider(
            "追加検索するバズワード数",
            min_value=0,
            max_value=30,
            value=6,
            step=1,
            help="増やすほど幅広く調べますが、GDELTへのリクエスト数と取得時間が増えます。",
        )
        sleep_sec = st.slider(
            "GDELTアクセス間隔 秒",
            min_value=0.0,
            max_value=10.0,
            value=0.5,
            step=0.1,
            help="0.0秒から0.1秒刻みで指定できます。429や非JSONエラーが出る場合は増やしてください。",
        )

        domestic_penalty_alpha = st.slider("国内注目度の減点係数", 0.0, 1.5, 0.7, 0.05)
        min_score = st.slider("表示する最低スコア", -30.0, 50.0, -5.0, 1.0)
        exclude_domestic_heavy = st.checkbox("国内過熱トピックを除外", value=True)
        domestic_ratio_limit = st.slider("国内記事数 / 海外記事数 の除外倍率", 1.0, 10.0, 3.0, 0.5)

        submitted = st.form_submit_button("ニュースを取得・ランキング化")

    if st.button("キャッシュをクリア"):
        st.cache_data.clear()
        st.session_state.pop("last_result", None)
        st.success("キャッシュをクリアしました。")

    st.markdown("---")
    st.caption(f"App version: {APP_VERSION}")
    st.caption("データ出典: GDELT Project DOC 2.0 API")

if submitted:
    with st.spinner("GDELTから取得中です。高速モードで固定2語とバズワード検索を実行しています。"):
        result = collect_news(
            timespan=timespan,
            maxrecords_fixed=maxrecords_fixed,
            maxrecords_buzz=maxrecords_buzz,
            max_buzzword_queries=max_buzzword_queries,
            sleep_sec=sleep_sec,
            include_japanese_domestic_terms=False,
            fixed_chunk_size=2,
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
    st.info("左サイドバーの設定を確認して、『ニュースを取得・ランキング化』を押してください。")
    st.markdown("### このアプリの仕組み")
    st.markdown(
        """
- 固定ワードは Japan / Japanese の2種類だけです。
- GDELTがJSON以外を返した場合は、レスポンス冒頭をエラーに表示します。
- 海外記事タイトルからバズワードを自動抽出し、指定数だけ追加検索します。
- 海外記事数・海外媒体数・海外国数・大手媒体数を加点します。
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
query_log = result.get("query_log", [])

overseas_count = sum(1 for r in rows if r.get("origin") == "overseas")
domestic_count = sum(1 for r in rows if r.get("origin") == "domestic")

col1, col2, col3, col4 = st.columns(4)
col1.metric("取得記事数", len(rows))
col2.metric("海外記事", overseas_count)
col3.metric("国内記事", domestic_count)
col4.metric("ランキング件数", 0 if ranking_df is None else len(ranking_df))

if errors:
    with st.expander("GDELT取得エラー・警告", expanded=True):
        st.warning("一部のGDELT取得でエラーが出ました。取得自体が部分成功していればランキングは表示できます。頻発する場合は、取得件数削減、バズワード数削減、アクセス間隔増加を試してください。")
        for e in errors:
            st.code(e)

with st.expander("実際に使ったGDELTクエリ"):
    if query_log:
        qdf = pd.DataFrame(query_log)
        st.dataframe(qdf, use_container_width=True, hide_index=True)
    else:
        st.caption("クエリログなし")

if buzz_df is not None and not buzz_df.empty:
    with st.expander("自動抽出されたバズワード"):
        st.dataframe(buzz_df, use_container_width=True, hide_index=True)
        st.caption(f"追加検索に使ったバズワード: {', '.join(selected_buzzwords) if selected_buzzwords else 'なし'}")

st.markdown("## ランキング")

if ranking_df is None or ranking_df.empty:
    st.warning("ランキング対象がありません。対象期間を広げる、最低スコアを下げる、固定クエリ1本あたりの取得件数を増やす、などを試してください。")
    st.stop()

display_columns = [
    "rank", "score", "category", "representative_title", "representative_domain",
    "overseas_articles", "domestic_articles", "overseas_domains", "domestic_domains",
    "overseas_countries", "major_media_articles", "overseas_score", "domestic_penalty", "countries",
]

st.dataframe(ranking_df[display_columns], use_container_width=True, hide_index=True)

csv_df = ranking_df.drop(columns=["cluster"], errors="ignore")
csv_bytes = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button("ランキングCSVをダウンロード", data=csv_bytes, file_name="overseas_japan_news_ranking.csv", mime="text/csv")

st.markdown("## 上位トピック詳細")
for _, row in ranking_df.head(min(20, len(ranking_df))).iterrows():
    with st.expander(f'#{int(row["rank"])}｜{row["score"]}点｜{row["category"]}｜{row["representative_title"]}'):
        st.markdown(f'**代表見出し:** {row["representative_title"]}')
        if row.get("representative_url"):
            st.markdown(f'[代表記事を開く]({row["representative_url"]})')
        st.markdown(
            f"""
**海外記事数:** {row['overseas_articles']}  
**国内記事数:** {row['domestic_articles']}  
**海外媒体数:** {row['overseas_domains']}  
**国内媒体数:** {row['domestic_domains']}  
**海外国数:** {row['overseas_countries']}  
**大手海外媒体記事数:** {row['major_media_articles']}  
**海外スコア:** {row['overseas_score']}  
**国内減点:** {row['domestic_penalty']}  
**抽出トークン:** {row['tokens']}
            """
        )

        cluster = row["cluster"]
        st.markdown("### 海外関連記事")
        for a in cluster.get("overseas_articles", [])[:10]:
            t, u, d, c = a.get("title", ""), a.get("url", ""), a.get("domain", ""), a.get("sourcecountry", "")
            if u:
                st.markdown(f"- [{t}]({u})  \n  `{d}` / `{c}`")
            else:
                st.markdown(f"- {t}  \n  `{d}` / `{c}`")

        domestic_articles = cluster.get("domestic_articles", [])
        if domestic_articles:
            st.markdown("### 国内関連記事")
            for a in domestic_articles[:10]:
                t, u, d = a.get("title", ""), a.get("url", ""), a.get("domain", "")
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
st.caption("注: 国内注目度はSNSバズ度ではなく、GDELT上で日本国内メディアと判定された記事数・媒体数にもとづく近似値です。")
