# app.py
# Streamlit app: English overseas RSS Japan-buzz ranker
# - No article-body scraping
# - Excludes RSS sources previously identified as clearly restricted for commercial/non-commercial use
# - Ranks English RSS items by Japan-specific 300-term hits in title / URL / metadata

from __future__ import annotations

import csv
import math
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import SimpleNamespace
import html
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import pandas as pd
import requests
import streamlit as st

APP_VERSION = "2026-06-17-rss-japan-buzz-300-no-feedparser"
MAX_RANKING = 30

# Japan / Japanese are intentionally NOT included here.
# These 300 terms are used only for scoring after RSS items are collected.
JAPAN_SPECIFIC_TERMS_300 = ['yen',
 'Bank of Japan',
 'BOJ',
 'Nikkei',
 'TOPIX',
 'Tokyo Stock Exchange',
 'TSE',
 'JGB',
 'government bonds',
 'LDP',
 'Komeito',
 'Constitutional Democratic Party',
 'Diet',
 'National Diet',
 'House of Representatives',
 'House of Councillors',
 "Prime Minister's Office",
 'Kantei',
 'Self-Defense Forces',
 'SDF',
 'JSDF',
 'Okinawa bases',
 'Futenma',
 'Henoko',
 'Senkaku',
 'Northern Territories',
 'Yasukuni',
 'imperial family',
 'Emperor Naruhito',
 'Imperial Household Agency',
 'My Number',
 'consumer tax',
 'shunto',
 'keidanren',
 'zaibatsu',
 'keiretsu',
 'sogo shosha',
 'salaryman',
 'karoshi',
 'hikikomori',
 'aging population',
 'birth rate',
 'depopulation',
 'labor shortage',
 'technical intern',
 'Tokyo',
 'Osaka',
 'Kyoto',
 'Hokkaido',
 'Okinawa',
 'Mount Fuji',
 'Fuji',
 'Shibuya',
 'Shinjuku',
 'Akihabara',
 'Ginza',
 'Asakusa',
 'Harajuku',
 'Roppongi',
 'Ueno',
 'Ikebukuro',
 'Yokohama',
 'Kamakura',
 'Kobe',
 'Nara',
 'Hiroshima',
 'Nagasaki',
 'Fukuoka',
 'Sapporo',
 'Nagoya',
 'Kanazawa',
 'Sendai',
 'Kumamoto',
 'Kagoshima',
 'Nikko',
 'Hakone',
 'Izu',
 'Noto Peninsula',
 'Tohoku',
 'Kansai',
 'Kyushu',
 'Shikoku',
 'Chubu',
 'Kanto',
 'Setouchi',
 'Miyajima',
 'Naoshima',
 'Shinkansen',
 'JR Pass',
 'Suica',
 'sushi',
 'ramen',
 'udon',
 'soba',
 'tempura',
 'wagyu',
 'kobe beef',
 'matcha',
 'sake',
 'nihonshu',
 'shochu',
 'umeshu',
 'bento',
 'onigiri',
 'takoyaki',
 'okonomiyaki',
 'yakitori',
 'tonkatsu',
 'curry rice',
 'omakase',
 'kaiseki',
 'izakaya',
 'miso',
 'natto',
 'tofu',
 'mochi',
 'daifuku',
 'dorayaki',
 'taiyaki',
 'umami',
 'kimono',
 'yukata',
 'geisha',
 'maiko',
 'samurai',
 'ninja',
 'shogun',
 'daimyo',
 'bushido',
 'katana',
 'wakizashi',
 'shuriken',
 'Shinto',
 'torii',
 'kami',
 'miko',
 'omamori',
 'ema',
 'shrine',
 'temple',
 'matsuri',
 'hanami',
 'sakura',
 'cherry blossoms',
 'bonsai',
 'ikebana',
 'tea ceremony',
 'tatami',
 'futon',
 'kabuki',
 'noh',
 'bunraku',
 'rakugo',
 'haiku',
 'ukiyo-e',
 'Hokusai',
 'Edo',
 'Meiji',
 'Heian',
 'Sengoku',
 'Ainu',
 'Ryukyu',
 'wabi-sabi',
 'kintsugi',
 'origami',
 'anime',
 'manga',
 'otaku',
 'cosplay',
 'comiket',
 'doujinshi',
 'light novel',
 'visual novel',
 'isekai',
 'shonen',
 'shojo',
 'seinen',
 'josei',
 'mecha',
 'magical girl',
 'kawaii',
 'moe',
 'tsundere',
 'yandere',
 'waifu',
 'husbando',
 'senpai',
 'sensei',
 'chibi',
 'chuunibyou',
 'gacha',
 'gachapon',
 'purikura',
 'maid cafe',
 'idol',
 'J-pop',
 'J-rock',
 'city pop',
 'enka',
 'Vocaloid',
 'Hatsune Miku',
 'VTuber',
 'Hololive',
 'Nijisanji',
 'virtual idol',
 'Niconico',
 'Pixiv',
 'Line stickers',
 'tokusatsu',
 'kaiju',
 'Studio Ghibli',
 'Hayao Miyazaki',
 'Ghibli Park',
 'Totoro',
 'Spirited Away',
 'Princess Mononoke',
 'Pokemon',
 'Pikachu',
 'Godzilla',
 'Toho',
 'Ultraman',
 'Gundam',
 'Evangelion',
 'One Piece',
 'Demon Slayer',
 'Kimetsu no Yaiba',
 'Dragon Ball',
 'Naruto',
 'Boruto',
 'Jujutsu Kaisen',
 'Attack on Titan',
 'My Hero Academia',
 'Chainsaw Man',
 'Spy x Family',
 'Sailor Moon',
 'Detective Conan',
 'Doraemon',
 'Hello Kitty',
 'Sanrio',
 'Aggretsuko',
 'Rilakkuma',
 'Chiikawa',
 'Anpanman',
 'Crayon Shin-chan',
 'Yu-Gi-Oh',
 'Beyblade',
 'Digimon',
 'Tamagotchi',
 'Final Fantasy',
 'Dragon Quest',
 'Kingdom Hearts',
 'Persona',
 'Monster Hunter',
 'Resident Evil',
 'Street Fighter',
 'Tekken',
 'Yakuza',
 'Like a Dragon',
 'Mario',
 'Zelda',
 'Toyota',
 'Honda',
 'Nissan',
 'Mazda',
 'Subaru',
 'Suzuki',
 'Mitsubishi Motors',
 'Lexus',
 'Yamaha',
 'Kawasaki',
 'Sony',
 'Nintendo',
 'SoftBank',
 'Rakuten',
 'NTT',
 'KDDI',
 'Panasonic',
 'Hitachi',
 'Toshiba',
 'Sharp',
 'Fujitsu',
 'NEC',
 'Canon',
 'Nikon',
 'Olympus',
 'Shohei Ohtani',
 'Ohtani',
 'Yoshinobu Yamamoto',
 'Roki Sasaki',
 'Ichiro',
 'Yuzuru Hanyu',
 'Naomi Osaka',
 'sumo',
 'yokozuna',
 'earthquake',
 'tsunami',
 'typhoon',
 'volcano',
 'Fukushima Daiichi',
 'Nankai Trough']

# Conservative initial RSS list.
# Excluded from this initial list: Guardian, Washington Post, Le Monde, Google News RSS, Reuters RSS.
RSS_FEEDS = [{'category': 'top', 'source': 'BBC News', 'url': 'http://feeds.bbci.co.uk/news/rss.xml', 'weight': 5},
 {'category': 'world', 'source': 'BBC News', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'weight': 5},
 {'category': 'business', 'source': 'BBC News', 'url': 'http://feeds.bbci.co.uk/news/business/rss.xml', 'weight': 4},
 {'category': 'technology',
  'source': 'BBC News',
  'url': 'http://feeds.bbci.co.uk/news/technology/rss.xml',
  'weight': 4},
 {'category': 'entertainment',
  'source': 'BBC News',
  'url': 'http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml',
  'weight': 3},
 {'category': 'top', 'source': 'ABC News', 'url': 'https://feeds.abcnews.com/abcnews/topstories', 'weight': 4},
 {'category': 'international',
  'source': 'ABC News',
  'url': 'https://feeds.abcnews.com/abcnews/internationalheadlines',
  'weight': 5},
 {'category': 'business', 'source': 'ABC News', 'url': 'https://feeds.abcnews.com/abcnews/moneyheadlines', 'weight': 3},
 {'category': 'technology',
  'source': 'ABC News',
  'url': 'https://feeds.abcnews.com/abcnews/technologyheadlines',
  'weight': 3},
 {'category': 'entertainment',
  'source': 'ABC News',
  'url': 'https://feeds.abcnews.com/abcnews/entertainmentheadlines',
  'weight': 3},
 {'category': 'travel', 'source': 'ABC News', 'url': 'https://feeds.abcnews.com/abcnews/travelheadlines', 'weight': 3},
 {'category': 'top', 'source': 'CBS News', 'url': 'https://www.cbsnews.com/latest/rss/main', 'weight': 4},
 {'category': 'world', 'source': 'CBS News', 'url': 'https://www.cbsnews.com/latest/rss/world', 'weight': 4},
 {'category': 'moneywatch', 'source': 'CBS News', 'url': 'https://www.cbsnews.com/latest/rss/moneywatch', 'weight': 3},
 {'category': 'science', 'source': 'CBS News', 'url': 'https://www.cbsnews.com/latest/rss/science', 'weight': 3},
 {'category': 'technology', 'source': 'CBS News', 'url': 'https://www.cbsnews.com/latest/rss/technology', 'weight': 3},
 {'category': 'entertainment',
  'source': 'CBS News',
  'url': 'https://www.cbsnews.com/latest/rss/entertainment',
  'weight': 3},
 {'category': 'news',
  'source': 'Euronews',
  'url': 'https://www.euronews.com/rss?format=mrss&level=theme&name=news',
  'weight': 4},
 {'category': 'travel',
  'source': 'Euronews',
  'url': 'https://www.euronews.com/rss?format=mrss&level=theme&name=travel',
  'weight': 3},
 {'category': 'culture',
  'source': 'Euronews',
  'url': 'https://www.euronews.com/rss?format=mrss&level=theme&name=culture',
  'weight': 3},
 {'category': 'technology',
  'source': 'Euronews',
  'url': 'https://www.euronews.com/rss?format=mrss&level=theme&name=next',
  'weight': 3},
 {'category': 'all', 'source': 'DW', 'url': 'https://rss.dw.com/rdf/rss-en-all', 'weight': 4},
 {'category': 'all', 'source': 'France 24', 'url': 'https://www.france24.com/en/rss', 'weight': 4},
 {'category': 'asia-pacific',
  'source': 'France 24',
  'url': 'https://www.france24.com/en/asia-pacific/rss',
  'weight': 4},
 {'category': 'business-tech',
  'source': 'France 24',
  'url': 'https://www.france24.com/en/business-tech/rss',
  'weight': 3},
 {'category': 'culture', 'source': 'France 24', 'url': 'https://www.france24.com/en/culture/rss', 'weight': 3},
 {'category': 'all', 'source': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'weight': 4},
 {'category': 'tech', 'source': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml', 'weight': 4},
 {'category': 'technology',
  'source': 'Ars Technica',
  'url': 'https://feeds.arstechnica.com/arstechnica/index',
  'weight': 3},
 {'category': 'technology', 'source': 'Engadget', 'url': 'https://www.engadget.com/rss.xml', 'weight': 3},
 {'category': 'gaming', 'source': 'Polygon', 'url': 'https://www.polygon.com/rss/index.xml', 'weight': 4},
 {'category': 'gaming', 'source': 'Kotaku', 'url': 'https://kotaku.com/rss', 'weight': 4},
 {'category': 'gaming', 'source': 'IGN', 'url': 'https://feeds.feedburner.com/ign/all', 'weight': 4},
 {'category': 'gaming', 'source': 'GameSpot', 'url': 'https://www.gamespot.com/feeds/mashup/', 'weight': 3},
 {'category': 'anime',
  'source': 'Anime News Network',
  'url': 'https://www.animenewsnetwork.com/all/rss.xml',
  'weight': 5},
 {'category': 'anime', 'source': 'Crunchyroll News', 'url': 'https://www.crunchyroll.com/news/rss', 'weight': 4},
 {'category': 'travel', 'source': 'BBC Travel', 'url': 'https://www.bbc.com/travel/feed.rss', 'weight': 4},
 {'category': 'travel', 'source': 'Travel + Leisure', 'url': 'https://www.travelandleisure.com/feed', 'weight': 3},
 {'category': 'travel', 'source': 'Lonely Planet', 'url': 'https://www.lonelyplanet.com/news/feed', 'weight': 3},
 {'category': 'travel-business', 'source': 'Skift', 'url': 'https://skift.com/feed/', 'weight': 3},
 {'category': 'markets',
  'source': 'MarketWatch',
  'url': 'https://feeds.marketwatch.com/marketwatch/topstories/',
  'weight': 3},
 {'category': 'finance', 'source': 'Yahoo Finance', 'url': 'https://finance.yahoo.com/news/rssindex', 'weight': 3}]

CATEGORY_BONUS = {
    "anime": 8,
    "gaming": 6,
    "culture": 5,
    "travel": 5,
    "travel-business": 4,
    "asia-pacific": 4,
    "business": 3,
    "business-tech": 3,
    "markets": 3,
    "finance": 3,
    "technology": 3,
    "tech": 3,
    "entertainment": 3,
    "world": 2,
    "international": 2,
    "top": 1,
    "all": 1,
}

NOISY_LOW_WEIGHT_TERMS = {
    "sake": 0.25,       # for the sake of
    "fuji": 0.5,        # names/products can collide
    "ninja": 0.7,
    "samurai": 0.7,
    "diet": 0.6,        # National Diet vs food diet
    "sharp": 0.6,
    "canon": 0.6,
    "temple": 0.8,
    "shrine": 0.8,
    "volcano": 0.8,
    "earthquake": 0.8,
    "typhoon": 0.8,
}

SCRIPT_BLOCK_RE = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿"
    r"가-힯Ѐ-ӿ؀-ۿ"
    r"฀-๿Ͱ-Ͽ]"
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; JapanBuzzRSSRanker/1.0; "
    "+https://example.com/rss-japan-buzz-ranker)"
)


def is_probably_english_title(title: str) -> bool:
    """Lightweight English-title filter without external language libraries."""
    if not title:
        return False
    t = unicodedata.normalize("NFKC", title).strip()
    if len(t) < 8:
        return False
    if SCRIPT_BLOCK_RE.search(t):
        return False
    letters = [ch for ch in t if ch.isalpha()]
    if len(letters) < 4:
        return False
    ascii_letters = [ch for ch in letters if "a" <= ch.lower() <= "z"]
    ascii_ratio = len(ascii_letters) / max(1, len(letters))
    return ascii_ratio >= 0.85


def clean_url_for_dedupe(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        filtered_query = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            kl = k.lower()
            if kl.startswith("utm_") or kl in {"fbclid", "gclid", "mc_cid", "mc_eid"}:
                continue
            filtered_query.append((k, v))
        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(filtered_query),
            "",
        ))
    except Exception:
        return url.strip().lower()


def normalize_for_matching(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    # Keep a raw-ish version but make URL separators and punctuation searchable as spaces.
    text = re.sub(r"[‐-―\-/_.:+|#?=&%]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def term_pattern(term: str) -> re.Pattern:
    t = normalize_for_matching(term)
    # Allow spaces/hyphen-like separators between phrase parts.
    escaped = re.escape(t).replace(r"\ ", r"[\s\-_/]+")
    return re.compile(r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])", re.IGNORECASE)


@st.cache_resource(show_spinner=False)
def compiled_term_patterns() -> list[tuple[str, re.Pattern]]:
    return [(term, term_pattern(term)) for term in JAPAN_SPECIFIC_TERMS_300]


def parse_datetime_string(value: str) -> datetime | None:
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    try:
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        iso = v.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_entry_datetime(entry: Any) -> datetime | None:
    dt = entry.get("published_dt")
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    for key in ("published", "updated", "created", "pubDate", "dc_date"):
        parsed = parse_datetime_string(entry.get(key, ""))
        if parsed:
            return parsed
    return None


def entry_tags_text(entry: Any) -> str:
    tags = []
    for tag in entry.get("tags", []) or []:
        if isinstance(tag, dict):
            term = tag.get("term") or tag.get("label")
        else:
            term = str(tag)
        if term:
            tags.append(str(term))
    return " ".join(tags)


def build_scoring_text(item: dict[str, Any], include_summary_for_scoring: bool) -> str:
    parts = [
        item.get("title", ""),
        item.get("link", ""),
        item.get("source", ""),
        item.get("feed_category", ""),
        item.get("feed_title", ""),
        item.get("tags", ""),
    ]
    if include_summary_for_scoring:
        # Used only internally for scoring; not displayed as article content.
        parts.append(item.get("summary", ""))
    return normalize_for_matching(" ".join(str(x) for x in parts if x))


def count_japan_terms(item: dict[str, Any], include_summary_for_scoring: bool) -> dict[str, Any]:
    text = build_scoring_text(item, include_summary_for_scoring)
    total_hits = 0
    weighted_hits = 0.0
    matched_terms: list[str] = []
    term_counts: dict[str, int] = {}

    for term, pat in compiled_term_patterns():
        n = len(pat.findall(text))
        if n <= 0:
            continue
        total_hits += n
        weight = NOISY_LOW_WEIGHT_TERMS.get(term.lower(), 1.0)
        weighted_hits += n * weight
        matched_terms.append(term)
        term_counts[term] = n

    return {
        "term_total_hits": total_hits,
        "term_weighted_hits": weighted_hits,
        "unique_term_hits": len(matched_terms),
        "matched_terms": matched_terms,
        "term_counts": term_counts,
    }


def xml_text(parent: ET.Element | None, names: list[str]) -> str:
    if parent is None:
        return ""
    wanted = {n.lower() for n in names}
    for child in list(parent):
        local = child.tag.split("}")[-1].lower()
        full = child.tag.lower()
        if local in wanted or full in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return html.unescape(text)
    return ""


def xml_link(parent: ET.Element | None) -> str:
    if parent is None:
        return ""
    # RSS: <link>https://...</link>
    txt = xml_text(parent, ["link"])
    if txt and not txt.lower().startswith("mailto:"):
        return txt
    # Atom: <link href="..." rel="alternate"/>
    for child in list(parent):
        local = child.tag.split("}")[-1].lower()
        if local == "link":
            href = child.attrib.get("href", "")
            rel = child.attrib.get("rel", "alternate")
            if href and rel in {"alternate", "", None}:
                return html.unescape(href.strip())
    return ""


def xml_categories(parent: ET.Element | None) -> list[dict[str, str]]:
    if parent is None:
        return []
    out: list[dict[str, str]] = []
    for child in list(parent):
        local = child.tag.split("}")[-1].lower()
        if local in {"category", "subject"}:
            value = (child.attrib.get("term") or child.attrib.get("label") or "".join(child.itertext())).strip()
            if value:
                out.append({"term": html.unescape(value)})
    return out


def parse_feed_xml(content: bytes) -> SimpleNamespace:
    root = ET.fromstring(content)
    root_local = root.tag.split("}")[-1].lower()

    feed_title = xml_text(root, ["title"])
    entries: list[dict[str, Any]] = []

    if root_local == "rss" or root.find("channel") is not None:
        channel = root.find("channel")
        if channel is None:
            channel = root
        feed_title = xml_text(channel, ["title"]) or feed_title
        raw_items = channel.findall("item")
    else:
        # Atom or RDF-like feeds: collect direct/descendant entry/item elements.
        raw_items = [el for el in root.iter() if el.tag.split("}")[-1].lower() in {"entry", "item"}]

    for item in raw_items:
        published_raw = (
            xml_text(item, ["pubDate", "published", "updated", "created", "date"])
            or xml_text(item, ["dc:date"])
        )
        entry = {
            "title": xml_text(item, ["title"]),
            "link": xml_link(item),
            "summary": xml_text(item, ["summary", "description", "encoded"]),
            "description": xml_text(item, ["description"]),
            "published": published_raw,
            "updated": xml_text(item, ["updated"]),
            "created": xml_text(item, ["created"]),
            "tags": xml_categories(item),
            "published_dt": parse_datetime_string(published_raw) if published_raw else None,
        }
        entries.append(entry)

    return SimpleNamespace(feed={"title": feed_title}, entries=entries)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_feed(url: str, timeout_sec: int) -> tuple[Any | None, str | None]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout_sec)
        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code}"
        content = resp.content or b""
        if not content.strip():
            return None, "empty response"
        try:
            parsed = parse_feed_xml(content)
        except Exception as e:
            return None, f"XML parse error: {e}"
        if not parsed.entries:
            return None, "no entries found"
        return parsed, None
    except Exception as e:
        return None, repr(e)


def recency_bonus(published_dt: datetime | None, now: datetime, lookback_hours: int) -> float:
    if published_dt is None:
        return 0.0
    age_h = max(0.0, (now - published_dt).total_seconds() / 3600)
    if age_h > lookback_hours:
        return 0.0
    # 0-6 points. Fresh items get more.
    return max(0.0, 6.0 * (1.0 - age_h / max(1, lookback_hours)))


def feed_position_bonus(position: int) -> float:
    # Top of a feed usually means editorial importance.
    return max(0.0, 10.0 - min(position, 10))


def build_item_from_entry(feed_cfg: dict[str, Any], feed_title: str, entry: Any, position: int) -> dict[str, Any]:
    published_dt = parse_entry_datetime(entry)
    link = entry.get("link", "") or ""
    summary = entry.get("summary", "") or entry.get("description", "") or ""
    return {
        "source": feed_cfg["source"],
        "feed_category": feed_cfg["category"],
        "feed_url": feed_cfg["url"],
        "source_weight": float(feed_cfg.get("weight", 1)),
        "feed_title": feed_title,
        "feed_position": int(position),
        "title": (entry.get("title", "") or "").strip(),
        "link": link,
        "dedupe_url": clean_url_for_dedupe(link),
        "summary": re.sub(r"\s+", " ", summary).strip(),
        "tags": entry_tags_text(entry),
        "published_dt": published_dt,
        "published": published_dt.isoformat() if published_dt else "",
    }


def collect_and_rank(
    selected_sources: list[str],
    selected_categories: list[str],
    lookback_hours: int,
    max_entries_per_feed: int,
    request_interval_sec: float,
    timeout_sec: int,
    include_undated: bool,
    include_summary_for_scoring: bool,
    min_unique_terms: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    feeds = [f for f in RSS_FEEDS if f["source"] in selected_sources and f["category"] in selected_categories]

    progress = st.progress(0, text="RSSを巡回中...") if feeds else None
    total_feeds = max(1, len(feeds))

    for feed_i, cfg in enumerate(feeds):
        if request_interval_sec > 0 and feed_i > 0:
            time.sleep(request_interval_sec)

        parsed, err = fetch_feed(cfg["url"], timeout_sec=timeout_sec)
        if err:
            errors.append({"source": cfg["source"], "category": cfg["category"], "url": cfg["url"], "error": err})
            if progress:
                progress.progress((feed_i + 1) / total_feeds, text=f"RSS巡回中... {feed_i + 1}/{len(feeds)}")
            continue

        feed_title = ""
        try:
            feed_title = parsed.feed.get("title", "") if parsed and hasattr(parsed, "feed") else ""
        except Exception:
            feed_title = ""

        entries = list(parsed.entries or [])[:max_entries_per_feed]
        for pos, entry in enumerate(entries):
            item = build_item_from_entry(cfg, feed_title, entry, pos)
            title = item["title"]
            if not is_probably_english_title(title):
                continue

            published_dt = item["published_dt"]
            if published_dt is None:
                if not include_undated:
                    continue
            elif published_dt < cutoff or published_dt > now + timedelta(hours=2):
                continue

            dedupe_key = item["dedupe_url"] or normalize_for_matching(title)
            if not dedupe_key or dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            hit = count_japan_terms(item, include_summary_for_scoring)
            if hit["unique_term_hits"] < min_unique_terms or hit["term_total_hits"] <= 0:
                continue

            cat_bonus = CATEGORY_BONUS.get(str(cfg["category"]).lower(), 0)
            r_bonus = recency_bonus(published_dt, now, lookback_hours)
            p_bonus = feed_position_bonus(pos)
            source_weight = float(cfg.get("weight", 1))

            # Main objective: Japan-specific term density, plus RSS editorial prominence.
            score = (
                3.0 * hit["term_weighted_hits"]
                + 5.0 * hit["unique_term_hits"]
                + 1.0 * source_weight
                + 0.8 * cat_bonus
                + 0.7 * p_bonus
                + 0.8 * r_bonus
            )

            rows.append({
                "score": round(score, 2),
                "term_total_hits": hit["term_total_hits"],
                "unique_term_hits": hit["unique_term_hits"],
                "matched_terms": ", ".join(hit["matched_terms"][:18]),
                "title": title,
                "source": item["source"],
                "category": item["feed_category"],
                "published": item["published"],
                "feed_position": item["feed_position"] + 1,
                "source_weight": source_weight,
                "url": item["link"],
            })

        if progress:
            progress.progress((feed_i + 1) / total_feeds, text=f"RSS巡回中... {feed_i + 1}/{len(feeds)}")

    if progress:
        progress.empty()

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            by=["score", "term_total_hits", "unique_term_hits", "published"],
            ascending=[False, False, False, False],
        ).head(MAX_RANKING).reset_index(drop=True)
        df.insert(0, "rank", range(1, len(df) + 1))

    err_df = pd.DataFrame(errors)
    return df, err_df


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL).encode("utf-8-sig")


def render_result_cards(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        st.markdown(f"### {int(row['rank'])}. [{row['title']}]({row['url']})")
        st.caption(
            f"score={row['score']} | hits={row['term_total_hits']} | "
            f"unique={row['unique_term_hits']} | {row['source']} / {row['category']} | "
            f"feed position={row['feed_position']} | {row['published'] or 'date unknown'}"
        )
        st.write("**Matched terms:** " + str(row["matched_terms"]))
        st.divider()


def main() -> None:
    st.set_page_config(page_title="海外日本バズRSSランキング", layout="wide")
    st.title("海外日本バズRSSランキング")
    st.caption(
        "海外RSSの英語タイトル記事だけを巡回し、日本特有300語がタイトル・URL・RSSメタデータに多く出る記事を上位30件で表示します。"
    )

    with st.sidebar:
        st.header("設定")
        st.caption(f"app version: {APP_VERSION}")

        lookback_hours = st.slider(
            "周回対象期間（直近何時間の記事を見るか）",
            min_value=1,
            max_value=24 * 14,
            value=72,
            step=1,
        )
        max_entries_per_feed = st.slider("RSSごとの最大取得件数", 0, 100, 40, 5)
        request_interval_sec = st.slider("RSSアクセス間隔 秒", 0.0, 5.0, 0.2, 0.1)
        timeout_sec = st.slider("RSSタイムアウト 秒", 3, 30, 12, 1)
        include_undated = st.checkbox("日付不明の記事も含める", value=False)
        include_summary_for_scoring = st.checkbox(
            "RSS summary/description もスコア計算に使う（本文取得はしない）",
            value=True,
        )
        min_unique_terms = st.slider("最低ユニーク命中語数", 1, 5, 1, 1)

        sources = sorted({f["source"] for f in RSS_FEEDS})
        categories = sorted({f["category"] for f in RSS_FEEDS})
        selected_sources = st.multiselect("巡回する媒体", sources, default=sources)
        selected_categories = st.multiselect("巡回するカテゴリ", categories, default=categories)

        st.markdown("---")
        st.caption(
            "除外済み: Guardian / Washington Post / Le Monde / Google News RSS / Reuters RSS。"
        )
        run = st.button("RSSを巡回してランキング作成", type="primary")

    st.info(
        "表示するのはタイトル・媒体・日時・URL・命中語・独自スコアのみです。記事本文や画像は取得・転載しません。"
    )

    if not run:
        st.subheader("仕様")
        st.write(
            f"登録RSS: {len(RSS_FEEDS)}本 / 日本特有語: {len(JAPAN_SPECIFIC_TERMS_300)}語 / ランキング上限: {MAX_RANKING}件"
        )
        st.write("サイドバーで期間・媒体・カテゴリを指定して実行してください。")
        with st.expander("日本特有語300語を見る"):
            st.write(", ".join(JAPAN_SPECIFIC_TERMS_300))
        return

    if max_entries_per_feed <= 0:
        st.warning("RSSごとの最大取得件数が0なので、取得対象がありません。")
        return
    if not selected_sources or not selected_categories:
        st.warning("媒体またはカテゴリが未選択です。")
        return

    with st.spinner("RSSを巡回してランキングを作成しています..."):
        df, err_df = collect_and_rank(
            selected_sources=selected_sources,
            selected_categories=selected_categories,
            lookback_hours=lookback_hours,
            max_entries_per_feed=max_entries_per_feed,
            request_interval_sec=request_interval_sec,
            timeout_sec=timeout_sec,
            include_undated=include_undated,
            include_summary_for_scoring=include_summary_for_scoring,
            min_unique_terms=min_unique_terms,
        )

    st.subheader("ランキング")
    if df.empty:
        st.warning("条件に合う記事が見つかりませんでした。期間を長くする、取得件数を増やす、媒体カテゴリを増やすなどを試してください。")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("表示件数", len(df))
        c2.metric("最高スコア", float(df["score"].max()))
        c3.metric("対象期間", f"直近{lookback_hours}時間")

        st.download_button(
            "ランキングCSVをダウンロード",
            data=df_to_csv_bytes(df),
            file_name="rss_japan_buzz_ranking.csv",
            mime="text/csv",
        )

        display_cols = [
            "rank",
            "score",
            "term_total_hits",
            "unique_term_hits",
            "matched_terms",
            "title",
            "source",
            "category",
            "published",
            "url",
        ]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("リンク付き表示")
        render_result_cards(df)

    if not err_df.empty:
        with st.expander(f"取得エラー・失敗RSS（{len(err_df)}件）"):
            st.dataframe(err_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
