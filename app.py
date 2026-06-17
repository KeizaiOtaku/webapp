# app.py
# Streamlit app: English overseas RSS Japan-buzz ranker
# - No article-body scraping
# - Excludes RSS sources previously identified as clearly restricted for commercial/non-commercial use
# - Ranks English RSS items by Japan-specific 1000-term hits in title / URL / metadata
# - Repeated hits of the same term use geometric decay: 1.0, 0.5, 0.25, ...
# - Before global ranking, items in the same RSS category are also decayed: 1st=1.0, 2nd=0.5, 3rd=0.25, ...

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

APP_VERSION = "2026-06-17-rss-japan-buzz-1000-repeat-category-decay-limit100"
DEFAULT_RANKING_LIMIT = 30
MAX_RANKING_LIMIT = 100

# Japan / Japanese are intentionally NOT included here.
# The term list is weighted and category-balanced:
#   news 500 / business 200 / pop_culture 100 / anime 50 / game 50 / tourism 100 = 1000 terms.
# Terms containing "Japan" or "Japanese" are intentionally excluded.
JAPAN_SPECIFIC_TERMS_1000_RECORDS = [{'id': 1, 'category': 'news', 'term': 'LDP', 'weight': 1.0},
 {'id': 2, 'category': 'news', 'term': 'Komeito', 'weight': 1.0},
 {'id': 3, 'category': 'news', 'term': 'CDP', 'weight': 1.0},
 {'id': 4, 'category': 'news', 'term': 'Constitutional Democratic Party', 'weight': 1.0},
 {'id': 5, 'category': 'news', 'term': 'DPFP', 'weight': 1.0},
 {'id': 6, 'category': 'news', 'term': 'Ishin', 'weight': 1.0},
 {'id': 7, 'category': 'news', 'term': 'Reiwa Shinsengumi', 'weight': 1.0},
 {'id': 8, 'category': 'news', 'term': 'Communist Party', 'weight': 1.0},
 {'id': 9, 'category': 'news', 'term': 'Social Democratic Party', 'weight': 1.0},
 {'id': 10, 'category': 'news', 'term': 'Sangiin', 'weight': 1.0},
 {'id': 11, 'category': 'news', 'term': 'Shugiin', 'weight': 1.0},
 {'id': 12, 'category': 'news', 'term': 'Diet', 'weight': 1.0},
 {'id': 13, 'category': 'news', 'term': 'National Diet', 'weight': 1.0},
 {'id': 14, 'category': 'news', 'term': 'Lower House', 'weight': 1.0},
 {'id': 15, 'category': 'news', 'term': 'Upper House', 'weight': 1.0},
 {'id': 16, 'category': 'news', 'term': 'House of Representatives', 'weight': 1.0},
 {'id': 17, 'category': 'news', 'term': 'House of Councillors', 'weight': 1.0},
 {'id': 18, 'category': 'news', 'term': 'Kantei', 'weight': 1.0},
 {'id': 19, 'category': 'news', 'term': 'Kokkai', 'weight': 1.0},
 {'id': 20, 'category': 'news', 'term': 'Kasumigaseki', 'weight': 1.0},
 {'id': 21, 'category': 'news', 'term': 'Nagatacho', 'weight': 1.0},
 {'id': 22, 'category': 'news', 'term': 'Cabinet Secretariat', 'weight': 1.0},
 {'id': 23, 'category': 'news', 'term': 'Cabinet Office', 'weight': 1.0},
 {'id': 24, 'category': 'news', 'term': 'Chief Cabinet Secretary', 'weight': 1.0},
 {'id': 25, 'category': 'news', 'term': 'Ministry of Foreign Affairs', 'weight': 1.0},
 {'id': 26, 'category': 'news', 'term': 'MOFA', 'weight': 1.0},
 {'id': 27, 'category': 'news', 'term': 'Ministry of Finance', 'weight': 1.0},
 {'id': 28, 'category': 'news', 'term': 'MOF', 'weight': 1.0},
 {'id': 29, 'category': 'news', 'term': 'Ministry of Economy Trade and Industry', 'weight': 1.0},
 {'id': 30, 'category': 'news', 'term': 'METI', 'weight': 1.0},
 {'id': 31, 'category': 'news', 'term': 'Ministry of Defense', 'weight': 1.0},
 {'id': 32, 'category': 'news', 'term': 'MOD', 'weight': 1.0},
 {'id': 33, 'category': 'news', 'term': 'Ministry of Internal Affairs', 'weight': 1.0},
 {'id': 34, 'category': 'news', 'term': 'MIC', 'weight': 1.0},
 {'id': 35, 'category': 'news', 'term': 'Ministry of Justice', 'weight': 1.0},
 {'id': 36, 'category': 'news', 'term': 'MOJ', 'weight': 1.0},
 {'id': 37, 'category': 'news', 'term': 'Ministry of Health Labour and Welfare', 'weight': 1.0},
 {'id': 38, 'category': 'news', 'term': 'MHLW', 'weight': 1.0},
 {'id': 39, 'category': 'news', 'term': 'Ministry of Education Culture Sports Science and Technology', 'weight': 1.0},
 {'id': 40, 'category': 'news', 'term': 'MEXT', 'weight': 1.0},
 {'id': 41, 'category': 'news', 'term': 'Ministry of Agriculture Forestry and Fisheries', 'weight': 1.0},
 {'id': 42, 'category': 'news', 'term': 'MAFF', 'weight': 1.0},
 {'id': 43, 'category': 'news', 'term': 'Financial Services Agency', 'weight': 1.0},
 {'id': 44, 'category': 'news', 'term': 'FSA', 'weight': 1.0},
 {'id': 45, 'category': 'news', 'term': 'National Police Agency', 'weight': 1.0},
 {'id': 46, 'category': 'news', 'term': 'NPA', 'weight': 1.0},
 {'id': 47, 'category': 'news', 'term': 'Public Security Intelligence Agency', 'weight': 1.0},
 {'id': 48, 'category': 'news', 'term': 'PSIA', 'weight': 1.0},
 {'id': 49, 'category': 'news', 'term': 'Imperial Household Agency', 'weight': 1.0},
 {'id': 50, 'category': 'news', 'term': 'Board of Audit', 'weight': 1.0},
 {'id': 51, 'category': 'news', 'term': 'Supreme Court', 'weight': 1.0},
 {'id': 52, 'category': 'news', 'term': 'Tokyo District Court', 'weight': 1.0},
 {'id': 53, 'category': 'news', 'term': 'Tokyo High Court', 'weight': 1.0},
 {'id': 54, 'category': 'news', 'term': 'Public Prosecutors Office', 'weight': 1.0},
 {'id': 55, 'category': 'news', 'term': 'Special Investigation Department', 'weight': 1.0},
 {'id': 56, 'category': 'news', 'term': 'Election Administration Commission', 'weight': 1.0},
 {'id': 57, 'category': 'news', 'term': 'single-seat districts', 'weight': 1.0},
 {'id': 58, 'category': 'news', 'term': 'proportional representation', 'weight': 1.0},
 {'id': 59, 'category': 'news', 'term': 'snap election', 'weight': 1.0},
 {'id': 60, 'category': 'news', 'term': 'no-confidence motion', 'weight': 1.0},
 {'id': 61, 'category': 'news', 'term': 'coalition government', 'weight': 1.0},
 {'id': 62, 'category': 'news', 'term': 'cabinet approval', 'weight': 1.0},
 {'id': 63, 'category': 'news', 'term': 'cabinet reshuffle', 'weight': 1.0},
 {'id': 64, 'category': 'news', 'term': 'leadership election', 'weight': 1.0},
 {'id': 65, 'category': 'news', 'term': 'party president election', 'weight': 1.0},
 {'id': 66, 'category': 'news', 'term': 'local assembly', 'weight': 1.0},
 {'id': 67, 'category': 'news', 'term': 'prefectural governor', 'weight': 1.0},
 {'id': 68, 'category': 'news', 'term': 'mayoral election', 'weight': 1.0},
 {'id': 69, 'category': 'news', 'term': 'Tokyo governor', 'weight': 1.0},
 {'id': 70, 'category': 'news', 'term': 'Osaka governor', 'weight': 1.0},
 {'id': 71, 'category': 'news', 'term': 'Okinawa governor', 'weight': 1.0},
 {'id': 72, 'category': 'news', 'term': 'Hokkaido governor', 'weight': 1.0},
 {'id': 73, 'category': 'news', 'term': 'referendum', 'weight': 1.0},
 {'id': 74, 'category': 'news', 'term': 'constitutional revision', 'weight': 1.0},
 {'id': 75, 'category': 'news', 'term': 'Article 9', 'weight': 1.0},
 {'id': 76, 'category': 'news', 'term': 'pacifist constitution', 'weight': 1.0},
 {'id': 77, 'category': 'news', 'term': 'security legislation', 'weight': 1.0},
 {'id': 78, 'category': 'news', 'term': 'state secrecy law', 'weight': 1.0},
 {'id': 79, 'category': 'news', 'term': 'anti-conspiracy law', 'weight': 1.0},
 {'id': 80, 'category': 'news', 'term': 'My Number', 'weight': 1.0},
 {'id': 81, 'category': 'news', 'term': 'My Number card', 'weight': 1.0},
 {'id': 82, 'category': 'news', 'term': 'resident registry', 'weight': 1.0},
 {'id': 83, 'category': 'news', 'term': 'koseki', 'weight': 1.0},
 {'id': 84, 'category': 'news', 'term': 'family registry', 'weight': 1.0},
 {'id': 85, 'category': 'news', 'term': 'civil code', 'weight': 1.0},
 {'id': 86, 'category': 'news', 'term': 'penal code', 'weight': 1.0},
 {'id': 87, 'category': 'news', 'term': 'immigration control', 'weight': 1.0},
 {'id': 88, 'category': 'news', 'term': 'visa waiver', 'weight': 1.0},
 {'id': 89, 'category': 'news', 'term': 'residence card', 'weight': 1.0},
 {'id': 90, 'category': 'news', 'term': 'technical intern', 'weight': 1.0},
 {'id': 91, 'category': 'news', 'term': 'specified skilled worker', 'weight': 1.0},
 {'id': 92, 'category': 'news', 'term': 'asylum seeker', 'weight': 1.0},
 {'id': 93, 'category': 'news', 'term': 'foreign trainee', 'weight': 1.0},
 {'id': 94, 'category': 'news', 'term': 'labor standards office', 'weight': 1.0},
 {'id': 95, 'category': 'news', 'term': 'Consumer Affairs Agency', 'weight': 1.0},
 {'id': 96, 'category': 'news', 'term': 'Fair Trade Commission', 'weight': 1.0},
 {'id': 97, 'category': 'news', 'term': 'JFTC', 'weight': 1.0},
 {'id': 98, 'category': 'news', 'term': 'Personal Information Protection Commission', 'weight': 1.0},
 {'id': 99, 'category': 'news', 'term': 'Digital Agency', 'weight': 1.0},
 {'id': 100, 'category': 'news', 'term': 'Reconstruction Agency', 'weight': 1.0},
 {'id': 101, 'category': 'news', 'term': 'Children and Families Agency', 'weight': 1.0},
 {'id': 102, 'category': 'news', 'term': 'Nuclear Regulation Authority', 'weight': 1.0},
 {'id': 103, 'category': 'news', 'term': 'NRA', 'weight': 1.0},
 {'id': 104, 'category': 'news', 'term': 'Agency for Cultural Affairs', 'weight': 1.0},
 {'id': 105, 'category': 'news', 'term': 'tourism agency', 'weight': 1.0},
 {'id': 106, 'category': 'news', 'term': 'national census', 'weight': 1.0},
 {'id': 107, 'category': 'news', 'term': 'Basic Resident Register', 'weight': 1.0},
 {'id': 108, 'category': 'news', 'term': 'official gazette', 'weight': 1.0},
 {'id': 109, 'category': 'news', 'term': 'yen', 'weight': 1.0},
 {'id': 110, 'category': 'news', 'term': 'BOJ', 'weight': 1.0},
 {'id': 111, 'category': 'news', 'term': 'Nikkei', 'weight': 1.0},
 {'id': 112, 'category': 'news', 'term': 'TOPIX', 'weight': 1.0},
 {'id': 113, 'category': 'news', 'term': 'TSE', 'weight': 1.0},
 {'id': 114, 'category': 'news', 'term': 'Tokyo Stock Exchange', 'weight': 1.0},
 {'id': 115, 'category': 'news', 'term': 'JGB', 'weight': 1.0},
 {'id': 116, 'category': 'news', 'term': 'Tankan', 'weight': 1.0},
 {'id': 117, 'category': 'news', 'term': 'core CPI', 'weight': 1.0},
 {'id': 118, 'category': 'news', 'term': 'deflation', 'weight': 1.0},
 {'id': 119, 'category': 'news', 'term': 'reflation', 'weight': 1.0},
 {'id': 120, 'category': 'news', 'term': 'yield curve control', 'weight': 1.0},
 {'id': 121, 'category': 'news', 'term': 'negative interest rates', 'weight': 1.0},
 {'id': 122, 'category': 'news', 'term': 'policy rate', 'weight': 1.0},
 {'id': 123, 'category': 'news', 'term': 'ultra-low rates', 'weight': 1.0},
 {'id': 124, 'category': 'news', 'term': 'yen intervention', 'weight': 1.0},
 {'id': 125, 'category': 'news', 'term': 'currency intervention', 'weight': 1.0},
 {'id': 126, 'category': 'news', 'term': 'yen carry trade', 'weight': 1.0},
 {'id': 127, 'category': 'news', 'term': 'weak yen', 'weight': 1.0},
 {'id': 128, 'category': 'news', 'term': 'strong yen', 'weight': 1.0},
 {'id': 129, 'category': 'news', 'term': 'wage hike', 'weight': 1.0},
 {'id': 130, 'category': 'news', 'term': 'shunto', 'weight': 1.0},
 {'id': 131, 'category': 'news', 'term': 'spring wage negotiations', 'weight': 1.0},
 {'id': 132, 'category': 'news', 'term': 'base pay hike', 'weight': 1.0},
 {'id': 133, 'category': 'news', 'term': 'minimum wage', 'weight': 1.0},
 {'id': 134, 'category': 'news', 'term': 'consumption tax', 'weight': 1.0},
 {'id': 135, 'category': 'news', 'term': 'sales tax hike', 'weight': 1.0},
 {'id': 136, 'category': 'news', 'term': 'fiscal stimulus', 'weight': 1.0},
 {'id': 137, 'category': 'news', 'term': 'supplementary budget', 'weight': 1.0},
 {'id': 138, 'category': 'news', 'term': 'primary balance', 'weight': 1.0},
 {'id': 139, 'category': 'news', 'term': 'public debt', 'weight': 1.0},
 {'id': 140, 'category': 'news', 'term': 'pension reform', 'weight': 1.0},
 {'id': 141, 'category': 'news', 'term': 'national pension', 'weight': 1.0},
 {'id': 142, 'category': 'news', 'term': 'employee pension', 'weight': 1.0},
 {'id': 143, 'category': 'news', 'term': 'social security costs', 'weight': 1.0},
 {'id': 144, 'category': 'news', 'term': 'health insurance premiums', 'weight': 1.0},
 {'id': 145, 'category': 'news', 'term': 'long-term care insurance', 'weight': 1.0},
 {'id': 146, 'category': 'news', 'term': 'child allowance', 'weight': 1.0},
 {'id': 147, 'category': 'news', 'term': 'tuition-free program', 'weight': 1.0},
 {'id': 148, 'category': 'news', 'term': 'nursing care', 'weight': 1.0},
 {'id': 149, 'category': 'news', 'term': 'daycare shortage', 'weight': 1.0},
 {'id': 150, 'category': 'news', 'term': 'waiting list children', 'weight': 1.0},
 {'id': 151, 'category': 'news', 'term': 'aging population', 'weight': 1.0},
 {'id': 152, 'category': 'news', 'term': 'super-aged society', 'weight': 1.0},
 {'id': 153, 'category': 'news', 'term': 'birth rate', 'weight': 1.0},
 {'id': 154, 'category': 'news', 'term': 'fertility rate', 'weight': 1.0},
 {'id': 155, 'category': 'news', 'term': 'depopulation', 'weight': 1.0},
 {'id': 156, 'category': 'news', 'term': 'population decline', 'weight': 1.0},
 {'id': 157, 'category': 'news', 'term': 'labor shortage', 'weight': 1.0},
 {'id': 158, 'category': 'news', 'term': 'overtime cap', 'weight': 1.0},
 {'id': 159, 'category': 'news', 'term': 'karoshi', 'weight': 1.0},
 {'id': 160, 'category': 'news', 'term': 'death from overwork', 'weight': 1.0},
 {'id': 161, 'category': 'news', 'term': 'power harassment', 'weight': 1.0},
 {'id': 162, 'category': 'news', 'term': 'maternity harassment', 'weight': 1.0},
 {'id': 163, 'category': 'news', 'term': 'black company', 'weight': 1.0},
 {'id': 164, 'category': 'news', 'term': 'salaryman', 'weight': 1.0},
 {'id': 165, 'category': 'news', 'term': 'office worker', 'weight': 1.0},
 {'id': 166, 'category': 'news', 'term': 'freeter', 'weight': 1.0},
 {'id': 167, 'category': 'news', 'term': 'NEET', 'weight': 1.0},
 {'id': 168, 'category': 'news', 'term': 'hikikomori', 'weight': 1.0},
 {'id': 169, 'category': 'news', 'term': 'kodokushi', 'weight': 1.0},
 {'id': 170, 'category': 'news', 'term': 'lonely death', 'weight': 1.0},
 {'id': 171, 'category': 'news', 'term': 'single-person households', 'weight': 1.0},
 {'id': 172, 'category': 'news', 'term': 'empty homes', 'weight': 1.0},
 {'id': 173, 'category': 'news', 'term': 'akiya', 'weight': 1.0},
 {'id': 174, 'category': 'news', 'term': 'rural depopulation', 'weight': 1.0},
 {'id': 175, 'category': 'news', 'term': 'regional revitalization', 'weight': 1.0},
 {'id': 176, 'category': 'news', 'term': 'furusato tax', 'weight': 1.0},
 {'id': 177, 'category': 'news', 'term': 'hometown tax', 'weight': 1.0},
 {'id': 178, 'category': 'news', 'term': 'inbound tourism', 'weight': 1.0},
 {'id': 179, 'category': 'news', 'term': 'overtourism', 'weight': 1.0},
 {'id': 180, 'category': 'news', 'term': 'cashless payments', 'weight': 1.0},
 {'id': 181, 'category': 'news', 'term': 'point economy', 'weight': 1.0},
 {'id': 182, 'category': 'news', 'term': 'convenience store chains', 'weight': 1.0},
 {'id': 183, 'category': 'news', 'term': 'delivery robotics', 'weight': 1.0},
 {'id': 184, 'category': 'news', 'term': 'driver shortage', 'weight': 1.0},
 {'id': 185, 'category': 'news', 'term': 'logistics crisis', 'weight': 1.0},
 {'id': 186, 'category': 'news', 'term': '2024 logistics problem', 'weight': 1.0},
 {'id': 187, 'category': 'news', 'term': 'rice prices', 'weight': 1.0},
 {'id': 188, 'category': 'news', 'term': 'rice shortage', 'weight': 1.0},
 {'id': 189, 'category': 'news', 'term': 'food self-sufficiency', 'weight': 1.0},
 {'id': 190, 'category': 'news', 'term': 'energy security', 'weight': 1.0},
 {'id': 191, 'category': 'news', 'term': 'LNG imports', 'weight': 1.0},
 {'id': 192, 'category': 'news', 'term': 'nuclear restart', 'weight': 1.0},
 {'id': 193, 'category': 'news', 'term': 'renewable surcharge', 'weight': 1.0},
 {'id': 194, 'category': 'news', 'term': 'solar panel rules', 'weight': 1.0},
 {'id': 195, 'category': 'news', 'term': 'offshore wind', 'weight': 1.0},
 {'id': 196, 'category': 'news', 'term': 'hydrogen strategy', 'weight': 1.0},
 {'id': 197, 'category': 'news', 'term': 'ammonia co-firing', 'weight': 1.0},
 {'id': 198, 'category': 'news', 'term': 'semiconductor subsidies', 'weight': 1.0},
 {'id': 199, 'category': 'news', 'term': 'economic security law', 'weight': 1.0},
 {'id': 200, 'category': 'news', 'term': 'supply chain resilience', 'weight': 1.0},
 {'id': 201, 'category': 'news', 'term': 'critical minerals', 'weight': 1.0},
 {'id': 202, 'category': 'news', 'term': 'rare earths', 'weight': 1.0},
 {'id': 203, 'category': 'news', 'term': 'export controls', 'weight': 1.0},
 {'id': 204, 'category': 'news', 'term': 'trade surplus', 'weight': 1.0},
 {'id': 205, 'category': 'news', 'term': 'trade deficit', 'weight': 1.0},
 {'id': 206, 'category': 'news', 'term': 'current account surplus', 'weight': 1.0},
 {'id': 207, 'category': 'news', 'term': 'household spending', 'weight': 1.0},
 {'id': 208, 'category': 'news', 'term': 'real wages', 'weight': 1.0},
 {'id': 209, 'category': 'news', 'term': 'land prices', 'weight': 1.0},
 {'id': 210, 'category': 'news', 'term': 'condo prices', 'weight': 1.0},
 {'id': 211, 'category': 'news', 'term': 'Tokyo condo market', 'weight': 1.0},
 {'id': 212, 'category': 'news', 'term': 'urban redevelopment', 'weight': 1.0},
 {'id': 213, 'category': 'news', 'term': 'SDF', 'weight': 1.0},
 {'id': 214, 'category': 'news', 'term': 'JSDF', 'weight': 1.0},
 {'id': 215, 'category': 'news', 'term': 'Self-Defense Forces', 'weight': 1.0},
 {'id': 216, 'category': 'news', 'term': 'JASDF', 'weight': 1.0},
 {'id': 217, 'category': 'news', 'term': 'JGSDF', 'weight': 1.0},
 {'id': 218, 'category': 'news', 'term': 'JMSDF', 'weight': 1.0},
 {'id': 219, 'category': 'news', 'term': 'Maritime Self-Defense Force', 'weight': 1.0},
 {'id': 220, 'category': 'news', 'term': 'Air Self-Defense Force', 'weight': 1.0},
 {'id': 221, 'category': 'news', 'term': 'Ground Self-Defense Force', 'weight': 1.0},
 {'id': 222, 'category': 'news', 'term': 'Aegis destroyer', 'weight': 1.0},
 {'id': 223, 'category': 'news', 'term': 'Aegis Ashore', 'weight': 1.0},
 {'id': 224, 'category': 'news', 'term': 'Tomahawk missiles', 'weight': 1.0},
 {'id': 225, 'category': 'news', 'term': 'counterstrike capability', 'weight': 1.0},
 {'id': 226, 'category': 'news', 'term': 'defense budget', 'weight': 1.0},
 {'id': 227, 'category': 'news', 'term': 'defense buildup', 'weight': 1.0},
 {'id': 228, 'category': 'news', 'term': 'security treaty', 'weight': 1.0},
 {'id': 229, 'category': 'news', 'term': 'US Forces in Okinawa', 'weight': 1.0},
 {'id': 230, 'category': 'news', 'term': 'Okinawa bases', 'weight': 1.0},
 {'id': 231, 'category': 'news', 'term': 'Futenma', 'weight': 1.0},
 {'id': 232, 'category': 'news', 'term': 'Henoko', 'weight': 1.0},
 {'id': 233, 'category': 'news', 'term': 'Kadena', 'weight': 1.0},
 {'id': 234, 'category': 'news', 'term': 'Yokosuka', 'weight': 1.0},
 {'id': 235, 'category': 'news', 'term': 'Sasebo', 'weight': 1.0},
 {'id': 236, 'category': 'news', 'term': 'Misawa Air Base', 'weight': 1.0},
 {'id': 237, 'category': 'news', 'term': 'Iwakuni', 'weight': 1.0},
 {'id': 238, 'category': 'news', 'term': 'Camp Schwab', 'weight': 1.0},
 {'id': 239, 'category': 'news', 'term': 'Camp Hansen', 'weight': 1.0},
 {'id': 240, 'category': 'news', 'term': 'Yokota Air Base', 'weight': 1.0},
 {'id': 241, 'category': 'news', 'term': 'SOFA', 'weight': 1.0},
 {'id': 242, 'category': 'news', 'term': 'Status of Forces Agreement', 'weight': 1.0},
 {'id': 243, 'category': 'news', 'term': 'Senkaku', 'weight': 1.0},
 {'id': 244, 'category': 'news', 'term': 'Diaoyu dispute', 'weight': 1.0},
 {'id': 245, 'category': 'news', 'term': 'East China Sea', 'weight': 1.0},
 {'id': 246, 'category': 'news', 'term': 'Sea of Okhotsk', 'weight': 1.0},
 {'id': 247, 'category': 'news', 'term': 'Northern Territories', 'weight': 1.0},
 {'id': 248, 'category': 'news', 'term': 'Kuril Islands dispute', 'weight': 1.0},
 {'id': 249, 'category': 'news', 'term': 'Takeshima', 'weight': 1.0},
 {'id': 250, 'category': 'news', 'term': 'Dokdo dispute', 'weight': 1.0},
 {'id': 251, 'category': 'news', 'term': 'comfort women issue', 'weight': 1.0},
 {'id': 252, 'category': 'news', 'term': 'wartime labor issue', 'weight': 1.0},
 {'id': 253, 'category': 'news', 'term': 'history textbook issue', 'weight': 1.0},
 {'id': 254, 'category': 'news', 'term': 'Yasukuni', 'weight': 1.0},
 {'id': 255, 'category': 'news', 'term': 'Yasukuni Shrine', 'weight': 1.0},
 {'id': 256, 'category': 'news', 'term': 'Nanjing dispute', 'weight': 1.0},
 {'id': 257, 'category': 'news', 'term': 'abduction issue', 'weight': 1.0},
 {'id': 258, 'category': 'news', 'term': 'North Korean abductions', 'weight': 1.0},
 {'id': 259, 'category': 'news', 'term': 'missile alert', 'weight': 1.0},
 {'id': 260, 'category': 'news', 'term': 'J-Alert', 'weight': 1.0},
 {'id': 261, 'category': 'news', 'term': 'air defense identification zone', 'weight': 1.0},
 {'id': 262, 'category': 'news', 'term': 'Quad', 'weight': 1.0},
 {'id': 263, 'category': 'news', 'term': 'FOIP', 'weight': 1.0},
 {'id': 264, 'category': 'news', 'term': 'Free and Open Indo-Pacific', 'weight': 1.0},
 {'id': 265, 'category': 'news', 'term': 'Indo-Pacific strategy', 'weight': 1.0},
 {'id': 266, 'category': 'news', 'term': 'AUKUS cooperation', 'weight': 1.0},
 {'id': 267, 'category': 'news', 'term': 'G7 Hiroshima', 'weight': 1.0},
 {'id': 268, 'category': 'news', 'term': 'Hiroshima summit', 'weight': 1.0},
 {'id': 269, 'category': 'news', 'term': 'CPTPP', 'weight': 1.0},
 {'id': 270, 'category': 'news', 'term': 'RCEP', 'weight': 1.0},
 {'id': 271, 'category': 'news', 'term': 'IPEF', 'weight': 1.0},
 {'id': 272, 'category': 'news', 'term': 'ODA charter', 'weight': 1.0},
 {'id': 273, 'category': 'news', 'term': 'development aid', 'weight': 1.0},
 {'id': 274, 'category': 'news', 'term': 'peacekeeping operations', 'weight': 1.0},
 {'id': 275, 'category': 'news', 'term': 'PKO', 'weight': 1.0},
 {'id': 276, 'category': 'news', 'term': 'UN Security Council bid', 'weight': 1.0},
 {'id': 277, 'category': 'news', 'term': 'whaling dispute', 'weight': 1.0},
 {'id': 278, 'category': 'news', 'term': 'IWC withdrawal', 'weight': 1.0},
 {'id': 279, 'category': 'news', 'term': 'bluefin tuna quotas', 'weight': 1.0},
 {'id': 280, 'category': 'news', 'term': 'fisheries dispute', 'weight': 1.0},
 {'id': 281, 'category': 'news', 'term': 'treated water release', 'weight': 1.0},
 {'id': 282, 'category': 'news', 'term': 'ALPS treated water', 'weight': 1.0},
 {'id': 283, 'category': 'news', 'term': 'Fukushima water release', 'weight': 1.0},
 {'id': 284, 'category': 'news', 'term': 'nuclear safety inspection', 'weight': 1.0},
 {'id': 285, 'category': 'news', 'term': 'IAEA review', 'weight': 1.0},
 {'id': 286, 'category': 'news', 'term': 'sanctions package', 'weight': 1.0},
 {'id': 287, 'category': 'news', 'term': 'export whitelist', 'weight': 1.0},
 {'id': 288, 'category': 'news', 'term': 'strategic dialogue', 'weight': 1.0},
 {'id': 289, 'category': 'news', 'term': '2+2 talks', 'weight': 1.0},
 {'id': 290, 'category': 'news', 'term': 'trilateral summit', 'weight': 1.0},
 {'id': 291, 'category': 'news', 'term': 'Shangri-La Dialogue', 'weight': 1.0},
 {'id': 292, 'category': 'news', 'term': 'Fukushima Daiichi', 'weight': 1.0},
 {'id': 293, 'category': 'news', 'term': 'Fukushima nuclear plant', 'weight': 1.0},
 {'id': 294, 'category': 'news', 'term': 'Fukushima meltdown', 'weight': 1.0},
 {'id': 295, 'category': 'news', 'term': 'TEPCO', 'weight': 1.0},
 {'id': 296, 'category': 'news', 'term': 'Nankai Trough', 'weight': 1.0},
 {'id': 297, 'category': 'news', 'term': 'Kanto quake', 'weight': 1.0},
 {'id': 298, 'category': 'news', 'term': 'Great East Earthquake', 'weight': 1.0},
 {'id': 299, 'category': 'news', 'term': 'Tohoku quake', 'weight': 1.0},
 {'id': 300, 'category': 'news', 'term': 'Kobe quake', 'weight': 1.0},
 {'id': 301, 'category': 'news', 'term': 'Kumamoto quake', 'weight': 1.0},
 {'id': 302, 'category': 'news', 'term': 'Noto Peninsula quake', 'weight': 1.0},
 {'id': 303, 'category': 'news', 'term': 'earthquake early warning', 'weight': 1.0},
 {'id': 304, 'category': 'news', 'term': 'seismic intensity', 'weight': 1.0},
 {'id': 305, 'category': 'news', 'term': 'shindo', 'weight': 1.0},
 {'id': 306, 'category': 'news', 'term': 'tsunami warning', 'weight': 1.0},
 {'id': 307, 'category': 'news', 'term': 'tsunami advisory', 'weight': 1.0},
 {'id': 308, 'category': 'news', 'term': 'evacuation order', 'weight': 1.0},
 {'id': 309, 'category': 'news', 'term': 'emergency alert', 'weight': 1.0},
 {'id': 310, 'category': 'news', 'term': 'typhoon', 'weight': 1.0},
 {'id': 311, 'category': 'news', 'term': 'landslide', 'weight': 1.0},
 {'id': 312, 'category': 'news', 'term': 'volcanic eruption', 'weight': 1.0},
 {'id': 313, 'category': 'news', 'term': 'Mount Aso', 'weight': 1.0},
 {'id': 314, 'category': 'news', 'term': 'Sakurajima', 'weight': 1.0},
 {'id': 315, 'category': 'news', 'term': 'Mount Ontake', 'weight': 1.0},
 {'id': 316, 'category': 'news', 'term': 'Mount Unzen', 'weight': 1.0},
 {'id': 317, 'category': 'news', 'term': 'Kirishima', 'weight': 1.0},
 {'id': 318, 'category': 'news', 'term': 'Kilauea no', 'weight': 1.0},
 {'id': 319, 'category': 'news', 'term': 'heavy rain warning', 'weight': 1.0},
 {'id': 320, 'category': 'news', 'term': 'linear rainband', 'weight': 1.0},
 {'id': 321, 'category': 'news', 'term': 'heatstroke alert', 'weight': 1.0},
 {'id': 322, 'category': 'news', 'term': 'disaster shelters', 'weight': 1.0},
 {'id': 323, 'category': 'news', 'term': 'temporary housing', 'weight': 1.0},
 {'id': 324, 'category': 'news', 'term': 'seawall', 'weight': 1.0},
 {'id': 325, 'category': 'news', 'term': 'nuclear evacuation zone', 'weight': 1.0},
 {'id': 326, 'category': 'news', 'term': 'radiation monitoring', 'weight': 1.0},
 {'id': 327, 'category': 'news', 'term': 'decontamination work', 'weight': 1.0},
 {'id': 328, 'category': 'news', 'term': 'contaminated soil', 'weight': 1.0},
 {'id': 329, 'category': 'news', 'term': 'reconstruction bonds', 'weight': 1.0},
 {'id': 330, 'category': 'news', 'term': 'resilience planning', 'weight': 1.0},
 {'id': 331, 'category': 'news', 'term': 'bullet train suspension', 'weight': 1.0},
 {'id': 332, 'category': 'news', 'term': 'Shinkansen disruption', 'weight': 1.0},
 {'id': 333, 'category': 'news', 'term': 'railway timetable', 'weight': 1.0},
 {'id': 334, 'category': 'news', 'term': 'subway attack', 'weight': 1.0},
 {'id': 335, 'category': 'news', 'term': 'Sarin attack', 'weight': 1.0},
 {'id': 336, 'category': 'news', 'term': 'Aum Shinrikyo', 'weight': 1.0},
 {'id': 337, 'category': 'news', 'term': 'Aleph group', 'weight': 1.0},
 {'id': 338, 'category': 'news', 'term': 'knife attack', 'weight': 1.0},
 {'id': 339, 'category': 'news', 'term': 'arson attack', 'weight': 1.0},
 {'id': 340, 'category': 'news', 'term': 'cyberattack', 'weight': 1.0},
 {'id': 341, 'category': 'news', 'term': 'ransomware attack', 'weight': 1.0},
 {'id': 342, 'category': 'news', 'term': 'data breach', 'weight': 1.0},
 {'id': 343, 'category': 'news', 'term': 'Kobayashi red yeast rice', 'weight': 1.0},
 {'id': 344, 'category': 'news', 'term': 'beni koji scandal', 'weight': 1.0},
 {'id': 345, 'category': 'news', 'term': 'food poisoning', 'weight': 1.0},
 {'id': 346, 'category': 'news', 'term': 'avian flu', 'weight': 1.0},
 {'id': 347, 'category': 'news', 'term': 'swine fever', 'weight': 1.0},
 {'id': 348, 'category': 'news', 'term': 'bear attacks', 'weight': 1.0},
 {'id': 349, 'category': 'news', 'term': 'wild boar damage', 'weight': 1.0},
 {'id': 350, 'category': 'news', 'term': 'crowd crush', 'weight': 1.0},
 {'id': 351, 'category': 'news', 'term': 'school lunch issue', 'weight': 1.0},
 {'id': 352, 'category': 'news', 'term': 'unexploded ordnance', 'weight': 1.0},
 {'id': 353, 'category': 'news', 'term': 'ordnance disposal', 'weight': 1.0},
 {'id': 354, 'category': 'news', 'term': 'space agency', 'weight': 1.0},
 {'id': 355, 'category': 'news', 'term': 'JAXA', 'weight': 1.0},
 {'id': 356, 'category': 'news', 'term': 'H3 rocket', 'weight': 1.0},
 {'id': 357, 'category': 'news', 'term': 'H2A rocket', 'weight': 1.0},
 {'id': 358, 'category': 'news', 'term': 'SLIM moon lander', 'weight': 1.0},
 {'id': 359, 'category': 'news', 'term': 'Hayabusa2', 'weight': 1.0},
 {'id': 360, 'category': 'news', 'term': 'Kibo module', 'weight': 1.0},
 {'id': 361, 'category': 'news', 'term': 'Michi no Eki', 'weight': 1.0},
 {'id': 362, 'category': 'news', 'term': 'smart city project', 'weight': 1.0},
 {'id': 363, 'category': 'news', 'term': 'Osaka Expo', 'weight': 1.0},
 {'id': 364, 'category': 'news', 'term': 'World Expo 2025', 'weight': 1.0},
 {'id': 365, 'category': 'news', 'term': 'integrated resort', 'weight': 1.0},
 {'id': 366, 'category': 'news', 'term': 'casino resort', 'weight': 1.0},
 {'id': 367, 'category': 'news', 'term': 'IR project', 'weight': 1.0},
 {'id': 368, 'category': 'news', 'term': 'maglev', 'weight': 1.0},
 {'id': 369, 'category': 'news', 'term': 'Linear Chuo Shinkansen', 'weight': 1.0},
 {'id': 370, 'category': 'news', 'term': 'Chuo Shinkansen', 'weight': 1.0},
 {'id': 371, 'category': 'news', 'term': 'Tokyo Bay redevelopment', 'weight': 1.0},
 {'id': 372, 'category': 'news', 'term': 'Tsukiji redevelopment', 'weight': 1.0},
 {'id': 373, 'category': 'news', 'term': 'Toyosu market', 'weight': 1.0},
 {'id': 374, 'category': 'news', 'term': 'fish market auction', 'weight': 1.0},
 {'id': 375, 'category': 'news', 'term': 'waterworks privatization', 'weight': 1.0},
 {'id': 376, 'category': 'news', 'term': 'PFAS contamination', 'weight': 1.0},
 {'id': 377, 'category': 'news', 'term': 'microplastics policy', 'weight': 1.0},
 {'id': 378, 'category': 'news', 'term': 'bear culling', 'weight': 1.0},
 {'id': 379, 'category': 'news', 'term': 'cedar pollen', 'weight': 1.0},
 {'id': 380, 'category': 'news', 'term': 'hay fever season', 'weight': 1.0},
 {'id': 381, 'category': 'news', 'term': 'kafunsho', 'weight': 1.0},
 {'id': 382, 'category': 'news', 'term': 'Hokkaido', 'weight': 1.0},
 {'id': 383, 'category': 'news', 'term': 'Aomori', 'weight': 1.0},
 {'id': 384, 'category': 'news', 'term': 'Iwate', 'weight': 1.0},
 {'id': 385, 'category': 'news', 'term': 'Miyagi', 'weight': 1.0},
 {'id': 386, 'category': 'news', 'term': 'Akita', 'weight': 1.0},
 {'id': 387, 'category': 'news', 'term': 'Yamagata', 'weight': 1.0},
 {'id': 388, 'category': 'news', 'term': 'Fukushima', 'weight': 1.0},
 {'id': 389, 'category': 'news', 'term': 'Ibaraki', 'weight': 1.0},
 {'id': 390, 'category': 'news', 'term': 'Tochigi', 'weight': 1.0},
 {'id': 391, 'category': 'news', 'term': 'Gunma', 'weight': 1.0},
 {'id': 392, 'category': 'news', 'term': 'Saitama', 'weight': 1.0},
 {'id': 393, 'category': 'news', 'term': 'Chiba', 'weight': 1.0},
 {'id': 394, 'category': 'news', 'term': 'Tokyo', 'weight': 1.0},
 {'id': 395, 'category': 'news', 'term': 'Kanagawa', 'weight': 1.0},
 {'id': 396, 'category': 'news', 'term': 'Niigata', 'weight': 1.0},
 {'id': 397, 'category': 'news', 'term': 'Toyama', 'weight': 1.0},
 {'id': 398, 'category': 'news', 'term': 'Ishikawa', 'weight': 1.0},
 {'id': 399, 'category': 'news', 'term': 'Fukui', 'weight': 1.0},
 {'id': 400, 'category': 'news', 'term': 'Yamanashi', 'weight': 1.0},
 {'id': 401, 'category': 'news', 'term': 'Nagano', 'weight': 1.0},
 {'id': 402, 'category': 'news', 'term': 'Gifu', 'weight': 1.0},
 {'id': 403, 'category': 'news', 'term': 'Shizuoka', 'weight': 1.0},
 {'id': 404, 'category': 'news', 'term': 'Aichi', 'weight': 1.0},
 {'id': 405, 'category': 'news', 'term': 'Mie', 'weight': 1.0},
 {'id': 406, 'category': 'news', 'term': 'Shiga', 'weight': 1.0},
 {'id': 407, 'category': 'news', 'term': 'Kyoto', 'weight': 1.0},
 {'id': 408, 'category': 'news', 'term': 'Osaka', 'weight': 1.0},
 {'id': 409, 'category': 'news', 'term': 'Hyogo', 'weight': 1.0},
 {'id': 410, 'category': 'news', 'term': 'Nara', 'weight': 1.0},
 {'id': 411, 'category': 'news', 'term': 'Wakayama', 'weight': 1.0},
 {'id': 412, 'category': 'news', 'term': 'Tottori', 'weight': 1.0},
 {'id': 413, 'category': 'news', 'term': 'Shimane', 'weight': 1.0},
 {'id': 414, 'category': 'news', 'term': 'Okayama', 'weight': 1.0},
 {'id': 415, 'category': 'news', 'term': 'Hiroshima', 'weight': 1.0},
 {'id': 416, 'category': 'news', 'term': 'Yamaguchi', 'weight': 1.0},
 {'id': 417, 'category': 'news', 'term': 'Tokushima', 'weight': 1.0},
 {'id': 418, 'category': 'news', 'term': 'Kagawa', 'weight': 1.0},
 {'id': 419, 'category': 'news', 'term': 'Ehime', 'weight': 1.0},
 {'id': 420, 'category': 'news', 'term': 'Kochi', 'weight': 1.0},
 {'id': 421, 'category': 'news', 'term': 'Fukuoka', 'weight': 1.0},
 {'id': 422, 'category': 'news', 'term': 'Saga', 'weight': 1.0},
 {'id': 423, 'category': 'news', 'term': 'Nagasaki', 'weight': 1.0},
 {'id': 424, 'category': 'news', 'term': 'Kumamoto', 'weight': 1.0},
 {'id': 425, 'category': 'news', 'term': 'Oita', 'weight': 1.0},
 {'id': 426, 'category': 'news', 'term': 'Miyazaki', 'weight': 1.0},
 {'id': 427, 'category': 'news', 'term': 'Kagoshima', 'weight': 1.0},
 {'id': 428, 'category': 'news', 'term': 'Okinawa', 'weight': 1.0},
 {'id': 429, 'category': 'news', 'term': 'Sapporo', 'weight': 1.0},
 {'id': 430, 'category': 'news', 'term': 'Sendai', 'weight': 1.0},
 {'id': 431, 'category': 'news', 'term': 'Yokohama', 'weight': 1.0},
 {'id': 432, 'category': 'news', 'term': 'Kawasaki city', 'weight': 1.0},
 {'id': 433, 'category': 'news', 'term': 'Saitama city', 'weight': 1.0},
 {'id': 434, 'category': 'news', 'term': 'Chiba city', 'weight': 1.0},
 {'id': 435, 'category': 'news', 'term': 'Nagoya', 'weight': 1.0},
 {'id': 436, 'category': 'news', 'term': 'Kobe', 'weight': 1.0},
 {'id': 437, 'category': 'news', 'term': 'Kitakyushu', 'weight': 1.0},
 {'id': 438, 'category': 'news', 'term': 'Sakai', 'weight': 1.0},
 {'id': 439, 'category': 'news', 'term': 'Hamamatsu', 'weight': 1.0},
 {'id': 440, 'category': 'news', 'term': 'Niigata city', 'weight': 1.0},
 {'id': 441, 'category': 'news', 'term': 'Okayama city', 'weight': 1.0},
 {'id': 442, 'category': 'news', 'term': 'Kumamoto city', 'weight': 1.0},
 {'id': 443, 'category': 'news', 'term': 'Sagamihara', 'weight': 1.0},
 {'id': 444, 'category': 'news', 'term': 'Shizuoka city', 'weight': 1.0},
 {'id': 445, 'category': 'news', 'term': 'Hachioji', 'weight': 1.0},
 {'id': 446, 'category': 'news', 'term': 'Himeji', 'weight': 1.0},
 {'id': 447, 'category': 'news', 'term': 'Naha', 'weight': 1.0},
 {'id': 448, 'category': 'news', 'term': 'Utsunomiya', 'weight': 1.0},
 {'id': 449, 'category': 'news', 'term': 'Maebashi', 'weight': 1.0},
 {'id': 450, 'category': 'news', 'term': 'Mito', 'weight': 1.0},
 {'id': 451, 'category': 'news', 'term': 'Kanazawa', 'weight': 1.0},
 {'id': 452, 'category': 'news', 'term': 'Toyama city', 'weight': 1.0},
 {'id': 453, 'category': 'news', 'term': 'Fukui city', 'weight': 1.0},
 {'id': 454, 'category': 'news', 'term': 'Kofu', 'weight': 1.0},
 {'id': 455, 'category': 'news', 'term': 'Matsumoto', 'weight': 1.0},
 {'id': 456, 'category': 'news', 'term': 'Gifu city', 'weight': 1.0},
 {'id': 457, 'category': 'news', 'term': 'Tsu', 'weight': 1.0},
 {'id': 458, 'category': 'news', 'term': 'Otsu', 'weight': 1.0},
 {'id': 459, 'category': 'news', 'term': 'Wakayama city', 'weight': 1.0},
 {'id': 460, 'category': 'news', 'term': 'Matsue', 'weight': 1.0},
 {'id': 461, 'category': 'news', 'term': 'Takamatsu', 'weight': 1.0},
 {'id': 462, 'category': 'news', 'term': 'Matsuyama', 'weight': 1.0},
 {'id': 463, 'category': 'news', 'term': 'Kochi city', 'weight': 1.0},
 {'id': 464, 'category': 'news', 'term': 'Nagasaki city', 'weight': 1.0},
 {'id': 465, 'category': 'news', 'term': 'Miyazaki city', 'weight': 1.0},
 {'id': 466, 'category': 'news', 'term': 'Kagoshima city', 'weight': 1.0},
 {'id': 467, 'category': 'news', 'term': 'Aomori city', 'weight': 1.0},
 {'id': 468, 'category': 'news', 'term': 'Morioka', 'weight': 1.0},
 {'id': 469, 'category': 'news', 'term': 'Akita city', 'weight': 1.0},
 {'id': 470, 'category': 'news', 'term': 'Yamagata city', 'weight': 1.0},
 {'id': 471, 'category': 'news', 'term': 'Fukushima city', 'weight': 1.0},
 {'id': 472, 'category': 'news', 'term': 'Noto Peninsula', 'weight': 1.0},
 {'id': 473, 'category': 'news', 'term': 'Tohoku', 'weight': 1.0},
 {'id': 474, 'category': 'news', 'term': 'Kanto', 'weight': 1.0},
 {'id': 475, 'category': 'news', 'term': 'Chubu', 'weight': 1.0},
 {'id': 476, 'category': 'news', 'term': 'Kansai', 'weight': 1.0},
 {'id': 477, 'category': 'news', 'term': 'Chugoku region', 'weight': 1.0},
 {'id': 478, 'category': 'news', 'term': 'Shikoku', 'weight': 1.0},
 {'id': 479, 'category': 'news', 'term': 'Kyushu', 'weight': 1.0},
 {'id': 480, 'category': 'news', 'term': 'Setouchi', 'weight': 1.0},
 {'id': 481, 'category': 'news', 'term': 'Sanriku', 'weight': 1.0},
 {'id': 482, 'category': 'news', 'term': 'Boso Peninsula', 'weight': 1.0},
 {'id': 483, 'category': 'news', 'term': 'Izu Peninsula', 'weight': 1.0},
 {'id': 484, 'category': 'news', 'term': 'Kii Peninsula', 'weight': 1.0},
 {'id': 485, 'category': 'news', 'term': 'Tsugaru Strait', 'weight': 1.0},
 {'id': 486, 'category': 'news', 'term': 'Seto Inland Sea', 'weight': 1.0},
 {'id': 487, 'category': 'news', 'term': 'Ogasawara Islands', 'weight': 1.0},
 {'id': 488, 'category': 'news', 'term': 'Amami Oshima', 'weight': 1.0},
 {'id': 489, 'category': 'news', 'term': 'Miyakojima', 'weight': 1.0},
 {'id': 490, 'category': 'news', 'term': 'Ishigaki', 'weight': 1.0},
 {'id': 491, 'category': 'news', 'term': 'Yaeyama', 'weight': 1.0},
 {'id': 492, 'category': 'news', 'term': 'Iriomote', 'weight': 1.0},
 {'id': 493, 'category': 'news', 'term': 'Tsushima', 'weight': 1.0},
 {'id': 494, 'category': 'news', 'term': 'Sado Island', 'weight': 1.0},
 {'id': 495, 'category': 'news', 'term': 'Awaji Island', 'weight': 1.0},
 {'id': 496, 'category': 'news', 'term': 'Oki Islands', 'weight': 1.0},
 {'id': 497, 'category': 'news', 'term': 'Rishiri', 'weight': 1.0},
 {'id': 498, 'category': 'news', 'term': 'Rebun', 'weight': 1.0},
 {'id': 499, 'category': 'news', 'term': 'Shiretoko', 'weight': 1.0},
 {'id': 500, 'category': 'news', 'term': 'Lake Biwa', 'weight': 1.0},
 {'id': 501, 'category': 'business', 'term': 'Toyota', 'weight': 1.1},
 {'id': 502, 'category': 'business', 'term': 'Honda', 'weight': 1.1},
 {'id': 503, 'category': 'business', 'term': 'Nissan', 'weight': 1.1},
 {'id': 504, 'category': 'business', 'term': 'Mazda', 'weight': 1.1},
 {'id': 505, 'category': 'business', 'term': 'Subaru', 'weight': 1.1},
 {'id': 506, 'category': 'business', 'term': 'Suzuki', 'weight': 1.1},
 {'id': 507, 'category': 'business', 'term': 'Mitsubishi Motors', 'weight': 1.1},
 {'id': 508, 'category': 'business', 'term': 'Lexus', 'weight': 1.1},
 {'id': 509, 'category': 'business', 'term': 'Daihatsu', 'weight': 1.1},
 {'id': 510, 'category': 'business', 'term': 'Hino Motors', 'weight': 1.1},
 {'id': 511, 'category': 'business', 'term': 'Yamaha Motor', 'weight': 1.1},
 {'id': 512, 'category': 'business', 'term': 'Kawasaki Heavy Industries', 'weight': 1.1},
 {'id': 513, 'category': 'business', 'term': 'Isuzu', 'weight': 1.1},
 {'id': 514, 'category': 'business', 'term': 'Bridgestone', 'weight': 1.1},
 {'id': 515, 'category': 'business', 'term': 'Yokohama Rubber', 'weight': 1.1},
 {'id': 516, 'category': 'business', 'term': 'Sumitomo Rubber', 'weight': 1.1},
 {'id': 517, 'category': 'business', 'term': 'Aisin', 'weight': 1.1},
 {'id': 518, 'category': 'business', 'term': 'Denso', 'weight': 1.1},
 {'id': 519, 'category': 'business', 'term': 'Toyota Industries', 'weight': 1.1},
 {'id': 520, 'category': 'business', 'term': 'Toyota Tsusho', 'weight': 1.1},
 {'id': 521, 'category': 'business', 'term': 'JTEKT', 'weight': 1.1},
 {'id': 522, 'category': 'business', 'term': 'Nippon Steel', 'weight': 1.1},
 {'id': 523, 'category': 'business', 'term': 'JFE Holdings', 'weight': 1.1},
 {'id': 524, 'category': 'business', 'term': 'Kobe Steel', 'weight': 1.1},
 {'id': 525, 'category': 'business', 'term': 'Mitsubishi Heavy Industries', 'weight': 1.1},
 {'id': 526, 'category': 'business', 'term': 'IHI', 'weight': 1.1},
 {'id': 527, 'category': 'business', 'term': 'Hitachi', 'weight': 1.1},
 {'id': 528, 'category': 'business', 'term': 'Toshiba', 'weight': 1.1},
 {'id': 529, 'category': 'business', 'term': 'Panasonic', 'weight': 1.1},
 {'id': 530, 'category': 'business', 'term': 'Sony', 'weight': 1.1},
 {'id': 531, 'category': 'business', 'term': 'Canon', 'weight': 1.1},
 {'id': 532, 'category': 'business', 'term': 'Nikon', 'weight': 1.1},
 {'id': 533, 'category': 'business', 'term': 'Olympus', 'weight': 1.1},
 {'id': 534, 'category': 'business', 'term': 'Fujifilm', 'weight': 1.1},
 {'id': 535, 'category': 'business', 'term': 'Ricoh', 'weight': 1.1},
 {'id': 536, 'category': 'business', 'term': 'Sharp', 'weight': 1.1},
 {'id': 537, 'category': 'business', 'term': 'NEC', 'weight': 1.1},
 {'id': 538, 'category': 'business', 'term': 'Fujitsu', 'weight': 1.1},
 {'id': 539, 'category': 'business', 'term': 'TDK', 'weight': 1.1},
 {'id': 540, 'category': 'business', 'term': 'Murata Manufacturing', 'weight': 1.1},
 {'id': 541, 'category': 'business', 'term': 'Kyocera', 'weight': 1.1},
 {'id': 542, 'category': 'business', 'term': 'Omron', 'weight': 1.1},
 {'id': 543, 'category': 'business', 'term': 'Keyence', 'weight': 1.1},
 {'id': 544, 'category': 'business', 'term': 'Fanuc', 'weight': 1.1},
 {'id': 545, 'category': 'business', 'term': 'Yaskawa Electric', 'weight': 1.1},
 {'id': 546, 'category': 'business', 'term': 'Rohm', 'weight': 1.1},
 {'id': 547, 'category': 'business', 'term': 'Renesas', 'weight': 1.1},
 {'id': 548, 'category': 'business', 'term': 'Tokyo Electron', 'weight': 1.1},
 {'id': 549, 'category': 'business', 'term': 'Screen Holdings', 'weight': 1.1},
 {'id': 550, 'category': 'business', 'term': 'Advantest', 'weight': 1.1},
 {'id': 551, 'category': 'business', 'term': 'Disco Corp', 'weight': 1.1},
 {'id': 552, 'category': 'business', 'term': 'Lasertec', 'weight': 1.1},
 {'id': 553, 'category': 'business', 'term': 'Sumco', 'weight': 1.1},
 {'id': 554, 'category': 'business', 'term': 'Shin-Etsu Chemical', 'weight': 1.1},
 {'id': 555, 'category': 'business', 'term': 'JSR', 'weight': 1.1},
 {'id': 556, 'category': 'business', 'term': 'Tokyo Ohka Kogyo', 'weight': 1.1},
 {'id': 557, 'category': 'business', 'term': 'Ajinomoto Build-up Film', 'weight': 1.1},
 {'id': 558, 'category': 'business', 'term': 'ABF substrate', 'weight': 1.1},
 {'id': 559, 'category': 'business', 'term': 'Ibiden', 'weight': 1.1},
 {'id': 560, 'category': 'business', 'term': 'Shinko Electric', 'weight': 1.1},
 {'id': 561, 'category': 'business', 'term': 'Mitsubishi Chemical', 'weight': 1.1},
 {'id': 562, 'category': 'business', 'term': 'Sumitomo Chemical', 'weight': 1.1},
 {'id': 563, 'category': 'business', 'term': 'Asahi Kasei', 'weight': 1.1},
 {'id': 564, 'category': 'business', 'term': 'Toray', 'weight': 1.1},
 {'id': 565, 'category': 'business', 'term': 'Teijin', 'weight': 1.1},
 {'id': 566, 'category': 'business', 'term': 'Kuraray', 'weight': 1.1},
 {'id': 567, 'category': 'business', 'term': 'Daikin', 'weight': 1.1},
 {'id': 568, 'category': 'business', 'term': 'Komatsu', 'weight': 1.1},
 {'id': 569, 'category': 'business', 'term': 'Kubota', 'weight': 1.1},
 {'id': 570, 'category': 'business', 'term': 'Makita', 'weight': 1.1},
 {'id': 571, 'category': 'business', 'term': 'SMC', 'weight': 1.1},
 {'id': 572, 'category': 'business', 'term': 'Mitsubishi Electric', 'weight': 1.1},
 {'id': 573, 'category': 'business', 'term': 'Seiko Epson', 'weight': 1.1},
 {'id': 574, 'category': 'business', 'term': 'Casio', 'weight': 1.1},
 {'id': 575, 'category': 'business', 'term': 'Citizen Watch', 'weight': 1.1},
 {'id': 576, 'category': 'business', 'term': 'Seiko Group', 'weight': 1.1},
 {'id': 577, 'category': 'business', 'term': 'Brother Industries', 'weight': 1.1},
 {'id': 578, 'category': 'business', 'term': 'Nintendo', 'weight': 1.1},
 {'id': 579, 'category': 'business', 'term': 'Bandai Namco', 'weight': 1.1},
 {'id': 580, 'category': 'business', 'term': 'Square Enix', 'weight': 1.1},
 {'id': 581, 'category': 'business', 'term': 'Capcom', 'weight': 1.1},
 {'id': 582, 'category': 'business', 'term': 'Konami', 'weight': 1.1},
 {'id': 583, 'category': 'business', 'term': 'Sega Sammy', 'weight': 1.1},
 {'id': 584, 'category': 'business', 'term': 'CyberAgent', 'weight': 1.1},
 {'id': 585, 'category': 'business', 'term': 'DeNA', 'weight': 1.1},
 {'id': 586, 'category': 'business', 'term': 'Gree', 'weight': 1.1},
 {'id': 587, 'category': 'business', 'term': 'Mixi', 'weight': 1.1},
 {'id': 588, 'category': 'business', 'term': 'Koei Tecmo', 'weight': 1.1},
 {'id': 589, 'category': 'business', 'term': 'Sony Interactive Entertainment', 'weight': 1.1},
 {'id': 590, 'category': 'business', 'term': 'PlayStation', 'weight': 1.1},
 {'id': 591, 'category': 'business', 'term': 'SoftBank', 'weight': 1.1},
 {'id': 592, 'category': 'business', 'term': 'Rakuten', 'weight': 1.1},
 {'id': 593, 'category': 'business', 'term': 'NTT', 'weight': 1.1},
 {'id': 594, 'category': 'business', 'term': 'NTT Docomo', 'weight': 1.1},
 {'id': 595, 'category': 'business', 'term': 'KDDI', 'weight': 1.1},
 {'id': 596, 'category': 'business', 'term': 'au', 'weight': 1.1},
 {'id': 597, 'category': 'business', 'term': 'Line Yahoo', 'weight': 1.1},
 {'id': 598, 'category': 'business', 'term': 'Mercari', 'weight': 1.1},
 {'id': 599, 'category': 'business', 'term': 'DMM', 'weight': 1.1},
 {'id': 600, 'category': 'business', 'term': 'Z Holdings', 'weight': 1.1},
 {'id': 601, 'category': 'business', 'term': 'Recruit Holdings', 'weight': 1.1},
 {'id': 602, 'category': 'business', 'term': 'Rikunabi', 'weight': 1.1},
 {'id': 603, 'category': 'business', 'term': 'Indeed parent', 'weight': 1.1},
 {'id': 604, 'category': 'business', 'term': 'Fast Retailing', 'weight': 1.1},
 {'id': 605, 'category': 'business', 'term': 'Uniqlo', 'weight': 1.1},
 {'id': 606, 'category': 'business', 'term': 'GU', 'weight': 1.1},
 {'id': 607, 'category': 'business', 'term': 'Muji', 'weight': 1.1},
 {'id': 608, 'category': 'business', 'term': 'Ryohin Keikaku', 'weight': 1.1},
 {'id': 609, 'category': 'business', 'term': 'Seven & i', 'weight': 1.1},
 {'id': 610, 'category': 'business', 'term': 'Ito-Yokado', 'weight': 1.1},
 {'id': 611, 'category': 'business', 'term': 'Lawson', 'weight': 1.1},
 {'id': 612, 'category': 'business', 'term': 'FamilyMart', 'weight': 1.1},
 {'id': 613, 'category': 'business', 'term': 'Aeon', 'weight': 1.1},
 {'id': 614, 'category': 'business', 'term': 'Don Quijote', 'weight': 1.1},
 {'id': 615, 'category': 'business', 'term': 'Pan Pacific International', 'weight': 1.1},
 {'id': 616, 'category': 'business', 'term': 'Isetan Mitsukoshi', 'weight': 1.1},
 {'id': 617, 'category': 'business', 'term': 'Takashimaya', 'weight': 1.1},
 {'id': 618, 'category': 'business', 'term': 'Daimaru Matsuzakaya', 'weight': 1.1},
 {'id': 619, 'category': 'business', 'term': 'Marui', 'weight': 1.1},
 {'id': 620, 'category': 'business', 'term': 'ZOZO', 'weight': 1.1},
 {'id': 621, 'category': 'business', 'term': 'Rakuten Ichiba', 'weight': 1.1},
 {'id': 622, 'category': 'business', 'term': 'Mitsubishi UFJ', 'weight': 1.1},
 {'id': 623, 'category': 'business', 'term': 'MUFG', 'weight': 1.1},
 {'id': 624, 'category': 'business', 'term': 'Sumitomo Mitsui', 'weight': 1.1},
 {'id': 625, 'category': 'business', 'term': 'SMFG', 'weight': 1.1},
 {'id': 626, 'category': 'business', 'term': 'Mizuho', 'weight': 1.1},
 {'id': 627, 'category': 'business', 'term': 'Nomura', 'weight': 1.1},
 {'id': 628, 'category': 'business', 'term': 'Daiwa Securities', 'weight': 1.1},
 {'id': 629, 'category': 'business', 'term': 'SBI Holdings', 'weight': 1.1},
 {'id': 630, 'category': 'business', 'term': 'Monex', 'weight': 1.1},
 {'id': 631, 'category': 'business', 'term': 'ORIX', 'weight': 1.1},
 {'id': 632, 'category': 'business', 'term': 'Tokio Marine', 'weight': 1.1},
 {'id': 633, 'category': 'business', 'term': 'MS&AD', 'weight': 1.1},
 {'id': 634, 'category': 'business', 'term': 'Sompo', 'weight': 1.1},
 {'id': 635, 'category': 'business', 'term': 'Dai-ichi Life', 'weight': 1.1},
 {'id': 636, 'category': 'business', 'term': 'Nippon Life', 'weight': 1.1},
 {'id': 637, 'category': 'business', 'term': 'Meiji Yasuda', 'weight': 1.1},
 {'id': 638, 'category': 'business', 'term': 'Mitsui Fudosan', 'weight': 1.1},
 {'id': 639, 'category': 'business', 'term': 'Mitsubishi Estate', 'weight': 1.1},
 {'id': 640, 'category': 'business', 'term': 'Sumitomo Realty', 'weight': 1.1},
 {'id': 641, 'category': 'business', 'term': 'Nomura Real Estate', 'weight': 1.1},
 {'id': 642, 'category': 'business', 'term': 'Sekisui House', 'weight': 1.1},
 {'id': 643, 'category': 'business', 'term': 'Daiwa House', 'weight': 1.1},
 {'id': 644, 'category': 'business', 'term': 'Obayashi', 'weight': 1.1},
 {'id': 645, 'category': 'business', 'term': 'Kajima', 'weight': 1.1},
 {'id': 646, 'category': 'business', 'term': 'Taisei', 'weight': 1.1},
 {'id': 647, 'category': 'business', 'term': 'Shimizu Corp', 'weight': 1.1},
 {'id': 648, 'category': 'business', 'term': 'Takenaka', 'weight': 1.1},
 {'id': 649, 'category': 'business', 'term': 'JR East', 'weight': 1.1},
 {'id': 650, 'category': 'business', 'term': 'JR Central', 'weight': 1.1},
 {'id': 651, 'category': 'business', 'term': 'JR West', 'weight': 1.1},
 {'id': 652, 'category': 'business', 'term': 'JR Kyushu', 'weight': 1.1},
 {'id': 653, 'category': 'business', 'term': 'JR Hokkaido', 'weight': 1.1},
 {'id': 654, 'category': 'business', 'term': 'JR Shikoku', 'weight': 1.1},
 {'id': 655, 'category': 'business', 'term': 'Tokyo Metro', 'weight': 1.1},
 {'id': 656, 'category': 'business', 'term': 'Tokyu', 'weight': 1.1},
 {'id': 657, 'category': 'business', 'term': 'Odakyu', 'weight': 1.1},
 {'id': 658, 'category': 'business', 'term': 'Keio', 'weight': 1.1},
 {'id': 659, 'category': 'business', 'term': 'Tobu', 'weight': 1.1},
 {'id': 660, 'category': 'business', 'term': 'Seibu', 'weight': 1.1},
 {'id': 661, 'category': 'business', 'term': 'Keisei', 'weight': 1.1},
 {'id': 662, 'category': 'business', 'term': 'Keikyu', 'weight': 1.1},
 {'id': 663, 'category': 'business', 'term': 'Kintetsu', 'weight': 1.1},
 {'id': 664, 'category': 'business', 'term': 'Hankyu Hanshin', 'weight': 1.1},
 {'id': 665, 'category': 'business', 'term': 'Nankai', 'weight': 1.1},
 {'id': 666, 'category': 'business', 'term': 'ANA', 'weight': 1.1},
 {'id': 667, 'category': 'business', 'term': 'All Nippon Airways', 'weight': 1.1},
 {'id': 668, 'category': 'business', 'term': 'JAL', 'weight': 1.1},
 {'id': 669, 'category': 'business', 'term': 'J-Air', 'weight': 1.1},
 {'id': 670, 'category': 'business', 'term': 'Skymark', 'weight': 1.1},
 {'id': 671, 'category': 'business', 'term': 'Peach Aviation', 'weight': 1.1},
 {'id': 672, 'category': 'business', 'term': 'Zipair', 'weight': 1.1},
 {'id': 673, 'category': 'business', 'term': 'Yamato Holdings', 'weight': 1.1},
 {'id': 674, 'category': 'business', 'term': 'Kuroneko Yamato', 'weight': 1.1},
 {'id': 675, 'category': 'business', 'term': 'Sagawa Express', 'weight': 1.1},
 {'id': 676, 'category': 'business', 'term': 'Nippon Express', 'weight': 1.1},
 {'id': 677, 'category': 'business', 'term': 'Nippon Yusen', 'weight': 1.1},
 {'id': 678, 'category': 'business', 'term': 'NYK Line', 'weight': 1.1},
 {'id': 679, 'category': 'business', 'term': 'Mitsui OSK Lines', 'weight': 1.1},
 {'id': 680, 'category': 'business', 'term': 'K Line', 'weight': 1.1},
 {'id': 681, 'category': 'business', 'term': 'Mitsubishi Corporation', 'weight': 1.1},
 {'id': 682, 'category': 'business', 'term': 'Mitsui & Co', 'weight': 1.1},
 {'id': 683, 'category': 'business', 'term': 'Itochu', 'weight': 1.1},
 {'id': 684, 'category': 'business', 'term': 'Sumitomo Corporation', 'weight': 1.1},
 {'id': 685, 'category': 'business', 'term': 'Marubeni', 'weight': 1.1},
 {'id': 686, 'category': 'business', 'term': 'Sojitz', 'weight': 1.1},
 {'id': 687, 'category': 'business', 'term': 'sogo shosha', 'weight': 1.1},
 {'id': 688, 'category': 'business', 'term': 'trading house', 'weight': 1.1},
 {'id': 689, 'category': 'business', 'term': 'keiretsu', 'weight': 1.1},
 {'id': 690, 'category': 'business', 'term': 'zaibatsu', 'weight': 1.1},
 {'id': 691, 'category': 'business', 'term': 'cross-shareholding', 'weight': 1.1},
 {'id': 692, 'category': 'business', 'term': 'activist investor', 'weight': 1.1},
 {'id': 693, 'category': 'business', 'term': 'shareholder proposal', 'weight': 1.1},
 {'id': 694, 'category': 'business', 'term': 'proxy fight', 'weight': 1.1},
 {'id': 695, 'category': 'business', 'term': 'tender offer', 'weight': 1.1},
 {'id': 696, 'category': 'business', 'term': 'TOB', 'weight': 1.1},
 {'id': 697, 'category': 'business', 'term': 'management buyout', 'weight': 1.1},
 {'id': 698, 'category': 'business', 'term': 'MBO', 'weight': 1.1},
 {'id': 699, 'category': 'business', 'term': 'corporate governance code', 'weight': 1.1},
 {'id': 700, 'category': 'business', 'term': 'stewardship code', 'weight': 1.1},
 {'id': 701, 'category': 'popculture', 'term': 'kawaii', 'weight': 0.9},
 {'id': 702, 'category': 'popculture', 'term': 'otaku', 'weight': 0.9},
 {'id': 703, 'category': 'popculture', 'term': 'cosplay', 'weight': 0.9},
 {'id': 704, 'category': 'popculture', 'term': 'Comiket', 'weight': 0.9},
 {'id': 705, 'category': 'popculture', 'term': 'doujinshi', 'weight': 0.9},
 {'id': 706, 'category': 'popculture', 'term': 'doujin', 'weight': 0.9},
 {'id': 707, 'category': 'popculture', 'term': 'maid cafe', 'weight': 0.9},
 {'id': 708, 'category': 'popculture', 'term': 'Akihabara culture', 'weight': 0.9},
 {'id': 709, 'category': 'popculture', 'term': 'Harajuku fashion', 'weight': 0.9},
 {'id': 710, 'category': 'popculture', 'term': 'Lolita fashion', 'weight': 0.9},
 {'id': 711, 'category': 'popculture', 'term': 'gyaru', 'weight': 0.9},
 {'id': 712, 'category': 'popculture', 'term': 'decora fashion', 'weight': 0.9},
 {'id': 713, 'category': 'popculture', 'term': 'visual kei', 'weight': 0.9},
 {'id': 714, 'category': 'popculture', 'term': 'J-pop', 'weight': 0.9},
 {'id': 715, 'category': 'popculture', 'term': 'J-rock', 'weight': 0.9},
 {'id': 716, 'category': 'popculture', 'term': 'city pop', 'weight': 0.9},
 {'id': 717, 'category': 'popculture', 'term': 'enka', 'weight': 0.9},
 {'id': 718, 'category': 'popculture', 'term': 'kayokyoku', 'weight': 0.9},
 {'id': 719, 'category': 'popculture', 'term': 'Vocaloid', 'weight': 0.9},
 {'id': 720, 'category': 'popculture', 'term': 'Hatsune Miku', 'weight': 0.9},
 {'id': 721, 'category': 'popculture', 'term': 'Kagamine Rin', 'weight': 0.9},
 {'id': 722, 'category': 'popculture', 'term': 'Megurine Luka', 'weight': 0.9},
 {'id': 723, 'category': 'popculture', 'term': 'Utau', 'weight': 0.9},
 {'id': 724, 'category': 'popculture', 'term': 'Niconico', 'weight': 0.9},
 {'id': 725, 'category': 'popculture', 'term': 'Pixiv', 'weight': 0.9},
 {'id': 726, 'category': 'popculture', 'term': 'Line stickers', 'weight': 0.9},
 {'id': 727, 'category': 'popculture', 'term': 'emoji culture', 'weight': 0.9},
 {'id': 728, 'category': 'popculture', 'term': 'kaomoji', 'weight': 0.9},
 {'id': 729, 'category': 'popculture', 'term': 'purikura', 'weight': 0.9},
 {'id': 730, 'category': 'popculture', 'term': 'gachapon', 'weight': 0.9},
 {'id': 731, 'category': 'popculture', 'term': 'capsule toy', 'weight': 0.9},
 {'id': 732, 'category': 'popculture', 'term': 'gacha', 'weight': 0.9},
 {'id': 733, 'category': 'popculture', 'term': 'oshikatsu', 'weight': 0.9},
 {'id': 734, 'category': 'popculture', 'term': 'oshi', 'weight': 0.9},
 {'id': 735, 'category': 'popculture', 'term': 'idol', 'weight': 0.9},
 {'id': 736, 'category': 'popculture', 'term': 'underground idol', 'weight': 0.9},
 {'id': 737, 'category': 'popculture', 'term': 'gravure idol', 'weight': 0.9},
 {'id': 738, 'category': 'popculture', 'term': 'boy band', 'weight': 0.9},
 {'id': 739, 'category': 'popculture', 'term': 'girl group', 'weight': 0.9},
 {'id': 740, 'category': 'popculture', 'term': 'Johnny & Associates', 'weight': 0.9},
 {'id': 741, 'category': 'popculture', 'term': 'Starto Entertainment', 'weight': 0.9},
 {'id': 742, 'category': 'popculture', 'term': 'AKB48', 'weight': 0.9},
 {'id': 743, 'category': 'popculture', 'term': 'Nogizaka46', 'weight': 0.9},
 {'id': 744, 'category': 'popculture', 'term': 'Sakurazaka46', 'weight': 0.9},
 {'id': 745, 'category': 'popculture', 'term': 'Hinatazaka46', 'weight': 0.9},
 {'id': 746, 'category': 'popculture', 'term': 'Morning Musume', 'weight': 0.9},
 {'id': 747, 'category': 'popculture', 'term': 'Perfume', 'weight': 0.9},
 {'id': 748, 'category': 'popculture', 'term': 'Babymetal', 'weight': 0.9},
 {'id': 749, 'category': 'popculture', 'term': 'XG', 'weight': 0.9},
 {'id': 750, 'category': 'popculture', 'term': 'King Gnu', 'weight': 0.9},
 {'id': 751, 'category': 'popculture', 'term': 'YOASOBI', 'weight': 0.9},
 {'id': 752, 'category': 'popculture', 'term': 'Ado', 'weight': 0.9},
 {'id': 753, 'category': 'popculture', 'term': 'Kenshi Yonezu', 'weight': 0.9},
 {'id': 754, 'category': 'popculture', 'term': 'LiSA', 'weight': 0.9},
 {'id': 755, 'category': 'popculture', 'term': 'Yumi Matsutoya', 'weight': 0.9},
 {'id': 756, 'category': 'popculture', 'term': 'Ryuichi Sakamoto', 'weight': 0.9},
 {'id': 757, 'category': 'popculture', 'term': 'Joe Hisaishi', 'weight': 0.9},
 {'id': 758, 'category': 'popculture', 'term': 'karaoke', 'weight': 0.9},
 {'id': 759, 'category': 'popculture', 'term': 'J-drama', 'weight': 0.9},
 {'id': 760, 'category': 'popculture', 'term': 'taiga drama', 'weight': 0.9},
 {'id': 761, 'category': 'popculture', 'term': 'asadora', 'weight': 0.9},
 {'id': 762, 'category': 'popculture', 'term': 'Takarazuka', 'weight': 0.9},
 {'id': 763, 'category': 'popculture', 'term': 'Takarazuka Revue', 'weight': 0.9},
 {'id': 764, 'category': 'popculture', 'term': 'kabuki actor', 'weight': 0.9},
 {'id': 765, 'category': 'popculture', 'term': 'host club', 'weight': 0.9},
 {'id': 766, 'category': 'popculture', 'term': 'Kabukicho', 'weight': 0.9},
 {'id': 767, 'category': 'popculture', 'term': 'Shibuya fashion', 'weight': 0.9},
 {'id': 768, 'category': 'popculture', 'term': 'Halloween in Shibuya', 'weight': 0.9},
 {'id': 769, 'category': 'popculture', 'term': 'Sanrio', 'weight': 0.9},
 {'id': 770, 'category': 'popculture', 'term': 'Hello Kitty', 'weight': 0.9},
 {'id': 771, 'category': 'popculture', 'term': 'My Melody', 'weight': 0.9},
 {'id': 772, 'category': 'popculture', 'term': 'Kuromi', 'weight': 0.9},
 {'id': 773, 'category': 'popculture', 'term': 'Cinnamoroll', 'weight': 0.9},
 {'id': 774, 'category': 'popculture', 'term': 'Pompompurin', 'weight': 0.9},
 {'id': 775, 'category': 'popculture', 'term': 'Rilakkuma', 'weight': 0.9},
 {'id': 776, 'category': 'popculture', 'term': 'Sumikko Gurashi', 'weight': 0.9},
 {'id': 777, 'category': 'popculture', 'term': 'Chiikawa', 'weight': 0.9},
 {'id': 778, 'category': 'popculture', 'term': 'Domo-kun', 'weight': 0.9},
 {'id': 779, 'category': 'popculture', 'term': 'Kumamon', 'weight': 0.9},
 {'id': 780, 'category': 'popculture', 'term': 'Funassyi', 'weight': 0.9},
 {'id': 781, 'category': 'popculture', 'term': 'Kewpie doll', 'weight': 0.9},
 {'id': 782, 'category': 'popculture', 'term': 'kokeshi', 'weight': 0.9},
 {'id': 783, 'category': 'popculture', 'term': 'Maneki-neko', 'weight': 0.9},
 {'id': 784, 'category': 'popculture', 'term': 'daruma doll', 'weight': 0.9},
 {'id': 785, 'category': 'popculture', 'term': 'kendama', 'weight': 0.9},
 {'id': 786, 'category': 'popculture', 'term': 'tamagochi', 'weight': 0.9},
 {'id': 787, 'category': 'popculture', 'term': 'Tamagotchi', 'weight': 0.9},
 {'id': 788, 'category': 'popculture', 'term': 'tokusatsu', 'weight': 0.9},
 {'id': 789, 'category': 'popculture', 'term': 'kaiju', 'weight': 0.9},
 {'id': 790, 'category': 'popculture', 'term': 'super sentai', 'weight': 0.9},
 {'id': 791, 'category': 'popculture', 'term': 'Kamen Rider', 'weight': 0.9},
 {'id': 792, 'category': 'popculture', 'term': 'Ultraman', 'weight': 0.9},
 {'id': 793, 'category': 'popculture', 'term': 'Godzilla', 'weight': 0.9},
 {'id': 794, 'category': 'popculture', 'term': 'Mothra', 'weight': 0.9},
 {'id': 795, 'category': 'popculture', 'term': 'Gamera', 'weight': 0.9},
 {'id': 796, 'category': 'popculture', 'term': 'Toho monsters', 'weight': 0.9},
 {'id': 797, 'category': 'popculture', 'term': 'VTuber', 'weight': 0.9},
 {'id': 798, 'category': 'popculture', 'term': 'Hololive', 'weight': 0.9},
 {'id': 799, 'category': 'popculture', 'term': 'Nijisanji', 'weight': 0.9},
 {'id': 800, 'category': 'popculture', 'term': 'Kizuna AI', 'weight': 0.9},
 {'id': 801, 'category': 'anime', 'term': 'Studio Ghibli', 'weight': 1.0},
 {'id': 802, 'category': 'anime', 'term': 'Hayao Miyazaki', 'weight': 1.0},
 {'id': 803, 'category': 'anime', 'term': 'Isao Takahata', 'weight': 1.0},
 {'id': 804, 'category': 'anime', 'term': 'Ghibli Park', 'weight': 1.0},
 {'id': 805, 'category': 'anime', 'term': 'Totoro', 'weight': 1.0},
 {'id': 806, 'category': 'anime', 'term': 'Spirited Away', 'weight': 1.0},
 {'id': 807, 'category': 'anime', 'term': 'Princess Mononoke', 'weight': 1.0},
 {'id': 808, 'category': 'anime', 'term': 'Howl’s Moving Castle', 'weight': 1.0},
 {'id': 809, 'category': 'anime', 'term': 'Kiki’s Delivery Service', 'weight': 1.0},
 {'id': 810, 'category': 'anime', 'term': 'Ponyo', 'weight': 1.0},
 {'id': 811, 'category': 'anime', 'term': 'The Boy and the Heron', 'weight': 1.0},
 {'id': 812, 'category': 'anime', 'term': 'Evangelion', 'weight': 1.0},
 {'id': 813, 'category': 'anime', 'term': 'Gundam', 'weight': 1.0},
 {'id': 814, 'category': 'anime', 'term': 'Mobile Suit Gundam', 'weight': 1.0},
 {'id': 815, 'category': 'anime', 'term': 'One Piece', 'weight': 1.0},
 {'id': 816, 'category': 'anime', 'term': 'Demon Slayer', 'weight': 1.0},
 {'id': 817, 'category': 'anime', 'term': 'Kimetsu no Yaiba', 'weight': 1.0},
 {'id': 818, 'category': 'anime', 'term': 'Dragon Ball', 'weight': 1.0},
 {'id': 819, 'category': 'anime', 'term': 'Naruto', 'weight': 1.0},
 {'id': 820, 'category': 'anime', 'term': 'Boruto', 'weight': 1.0},
 {'id': 821, 'category': 'anime', 'term': 'Jujutsu Kaisen', 'weight': 1.0},
 {'id': 822, 'category': 'anime', 'term': 'Attack on Titan', 'weight': 1.0},
 {'id': 823, 'category': 'anime', 'term': 'My Hero Academia', 'weight': 1.0},
 {'id': 824, 'category': 'anime', 'term': 'Chainsaw Man', 'weight': 1.0},
 {'id': 825, 'category': 'anime', 'term': 'Spy x Family', 'weight': 1.0},
 {'id': 826, 'category': 'anime', 'term': 'Sailor Moon', 'weight': 1.0},
 {'id': 827, 'category': 'anime', 'term': 'Detective Conan', 'weight': 1.0},
 {'id': 828, 'category': 'anime', 'term': 'Doraemon', 'weight': 1.0},
 {'id': 829, 'category': 'anime', 'term': 'Anpanman', 'weight': 1.0},
 {'id': 830, 'category': 'anime', 'term': 'Crayon Shin-chan', 'weight': 1.0},
 {'id': 831, 'category': 'anime', 'term': 'Pokemon anime', 'weight': 1.0},
 {'id': 832, 'category': 'anime', 'term': 'Digimon anime', 'weight': 1.0},
 {'id': 833, 'category': 'anime', 'term': 'Yu-Gi-Oh anime', 'weight': 1.0},
 {'id': 834, 'category': 'anime', 'term': 'Beyblade anime', 'weight': 1.0},
 {'id': 835, 'category': 'anime', 'term': 'Fullmetal Alchemist', 'weight': 1.0},
 {'id': 836, 'category': 'anime', 'term': 'Death Note', 'weight': 1.0},
 {'id': 837, 'category': 'anime', 'term': 'Cowboy Bebop', 'weight': 1.0},
 {'id': 838, 'category': 'anime', 'term': 'Ghost in the Shell', 'weight': 1.0},
 {'id': 839, 'category': 'anime', 'term': 'Akira anime', 'weight': 1.0},
 {'id': 840, 'category': 'anime', 'term': 'Your Name', 'weight': 1.0},
 {'id': 841, 'category': 'anime', 'term': 'Makoto Shinkai', 'weight': 1.0},
 {'id': 842, 'category': 'anime', 'term': 'Suzume', 'weight': 1.0},
 {'id': 843, 'category': 'anime', 'term': 'Weathering with You', 'weight': 1.0},
 {'id': 844, 'category': 'anime', 'term': 'Neon Genesis Evangelion', 'weight': 1.0},
 {'id': 845, 'category': 'anime', 'term': 'Frieren', 'weight': 1.0},
 {'id': 846, 'category': 'anime', 'term': 'Oshi no Ko', 'weight': 1.0},
 {'id': 847, 'category': 'anime', 'term': 'Haikyu', 'weight': 1.0},
 {'id': 848, 'category': 'anime', 'term': 'Blue Lock', 'weight': 1.0},
 {'id': 849, 'category': 'anime', 'term': 'Bocchi the Rock', 'weight': 1.0},
 {'id': 850, 'category': 'anime', 'term': 'Solo Leveling anime', 'weight': 1.0},
 {'id': 851, 'category': 'game', 'term': 'Mario', 'weight': 1.0},
 {'id': 852, 'category': 'game', 'term': 'Super Mario', 'weight': 1.0},
 {'id': 853, 'category': 'game', 'term': 'Zelda', 'weight': 1.0},
 {'id': 854, 'category': 'game', 'term': 'Legend of Zelda', 'weight': 1.0},
 {'id': 855, 'category': 'game', 'term': 'Donkey Kong', 'weight': 1.0},
 {'id': 856, 'category': 'game', 'term': 'Kirby', 'weight': 1.0},
 {'id': 857, 'category': 'game', 'term': 'Metroid', 'weight': 1.0},
 {'id': 858, 'category': 'game', 'term': 'Animal Crossing', 'weight': 1.0},
 {'id': 859, 'category': 'game', 'term': 'Splatoon', 'weight': 1.0},
 {'id': 860, 'category': 'game', 'term': 'Fire Emblem', 'weight': 1.0},
 {'id': 861, 'category': 'game', 'term': 'Pikmin', 'weight': 1.0},
 {'id': 862, 'category': 'game', 'term': 'Smash Bros', 'weight': 1.0},
 {'id': 863, 'category': 'game', 'term': 'Super Smash Bros', 'weight': 1.0},
 {'id': 864, 'category': 'game', 'term': 'Nintendo Switch', 'weight': 1.0},
 {'id': 865, 'category': 'game', 'term': 'Switch 2', 'weight': 1.0},
 {'id': 866, 'category': 'game', 'term': 'Nintendo Direct', 'weight': 1.0},
 {'id': 867, 'category': 'game', 'term': 'Pokemon games', 'weight': 1.0},
 {'id': 868, 'category': 'game', 'term': 'Pokemon Scarlet', 'weight': 1.0},
 {'id': 869, 'category': 'game', 'term': 'Pokemon Violet', 'weight': 1.0},
 {'id': 870, 'category': 'game', 'term': 'Pokemon Legends', 'weight': 1.0},
 {'id': 871, 'category': 'game', 'term': 'Pikachu', 'weight': 1.0},
 {'id': 872, 'category': 'game', 'term': 'Eevee', 'weight': 1.0},
 {'id': 873, 'category': 'game', 'term': 'Final Fantasy', 'weight': 1.0},
 {'id': 874, 'category': 'game', 'term': 'Dragon Quest', 'weight': 1.0},
 {'id': 875, 'category': 'game', 'term': 'Kingdom Hearts', 'weight': 1.0},
 {'id': 876, 'category': 'game', 'term': 'Persona', 'weight': 1.0},
 {'id': 877, 'category': 'game', 'term': 'Shin Megami Tensei', 'weight': 1.0},
 {'id': 878, 'category': 'game', 'term': 'Monster Hunter', 'weight': 1.0},
 {'id': 879, 'category': 'game', 'term': 'Resident Evil', 'weight': 1.0},
 {'id': 880, 'category': 'game', 'term': 'Street Fighter', 'weight': 1.0},
 {'id': 881, 'category': 'game', 'term': 'Tekken', 'weight': 1.0},
 {'id': 882, 'category': 'game', 'term': 'Yakuza game', 'weight': 1.0},
 {'id': 883, 'category': 'game', 'term': 'Like a Dragon', 'weight': 1.0},
 {'id': 884, 'category': 'game', 'term': 'Sonic the Hedgehog', 'weight': 1.0},
 {'id': 885, 'category': 'game', 'term': 'Metal Gear', 'weight': 1.0},
 {'id': 886, 'category': 'game', 'term': 'Silent Hill', 'weight': 1.0},
 {'id': 887, 'category': 'game', 'term': 'Castlevania', 'weight': 1.0},
 {'id': 888, 'category': 'game', 'term': 'Ace Attorney', 'weight': 1.0},
 {'id': 889, 'category': 'game', 'term': 'Phoenix Wright', 'weight': 1.0},
 {'id': 890, 'category': 'game', 'term': 'Elden Ring', 'weight': 1.0},
 {'id': 891, 'category': 'game', 'term': 'Dark Souls', 'weight': 1.0},
 {'id': 892, 'category': 'game', 'term': 'Sekiro', 'weight': 1.0},
 {'id': 893, 'category': 'game', 'term': 'Bloodborne', 'weight': 1.0},
 {'id': 894, 'category': 'game', 'term': 'Armored Core', 'weight': 1.0},
 {'id': 895, 'category': 'game', 'term': 'Gran Turismo', 'weight': 1.0},
 {'id': 896, 'category': 'game', 'term': 'Dynasty Warriors', 'weight': 1.0},
 {'id': 897, 'category': 'game', 'term': 'Touhou Project', 'weight': 1.0},
 {'id': 898, 'category': 'game', 'term': 'Pachinko', 'weight': 1.0},
 {'id': 899, 'category': 'game', 'term': 'Pachislot', 'weight': 1.0},
 {'id': 900, 'category': 'game', 'term': 'Arcade cabinet', 'weight': 1.0},
 {'id': 901, 'category': 'tourism', 'term': 'Mount Fuji', 'weight': 0.9},
 {'id': 902, 'category': 'tourism', 'term': 'Fuji Five Lakes', 'weight': 0.9},
 {'id': 903, 'category': 'tourism', 'term': 'Lake Kawaguchi', 'weight': 0.9},
 {'id': 904, 'category': 'tourism', 'term': 'Hakone', 'weight': 0.9},
 {'id': 905, 'category': 'tourism', 'term': 'Nikko', 'weight': 0.9},
 {'id': 906, 'category': 'tourism', 'term': 'Kamakura', 'weight': 0.9},
 {'id': 907, 'category': 'tourism', 'term': 'Koyasan', 'weight': 0.9},
 {'id': 908, 'category': 'tourism', 'term': 'Kumano Kodo', 'weight': 0.9},
 {'id': 909, 'category': 'tourism', 'term': 'Shirakawa-go', 'weight': 0.9},
 {'id': 910, 'category': 'tourism', 'term': 'Gokayama', 'weight': 0.9},
 {'id': 911, 'category': 'tourism', 'term': 'Takayama', 'weight': 0.9},
 {'id': 912, 'category': 'tourism', 'term': 'Kanazawa tourism', 'weight': 0.9},
 {'id': 913, 'category': 'tourism', 'term': 'Higashi Chaya', 'weight': 0.9},
 {'id': 914, 'category': 'tourism', 'term': 'Kenrokuen', 'weight': 0.9},
 {'id': 915, 'category': 'tourism', 'term': 'Matsumoto Castle', 'weight': 0.9},
 {'id': 916, 'category': 'tourism', 'term': 'Himeji Castle', 'weight': 0.9},
 {'id': 917, 'category': 'tourism', 'term': 'Osaka Castle', 'weight': 0.9},
 {'id': 918, 'category': 'tourism', 'term': 'Nijo Castle', 'weight': 0.9},
 {'id': 919, 'category': 'tourism', 'term': 'Hiroshima Peace Memorial', 'weight': 0.9},
 {'id': 920, 'category': 'tourism', 'term': 'Atomic Bomb Dome', 'weight': 0.9},
 {'id': 921, 'category': 'tourism', 'term': 'Miyajima', 'weight': 0.9},
 {'id': 922, 'category': 'tourism', 'term': 'Itsukushima Shrine', 'weight': 0.9},
 {'id': 923, 'category': 'tourism', 'term': 'Fushimi Inari', 'weight': 0.9},
 {'id': 924, 'category': 'tourism', 'term': 'Kiyomizu-dera', 'weight': 0.9},
 {'id': 925, 'category': 'tourism', 'term': 'Kinkaku-ji', 'weight': 0.9},
 {'id': 926, 'category': 'tourism', 'term': 'Ginkaku-ji', 'weight': 0.9},
 {'id': 927, 'category': 'tourism', 'term': 'Arashiyama', 'weight': 0.9},
 {'id': 928, 'category': 'tourism', 'term': 'Bamboo Grove', 'weight': 0.9},
 {'id': 929, 'category': 'tourism', 'term': 'Gion', 'weight': 0.9},
 {'id': 930, 'category': 'tourism', 'term': 'Nishiki Market', 'weight': 0.9},
 {'id': 931, 'category': 'tourism', 'term': 'Nara Park', 'weight': 0.9},
 {'id': 932, 'category': 'tourism', 'term': 'Todaiji', 'weight': 0.9},
 {'id': 933, 'category': 'tourism', 'term': 'Kasuga Taisha', 'weight': 0.9},
 {'id': 934, 'category': 'tourism', 'term': 'Shibuya Crossing', 'weight': 0.9},
 {'id': 935, 'category': 'tourism', 'term': 'Tokyo Skytree', 'weight': 0.9},
 {'id': 936, 'category': 'tourism', 'term': 'Tokyo Tower', 'weight': 0.9},
 {'id': 937, 'category': 'tourism', 'term': 'Sensoji', 'weight': 0.9},
 {'id': 938, 'category': 'tourism', 'term': 'Meiji Shrine', 'weight': 0.9},
 {'id': 939, 'category': 'tourism', 'term': 'Tsukiji Outer Market', 'weight': 0.9},
 {'id': 940, 'category': 'tourism', 'term': 'teamLab Borderless', 'weight': 0.9},
 {'id': 941, 'category': 'tourism', 'term': 'teamLab Planets', 'weight': 0.9},
 {'id': 942, 'category': 'tourism', 'term': 'Universal Studios Osaka', 'weight': 0.9},
 {'id': 943, 'category': 'tourism', 'term': 'Tokyo Disneyland', 'weight': 0.9},
 {'id': 944, 'category': 'tourism', 'term': 'Tokyo DisneySea', 'weight': 0.9},
 {'id': 945, 'category': 'tourism', 'term': 'Ghibli Museum', 'weight': 0.9},
 {'id': 946, 'category': 'tourism', 'term': 'Ghibli Park tourism', 'weight': 0.9},
 {'id': 947, 'category': 'tourism', 'term': 'Hakone Open-Air Museum', 'weight': 0.9},
 {'id': 948, 'category': 'tourism', 'term': 'Naoshima art island', 'weight': 0.9},
 {'id': 949, 'category': 'tourism', 'term': 'Benesse Art Site', 'weight': 0.9},
 {'id': 950, 'category': 'tourism', 'term': 'Teshima', 'weight': 0.9},
 {'id': 951, 'category': 'tourism', 'term': 'Setouchi Triennale', 'weight': 0.9},
 {'id': 952, 'category': 'tourism', 'term': 'Shimanami Kaido', 'weight': 0.9},
 {'id': 953, 'category': 'tourism', 'term': 'Matsuyama Castle', 'weight': 0.9},
 {'id': 954, 'category': 'tourism', 'term': 'Dogo Onsen', 'weight': 0.9},
 {'id': 955, 'category': 'tourism', 'term': 'Beppu Onsen', 'weight': 0.9},
 {'id': 956, 'category': 'tourism', 'term': 'Yufuin', 'weight': 0.9},
 {'id': 957, 'category': 'tourism', 'term': 'Kurokawa Onsen', 'weight': 0.9},
 {'id': 958, 'category': 'tourism', 'term': 'Kinosaki Onsen', 'weight': 0.9},
 {'id': 959, 'category': 'tourism', 'term': 'Arima Onsen', 'weight': 0.9},
 {'id': 960, 'category': 'tourism', 'term': 'Kusatsu Onsen', 'weight': 0.9},
 {'id': 961, 'category': 'tourism', 'term': 'Nozawa Onsen', 'weight': 0.9},
 {'id': 962, 'category': 'tourism', 'term': 'Ginzan Onsen', 'weight': 0.9},
 {'id': 963, 'category': 'tourism', 'term': 'Zao Onsen', 'weight': 0.9},
 {'id': 964, 'category': 'tourism', 'term': 'Jigokudani Monkey Park', 'weight': 0.9},
 {'id': 965, 'category': 'tourism', 'term': 'snow monkeys', 'weight': 0.9},
 {'id': 966, 'category': 'tourism', 'term': 'Sapporo Snow Festival', 'weight': 0.9},
 {'id': 967, 'category': 'tourism', 'term': 'Otaru Canal', 'weight': 0.9},
 {'id': 968, 'category': 'tourism', 'term': 'Furano lavender', 'weight': 0.9},
 {'id': 969, 'category': 'tourism', 'term': 'Biei Blue Pond', 'weight': 0.9},
 {'id': 970, 'category': 'tourism', 'term': 'Niseko', 'weight': 0.9},
 {'id': 971, 'category': 'tourism', 'term': 'Rusutsu', 'weight': 0.9},
 {'id': 972, 'category': 'tourism', 'term': 'Hakuba', 'weight': 0.9},
 {'id': 973, 'category': 'tourism', 'term': 'Nozawa ski resort', 'weight': 0.9},
 {'id': 974, 'category': 'tourism', 'term': 'Shiga Kogen', 'weight': 0.9},
 {'id': 975, 'category': 'tourism', 'term': 'Okinawa tourism', 'weight': 0.9},
 {'id': 976, 'category': 'tourism', 'term': 'Naha tourism', 'weight': 0.9},
 {'id': 977, 'category': 'tourism', 'term': 'Shuri Castle', 'weight': 0.9},
 {'id': 978, 'category': 'tourism', 'term': 'Ishigaki tourism', 'weight': 0.9},
 {'id': 979, 'category': 'tourism', 'term': 'Miyakojima beaches', 'weight': 0.9},
 {'id': 980, 'category': 'tourism', 'term': 'Kerama Islands', 'weight': 0.9},
 {'id': 981, 'category': 'tourism', 'term': 'Churaumi Aquarium', 'weight': 0.9},
 {'id': 982, 'category': 'tourism', 'term': 'Yakushima', 'weight': 0.9},
 {'id': 983, 'category': 'tourism', 'term': 'Jomon Sugi', 'weight': 0.9},
 {'id': 984, 'category': 'tourism', 'term': 'Amami Oshima tourism', 'weight': 0.9},
 {'id': 985, 'category': 'tourism', 'term': 'Kagoshima tourism', 'weight': 0.9},
 {'id': 986, 'category': 'tourism', 'term': 'Sakurajima tourism', 'weight': 0.9},
 {'id': 987, 'category': 'tourism', 'term': 'Fukuoka yatai', 'weight': 0.9},
 {'id': 988, 'category': 'tourism', 'term': 'Dazaifu Tenmangu', 'weight': 0.9},
 {'id': 989, 'category': 'tourism', 'term': 'Nagasaki lantern festival', 'weight': 0.9},
 {'id': 990, 'category': 'tourism', 'term': 'Gunkanjima', 'weight': 0.9},
 {'id': 991, 'category': 'tourism', 'term': 'Kumamoto Castle', 'weight': 0.9},
 {'id': 992, 'category': 'tourism', 'term': 'Aso caldera', 'weight': 0.9},
 {'id': 993, 'category': 'tourism', 'term': 'Iya Valley', 'weight': 0.9},
 {'id': 994, 'category': 'tourism', 'term': 'Tottori Sand Dunes', 'weight': 0.9},
 {'id': 995, 'category': 'tourism', 'term': 'Amanohashidate', 'weight': 0.9},
 {'id': 996, 'category': 'tourism', 'term': 'Ise Grand Shrine', 'weight': 0.9},
 {'id': 997, 'category': 'tourism', 'term': 'Nakasendo trail', 'weight': 0.9},
 {'id': 998, 'category': 'tourism', 'term': 'Tokaido trail', 'weight': 0.9},
 {'id': 999, 'category': 'tourism', 'term': 'bullet train pass', 'weight': 0.9},
 {'id': 1000, 'category': 'tourism', 'term': 'rail pass', 'weight': 0.9}]

JAPAN_SPECIFIC_TERMS_1000 = [r["term"] for r in JAPAN_SPECIFIC_TERMS_1000_RECORDS]
TERM_CATEGORY_BY_TERM = {r["term"]: r["category"] for r in JAPAN_SPECIFIC_TERMS_1000_RECORDS}
TERM_WEIGHT_BY_TERM = {r["term"]: float(r.get("weight", 1.0)) for r in JAPAN_SPECIFIC_TERMS_1000_RECORDS}
REPEAT_DECAY_FACTOR = 0.5
assert len(JAPAN_SPECIFIC_TERMS_1000) == 1000
assert all("japan" not in t.lower() and "japanese" not in t.lower() for t in JAPAN_SPECIFIC_TERMS_1000)

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
def compiled_term_patterns() -> list[tuple[str, str, float, re.Pattern]]:
    return [
        (
            str(r["term"]),
            str(r.get("category", "")),
            float(r.get("weight", 1.0)),
            term_pattern(str(r["term"])),
        )
        for r in JAPAN_SPECIFIC_TERMS_1000_RECORDS
    ]


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


def decayed_occurrence_score(n: int, decay_factor: float = REPEAT_DECAY_FACTOR) -> float:
    """Return 1 + 1/2 + 1/4 + ... for repeated appearances of one term."""
    if n <= 0:
        return 0.0
    # Closed form for geometric series; avoids loops and makes the scoring explicit.
    if decay_factor == 1.0:
        return float(n)
    return (1.0 - (decay_factor ** n)) / (1.0 - decay_factor)


def count_japan_terms(item: dict[str, Any], include_summary_for_scoring: bool) -> dict[str, Any]:
    text = build_scoring_text(item, include_summary_for_scoring)
    total_hits = 0
    decayed_weighted_hits = 0.0
    matched_terms: list[str] = []
    matched_terms_with_counts: list[str] = []
    term_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    term_decayed_scores: dict[str, float] = {}

    for term, category, base_weight, pat in compiled_term_patterns():
        n = len(pat.findall(text))
        if n <= 0:
            continue
        total_hits += n

        noise_weight = NOISY_LOW_WEIGHT_TERMS.get(term.lower(), 1.0)
        term_score = base_weight * noise_weight * decayed_occurrence_score(n)
        decayed_weighted_hits += term_score

        matched_terms.append(term)
        term_counts[term] = n
        term_decayed_scores[term] = term_score
        category_counts[category] = category_counts.get(category, 0) + 1
        matched_terms_with_counts.append(f"{term}×{n}={term_score:.2f}")

    return {
        "term_total_hits": total_hits,
        "term_decayed_hits": decayed_weighted_hits,
        "term_weighted_hits": decayed_weighted_hits,  # backward-compatible internal name
        "unique_term_hits": len(matched_terms),
        "matched_terms": matched_terms,
        "matched_terms_with_counts": matched_terms_with_counts,
        "term_counts": term_counts,
        "term_decayed_scores": term_decayed_scores,
        "category_counts": category_counts,
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
    ranking_limit: int,
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
                # raw_score is the score before the cross-article category-diversity decay.
                "raw_score": round(score, 2),
                "score": round(score, 2),
                "category_decay_rank": 1,
                "category_decay_multiplier": 1.0,
                "term_total_hits": hit["term_total_hits"],
                "term_decayed_hits": round(hit["term_decayed_hits"], 2),
                "unique_term_hits": hit["unique_term_hits"],
                "matched_terms": ", ".join(hit["matched_terms_with_counts"][:18]),
                "term_categories": ", ".join(f"{k}:{v}" for k, v in sorted(hit["category_counts"].items())),
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
        # 1) Sort by raw score within each RSS category.
        # 2) Apply category-diversity decay: for each already-higher raw-score article
        #    in the same category, halve the score.
        #    Example: category top=1.0x, second=0.5x, third=0.25x.
        raw_sort_cols = ["raw_score", "term_decayed_hits", "term_total_hits", "unique_term_hits", "published"]
        df = df.sort_values(by=raw_sort_cols, ascending=[False, False, False, False, False]).reset_index(drop=True)
        df["category_decay_rank"] = df.groupby("category", sort=False).cumcount() + 1
        df["category_decay_multiplier"] = 0.5 ** (df["category_decay_rank"] - 1)
        df["score"] = (df["raw_score"] * df["category_decay_multiplier"]).round(2)

        # 3) Global ranking after category decay.
        df = df.sort_values(
            by=["score", "raw_score", "term_decayed_hits", "term_total_hits", "unique_term_hits", "published"],
            ascending=[False, False, False, False, False, False],
        ).head(ranking_limit).reset_index(drop=True)
        df.insert(0, "rank", range(1, len(df) + 1))

    err_df = pd.DataFrame(errors)
    return df, err_df


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL).encode("utf-8-sig")


def render_result_cards(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        st.markdown(f"### {int(row['rank'])}. [{row['title']}]({row['url']})")
        st.caption(
            f"score={row['score']} | raw={row.get('raw_score', '')} | cat decay={row.get('category_decay_multiplier', '')} | raw hits={row['term_total_hits']} | decayed={row.get('term_decayed_hits', '')} | "
            f"unique={row['unique_term_hits']} | {row['source']} / {row['category']} | "
            f"feed position={row['feed_position']} | {row['published'] or 'date unknown'}"
        )
        st.write("**Matched terms:** " + str(row["matched_terms"]))
        st.divider()


def main() -> None:
    st.set_page_config(page_title="海外日本バズRSSランキング", layout="wide")
    st.title("海外日本バズRSSランキング")
    st.caption(
        "海外RSSの英語タイトル記事だけを巡回し、日本特有1000語がタイトル・URL・RSSメタデータに多く出る記事をランキング表示します。表示件数は最大100件まで調整できます。"
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
        ranking_limit = st.slider(
            "ランキング表示件数",
            min_value=1,
            max_value=MAX_RANKING_LIMIT,
            value=DEFAULT_RANKING_LIMIT,
            step=1,
        )

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
    st.caption(
        "同じ記事内で同一語が複数回出る場合は、1回目=1.0、2回目=0.5、3回目=0.25... と半減加点します。"
    )
    st.caption(
        "さらに全体ランキング前に、同一RSSカテゴリ内の上位raw score記事1本につきスコアを半減します。例: 同カテゴリ1位=1.0倍、2位=0.5倍、3位=0.25倍。"
    )

    if not run:
        st.subheader("仕様")
        st.write(
            f"登録RSS: {len(RSS_FEEDS)}本 / 日本特有語: {len(JAPAN_SPECIFIC_TERMS_1000)}語 / ランキング表示上限: {MAX_RANKING_LIMIT}件"
        )
        st.write("サイドバーで期間・媒体・カテゴリを指定して実行してください。")
        with st.expander("日本特有語1000語を見る"):
            st.write(", ".join(JAPAN_SPECIFIC_TERMS_1000))
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
            ranking_limit=ranking_limit,
        )

    st.subheader("ランキング")
    if df.empty:
        st.warning("条件に合う記事が見つかりませんでした。期間を長くする、取得件数を増やす、媒体カテゴリを増やすなどを試してください。")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("表示件数", f"{len(df)} / {ranking_limit}")
        c2.metric("最高補正後スコア", float(df["score"].max()))
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
            "raw_score",
            "category_decay_rank",
            "category_decay_multiplier",
            "term_total_hits",
            "term_decayed_hits",
            "unique_term_hits",
            "term_categories",
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
