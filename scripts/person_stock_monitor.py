#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor market-moving public figures and send US stock impact notes to Feishu.

This script is intentionally standalone so it can run in a lightweight GitHub
Actions workflow without installing the full stock analysis dependency set.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests


DEFAULT_PEOPLE = [
    {
        "name": "Donald Trump",
        "label": "特朗普",
        "query": '"Donald Trump" (stock OR stocks OR shares OR market OR tariff OR AI OR chip OR oil OR pharma OR bank)',
    },
    {
        "name": "Jensen Huang",
        "label": "黄仁勋",
        "query": '("Jensen Huang" OR "Nvidia CEO") (stock OR shares OR AI OR chip OR semiconductor OR datacenter)',
    },
    {
        "name": "Elon Musk",
        "label": "马斯克",
        "query": '"Elon Musk" (stock OR shares OR Tesla OR xAI OR SpaceX OR AI OR robotaxi OR chips)',
    },
    {
        "name": "Nancy Pelosi",
        "label": "佩洛西",
        "query": '"Nancy Pelosi" (stock OR stocks OR shares OR trading OR portfolio OR Nvidia OR options OR Congress)',
    },
]


COMPANY_ALIASES: Dict[str, Sequence[str]] = {
    "AAPL": ("Apple",),
    "AEHR": ("Aehr Test Systems", "Aehr"),
    "ALAB": ("Astera Labs",),
    "AMD": ("Advanced Micro Devices", "AMD"),
    "AMT": ("American Tower",),
    "AMZN": ("Amazon",),
    "ANET": ("Arista Networks", "Arista"),
    "APH": ("Amphenol",),
    "APP": ("AppLovin",),
    "APLD": ("Applied Digital",),
    "ARM": ("Arm Holdings", "Arm"),
    "ARKK": ("ARK Innovation", "ARKK"),
    "ASML": ("ASML",),
    "AVGO": ("Broadcom",),
    "AXTI": ("AXT",),
    "BABA": ("Alibaba",),
    "BE": ("Bloom Energy",),
    "BITB": ("Bitwise Bitcoin ETF", "BITB"),
    "BLK": ("BlackRock",),
    "BRK": ("Berkshire Hathaway", "Berkshire"),
    "BX": ("Blackstone",),
    "CAT": ("Caterpillar",),
    "CEG": ("Constellation Energy",),
    "COHR": ("Coherent",),
    "COIN": ("Coinbase",),
    "CORZ": ("Core Scientific",),
    "COST": ("Costco",),
    "CRM": ("Salesforce",),
    "CVX": ("Chevron",),
    "DELL": ("Dell",),
    "DIS": ("Disney", "Walt Disney"),
    "DNUT": ("Krispy Kreme",),
    "DOW": ("Dow Inc", "Dow Chemical"),
    "EQIX": ("Equinix",),
    "EQT": ("EQT",),
    "FN": ("Fabrinet",),
    "FTI": ("TechnipFMC",),
    "GEV": ("GE Vernova",),
    "GFI": ("Gold Fields",),
    "GLW": ("Corning",),
    "GOOG": ("Google", "Alphabet"),
    "GOOGL": ("Google", "Alphabet"),
    "GS": ("Goldman Sachs",),
    "HIMS": ("Hims & Hers", "Hims"),
    "HOOD": ("Robinhood",),
    "HSBC": ("HSBC",),
    "IBIT": ("iShares Bitcoin Trust", "IBIT"),
    "ILMN": ("Illumina",),
    "INTC": ("Intel",),
    "IREN": ("Iris Energy", "IREN"),
    "ISRG": ("Intuitive Surgical",),
    "ITOCY": ("Itochu",),
    "JD": ("JD.com", "JD"),
    "JPM": ("JPMorgan", "JP Morgan"),
    "KHC": ("Kraft Heinz",),
    "KKR": ("KKR",),
    "KLAC": ("KLA", "KLA Corp"),
    "KO": ("Coca-Cola", "Coca Cola"),
    "LASE": ("Laser Photonics",),
    "LCID": ("Lucid", "Lucid Group"),
    "LLY": ("Eli Lilly", "Lilly"),
    "LNC": ("Lincoln National",),
    "LVS": ("Las Vegas Sands",),
    "LWLG": ("Lightwave Logic",),
    "MCD": ("McDonald's", "McDonalds"),
    "META": ("Meta", "Facebook"),
    "MNST": ("Monster Beverage",),
    "MRK": ("Merck",),
    "MRVL": ("Marvell", "Marvell Technology"),
    "MSFT": ("Microsoft",),
    "MSTR": ("MicroStrategy", "Strategy"),
    "MTSUY": ("Mitsui",),
    "MU": ("Micron",),
    "MX": ("Magnachip",),
    "NBIS": ("Nebius",),
    "NET": ("Cloudflare",),
    "NFLX": ("Netflix",),
    "NOK": ("Nokia",),
    "NVDA": ("Nvidia", "NVIDIA"),
    "NVO": ("Novo Nordisk",),
    "NVTS": ("Navitas", "Navitas Semiconductor"),
    "ORLY": ("O'Reilly Automotive", "O'Reilly"),
    "PEP": ("PepsiCo", "Pepsi"),
    "PDD": ("PDD", "Pinduoduo", "Temu"),
    "PG": ("Procter & Gamble", "P&G"),
    "PLD": ("Prologis",),
    "PLTR": ("Palantir",),
    "PM": ("Philip Morris",),
    "POET": ("POET Technologies",),
    "QCOM": ("Qualcomm",),
    "QQQ": ("Invesco QQQ", "Nasdaq 100"),
    "QQQI": ("QQQI",),
    "RDDT": ("Reddit",),
    "RY": ("Royal Bank of Canada", "RBC"),
    "SAP": ("SAP",),
    "SBAC": ("SBA Communications",),
    "SCHW": ("Charles Schwab", "Schwab"),
    "SLB": ("SLB", "Schlumberger"),
    "SOXL": ("SOXL", "Direxion Semiconductor"),
    "SOXX": ("SOXX", "iShares Semiconductor"),
    "SPX": ("S&P 500", "SPX"),
    "STX": ("Seagate",),
    "SUM": ("Summit Materials",),
    "TEM": ("Tempus AI", "Tempus"),
    "TQQQ": ("TQQQ",),
    "TSLA": ("Tesla",),
    "TSM": ("Taiwan Semiconductor", "TSMC"),
    "TSEM": ("Tower Semiconductor",),
    "UNH": ("UnitedHealth", "United Health"),
    "VNM": ("VanEck Vietnam", "VNM"),
    "VOO": ("Vanguard S&P 500", "VOO"),
    "VRT": ("Vertiv",),
    "VRSN": ("Verisign",),
    "VST": ("Vistra",),
    "WDC": ("Western Digital",),
    "WOLF": ("Wolfspeed",),
    "WYNN": ("Wynn Resorts",),
    "XOM": ("Exxon", "Exxon Mobil", "ExxonMobil"),
    "YUM": ("Yum Brands", "Yum! Brands"),
}


@dataclass
class NewsItem:
    person_label: str
    person_name: str
    title: str
    link: str
    source: str
    published_at: str
    summary: str
    tickers: List[str]
    fingerprint: str


def env_int(name: str, default: int, *, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def parse_stock_list(raw: str) -> List[str]:
    seen = set()
    result: List[str] = []
    for token in re.split(r"[\s,;]+", raw or ""):
        ticker = token.strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        result.append(ticker)
    return result


def parse_people() -> List[Dict[str, str]]:
    raw = os.getenv("PERSON_MONITOR_PEOPLE_JSON", "").strip()
    if not raw:
        return DEFAULT_PEOPLE
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print("PERSON_MONITOR_PEOPLE_JSON is invalid; using defaults", file=sys.stderr)
        return DEFAULT_PEOPLE
    people = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        label = str(item.get("label") or name).strip()
        query = str(item.get("query") or name).strip()
        if name and query:
            people.append({"name": name, "label": label or name, "query": query})
    return people or DEFAULT_PEOPLE


def google_news_rss_url(query: str) -> str:
    encoded = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def parse_pub_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_person_items(person: Dict[str, str], max_items: int, lookback_hours: int) -> List[Dict[str, str]]:
    url = google_news_rss_url(person["query"])
    headers = {"User-Agent": "daily-stock-analysis-person-monitor/1.0"}
    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items: List[Dict[str, str]] = []

    for node in root.findall(".//item"):
        title = clean_text(node.findtext("title", ""))
        link = clean_text(node.findtext("link", ""))
        summary = clean_text(node.findtext("description", ""))
        pub_raw = clean_text(node.findtext("pubDate", ""))
        source = clean_text(node.findtext("source", ""))
        published = parse_pub_date(pub_raw)
        if published and published < cutoff:
            continue
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "source": source,
                "published_at": published.isoformat() if published else pub_raw,
            }
        )
        if len(items) >= max_items:
            break
    return items


def ticker_pattern(ticker: str) -> re.Pattern[str]:
    escaped = re.escape(ticker)
    if len(ticker) <= 2:
        return re.compile(rf"(?<![A-Za-z0-9])(?:\${escaped}|NASDAQ:{escaped}|NYSE:{escaped})(?![A-Za-z0-9])")
    return re.compile(rf"(?<![A-Za-z0-9])(?:\${escaped}|NASDAQ:{escaped}|NYSE:{escaped}|{escaped})(?![A-Za-z0-9])")


def alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def extract_tickers(text: str, watchlist: Sequence[str]) -> List[str]:
    matched = set()
    for ticker in watchlist:
        if ticker_pattern(ticker).search(text):
            matched.add(ticker)
            continue
        for alias in COMPANY_ALIASES.get(ticker, ()):
            if alias_pattern(alias).search(text):
                matched.add(ticker)
                break
    return sorted(matched)


def fingerprint_for(person_label: str, title: str, link: str) -> str:
    material = f"{person_label}|{title}|{link}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:20]


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"seen": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"seen": []}


def save_state(path: Path, seen: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    limited = list(dict.fromkeys(seen))[-1000:]
    path.write_text(json.dumps({"seen": limited}, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_relevant_items(people: Sequence[Dict[str, str]], watchlist: Sequence[str]) -> List[NewsItem]:
    lookback_hours = env_int("PERSON_MONITOR_LOOKBACK_HOURS", 24, minimum=1, maximum=168)
    max_items = env_int("PERSON_MONITOR_MAX_ITEMS_PER_PERSON", 12, minimum=1, maximum=50)
    relevant: List[NewsItem] = []

    for person in people:
        try:
            raw_items = fetch_person_items(person, max_items=max_items, lookback_hours=lookback_hours)
        except Exception as exc:
            print(f"Failed to fetch news for {person['label']}: {exc}", file=sys.stderr)
            continue

        for item in raw_items:
            combined = f"{item['title']} {item['summary']}"
            tickers = extract_tickers(combined, watchlist)
            if not tickers:
                continue
            relevant.append(
                NewsItem(
                    person_label=person["label"],
                    person_name=person["name"],
                    title=item["title"],
                    link=item["link"],
                    source=item["source"],
                    published_at=item["published_at"],
                    summary=item["summary"],
                    tickers=tickers,
                    fingerprint=fingerprint_for(person["label"], item["title"], item["link"]),
                )
            )
    return relevant


def analyze_with_openai(items: Sequence[NewsItem]) -> Dict[str, Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not items:
        return {}

    try:
        from openai import OpenAI
    except Exception as exc:
        print(f"OpenAI SDK unavailable: {exc}", file=sys.stderr)
        return {}

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    payload = [
        {
            "id": item.fingerprint,
            "person": item.person_label,
            "title": item.title,
            "source": item.source,
            "published_at": item.published_at,
            "tickers": item.tickers,
            "summary": item.summary[:800],
        }
        for item in items[:20]
    ]
    prompt = (
        "你是美股事件驱动分析助手。请基于新闻标题和摘要，判断人物言论/动向对相关美股的可能影响。"
        "只输出 JSON 数组，每项字段为: id, tickers, direction, impact_level, confidence, summary_zh, reason_zh, watch_points_zh。"
        "direction 只能是 positive, negative, mixed, unclear。impact_level 只能是 high, medium, low。"
        "confidence 只能是 high, medium, low。不要编造新闻中没有的信息。"
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content or "[]"
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE | re.DOTALL).strip()
        parsed = json.loads(content)
    except Exception as exc:
        print(f"OpenAI analysis failed: {exc}", file=sys.stderr)
        return {}

    results: Dict[str, Dict[str, Any]] = {}
    if isinstance(parsed, list):
        for row in parsed:
            if isinstance(row, dict) and row.get("id"):
                results[str(row["id"])] = row
    return results


def fallback_analysis(item: NewsItem) -> Dict[str, Any]:
    lowered = f"{item.title} {item.summary}".lower()
    negative_words = ("probe", "investigation", "ban", "tariff", "lawsuit", "sell", "sold", "crackdown", "risk")
    positive_words = ("buy", "bought", "deal", "approval", "partnership", "investment", "rally", "surge", "upgrade")
    direction = "unclear"
    if any(word in lowered for word in negative_words):
        direction = "negative"
    if any(word in lowered for word in positive_words):
        direction = "mixed" if direction == "negative" else "positive"
    return {
        "tickers": item.tickers,
        "direction": direction,
        "impact_level": "medium" if direction != "unclear" else "low",
        "confidence": "low",
        "summary_zh": "检测到人物相关报道提及自选股，需结合原文进一步确认。",
        "reason_zh": "未启用或未成功调用 OpenAI 分析，已使用关键词降级判断。",
        "watch_points_zh": "关注后续权威媒体报道、盘前/盘后价格变化、成交量和公司回应。",
    }


def direction_label(direction: str) -> str:
    mapping = {
        "positive": "偏利好",
        "negative": "偏利空",
        "mixed": "多空混合",
        "unclear": "影响不明",
    }
    return mapping.get(direction, "影响不明")


def build_message(items: Sequence[NewsItem], analyses: Dict[str, Dict[str, Any]]) -> str:
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    lines = [
        "美股人物动向监测",
        f"生成时间: {now:%Y-%m-%d %H:%M:%S} 北京时间",
        f"新命中: {len(items)} 条",
        "",
    ]
    for idx, item in enumerate(items, 1):
        analysis = analyses.get(item.fingerprint) or fallback_analysis(item)
        tickers = ", ".join(analysis.get("tickers") or item.tickers)
        direction = direction_label(str(analysis.get("direction", "unclear")))
        impact = str(analysis.get("impact_level", "low"))
        confidence = str(analysis.get("confidence", "low"))
        lines.extend(
            [
                f"{idx}. {item.person_label} - {tickers}",
                f"标题: {item.title}",
                f"来源: {item.source or 'Google News'} | 时间: {item.published_at}",
                f"影响: {direction} | 强度: {impact} | 置信度: {confidence}",
                f"摘要: {analysis.get('summary_zh', '').strip()}",
                f"原因: {analysis.get('reason_zh', '').strip()}",
                f"关注: {analysis.get('watch_points_zh', '').strip()}",
                f"链接: {item.link}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def feishu_security_fields(secret: str) -> Dict[str, str]:
    if not secret:
        return {}
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    return {"timestamp": timestamp, "sign": sign}


def send_feishu(message: str) -> bool:
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("FEISHU_WEBHOOK_URL is not configured", file=sys.stderr)
        return False
    keyword = os.getenv("FEISHU_WEBHOOK_KEYWORD", "").strip()
    secret = os.getenv("FEISHU_WEBHOOK_SECRET", "").strip()
    content = f"{keyword}\n{message}" if keyword else message
    payload: Dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "美股人物动向监测"}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content[:18000]}}],
        },
    }
    payload.update(feishu_security_fields(secret))
    response = requests.post(webhook_url, json=payload, timeout=30)
    try:
        data = response.json()
    except ValueError:
        data = {"status_code": response.status_code, "text": response.text}
    code = data.get("code", data.get("StatusCode"))
    ok = response.status_code == 200 and code == 0
    if not ok:
        print(f"Feishu send failed: {data}", file=sys.stderr)
    return ok


def main() -> int:
    watchlist = parse_stock_list(os.getenv("STOCK_LIST", ""))
    if not watchlist:
        print("STOCK_LIST is empty", file=sys.stderr)
        return 2

    state_path = Path(os.getenv("PERSON_MONITOR_STATE_PATH", ".person-monitor-state/seen.json"))
    state = load_state(state_path)
    seen = list(state.get("seen") or [])
    seen_set = set(str(item) for item in seen)
    force_notify = os.getenv("PERSON_MONITOR_FORCE_NOTIFY", "false").lower() == "true"
    dry_run = os.getenv("PERSON_MONITOR_DRY_RUN", "false").lower() == "true"

    items = collect_relevant_items(parse_people(), watchlist)
    new_items = [item for item in items if force_notify or item.fingerprint not in seen_set]
    limit = env_int("PERSON_MONITOR_MAX_NOTIFY_ITEMS", 12, minimum=1, maximum=30)
    new_items = new_items[:limit]

    print(f"Collected relevant items: {len(items)}; new items: {len(new_items)}")

    if not new_items:
        save_state(state_path, seen)
        print("No new person-stock items to notify")
        return 0

    analyses = analyze_with_openai(new_items)
    message = build_message(new_items, analyses)
    print(message if dry_run else f"Prepared Feishu message for {len(new_items)} items")

    if not dry_run and not send_feishu(message):
        return 1

    seen.extend(item.fingerprint for item in new_items)
    save_state(state_path, seen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
