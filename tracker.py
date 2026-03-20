#!/usr/bin/env python3
"""
Multi-Platform Social Listening Tracker
Tracks keywords across Hacker News, Reddit, Google News, Lobsters, Stack Overflow, and dev.to
"""

import csv
import datetime
import time
import urllib.parse
from collections import defaultdict
import requests
import feedparser

# ═══════════════════════════════════════════════════════
#  KEYWORDS TO TRACK  — edit these anytime
# ═══════════════════════════════════════════════════════
KEYWORDS = [
    # Fireworks AI
    "Fireworks AI",
    "fireworks.ai",
    "FireAttention",
    "Fireworks inference",

    # Kimi / Moonshot AI
    "Kimi k2.5 turbo",
    "Kimi k2",
    "Moonshot AI",
    "kimi.ai",

    # Competitive landscape
    "open source LLM inference",
    "LLM API pricing",
    "fast inference",
    "MoE model",
]

# ═══════════════════════════════════════════════════════
#  TIME RANGE  — how far back to look
#  Options: "24h"  |  "week"  |  "month"
# ═══════════════════════════════════════════════════════
TIME_RANGE = "week"

# ═══════════════════════════════════════════════════════
#  ENGINE — no need to edit below this line
# ═══════════════════════════════════════════════════════

# Map TIME_RANGE to platform-specific values
_reddit_time = {"24h": "day", "week": "week", "month": "month"}[TIME_RANGE]
_hn_cutoff   = int(time.time() - {"24h": 86400, "week": 604800, "month": 2592000}[TIME_RANGE])
_date_cutoff = datetime.datetime.now() - {"24h": datetime.timedelta(days=1),
                                           "week": datetime.timedelta(weeks=1),
                                           "month": datetime.timedelta(days=30)}[TIME_RANGE]

results = []

def is_relevant(title, keyword):
    """Check that at least one meaningful word from the keyword appears in the title."""
    title_lower = title.lower()
    # For short/single keywords, do a direct check
    if " " not in keyword:
        return keyword.lower() in title_lower
    # For phrase keywords, check if the full phrase OR the most distinctive word appears
    if keyword.lower() in title_lower:
        return True
    # Keep the longest word as the signal word (avoids matching "AI", "model", etc.)
    signal = max(keyword.split(), key=len)
    return signal.lower() in title_lower

def add(platform, title, url, score, keyword):
    if not is_relevant(title, keyword):
        return
    results.append({
        "platform":   platform,
        "keyword":    keyword,
        "title":      title[:150],
        "url":        url,
        "score":      score,
        "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    })


# ─── HACKER NEWS ──────────────────────────────────────
def fetch_hn(keyword):
    print(f"  [Hacker News]  {keyword}")
    try:
        r = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query":          keyword,
                "tags":           "story",
                "hitsPerPage":    20,
                "numericFilters": f"created_at_i>{_hn_cutoff}",
            },
            timeout=10,
        )
        for hit in r.json().get("hits", []):
            add(
                platform="Hacker News",
                title=hit.get("title", "(no title)"),
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                score=hit.get("points", 0),
                keyword=keyword,
            )
    except Exception as e:
        print(f"    ✗ HN error: {e}")


# ─── REDDIT ───────────────────────────────────────────
def fetch_reddit(keyword):
    print(f"  [Reddit]       {keyword}")
    try:
        headers = {"User-Agent": "social-tracker/1.0"}
        r = requests.get(
            "https://www.reddit.com/search.json",
            headers=headers,
            params={"q": keyword, "sort": "top", "t": _reddit_time, "limit": 20},
            timeout=10,
        )
        for post in r.json()["data"]["children"]:
            d = post["data"]
            add(
                platform="Reddit",
                title=d["title"],
                url=f"https://reddit.com{d['permalink']}",
                score=d["score"],
                keyword=keyword,
            )
    except Exception as e:
        print(f"    ✗ Reddit error: {e}")


# ─── GOOGLE NEWS ──────────────────────────────────────
def fetch_google_news(keyword):
    print(f"  [Google News]  {keyword}")
    # Wrap in quotes for exact phrase matching
    quoted = urllib.parse.quote(f'"{keyword}"')
    url = f"https://news.google.com/rss/search?q={quoted}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:20]:
            # Filter by date
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                entry_dt = datetime.datetime(*entry.published_parsed[:6])
                if entry_dt < _date_cutoff:
                    continue
            add(
                platform="Google News",
                title=entry.get("title", "(no title)"),
                url=entry.get("link", ""),
                score=0,
                keyword=keyword,
            )
    except Exception as e:
        print(f"    ✗ Google News error: {e}")


# ─── LOBSTERS ─────────────────────────────────────────
# Lobsters has no search API — fetch tag feeds and filter by keyword
_LOBSTERS_TAGS = ["llm", "ai", "programming"]
_lobsters_cache = {}

def fetch_lobsters(keyword):
    print(f"  [Lobsters]     {keyword}")
    try:
        for tag in _LOBSTERS_TAGS:
            if tag not in _lobsters_cache:
                r = requests.get(f"https://lobste.rs/t/{tag}.json", timeout=10)
                _lobsters_cache[tag] = r.json() if isinstance(r.json(), list) else []
            for story in _lobsters_cache[tag]:
                created = story.get("created_at", "")[:10]
                if created:
                    story_dt = datetime.datetime.strptime(created, "%Y-%m-%d")
                    if story_dt < _date_cutoff:
                        continue
                add(
                    platform="Lobsters",
                    title=story.get("title", "(no title)"),
                    url=story.get("url") or f"https://lobste.rs{story.get('comments_url', '')}",
                    score=story.get("score", 0),
                    keyword=keyword,
                )
    except Exception as e:
        print(f"    ✗ Lobsters error: {e}")


# ─── STACK OVERFLOW ───────────────────────────────────
def fetch_stackoverflow(keyword):
    print(f"  [Stack Overflow] {keyword}")
    try:
        r = requests.get(
            "https://api.stackexchange.com/2.3/search",
            params={
                "order":    "desc",
                "sort":     "relevance",
                "intitle":  keyword,
                "site":     "stackoverflow",
                "pagesize": 20,
                "fromdate": _hn_cutoff,
            },
            timeout=10,
        )
        for item in r.json().get("items", []):
            add(
                platform="Stack Overflow",
                title=item.get("title", "(no title)"),
                url=item.get("link", ""),
                score=item.get("score", 0),
                keyword=keyword,
            )
    except Exception as e:
        print(f"    ✗ Stack Overflow error: {e}")


# ─── DEV.TO ───────────────────────────────────────────
# dev.to search is unreliable — fetch tag feeds and filter by keyword
_DEVTO_TAGS = ["llm", "ai", "machinelearning"]
_devto_cache = {}

def fetch_devto(keyword):
    print(f"  [dev.to]       {keyword}")
    try:
        for tag in _DEVTO_TAGS:
            if tag not in _devto_cache:
                r = requests.get(
                    "https://dev.to/api/articles",
                    params={"tag": tag, "per_page": 30, "state": "rising"},
                    headers={"User-Agent": "social-tracker/1.0"},
                    timeout=10,
                )
                _devto_cache[tag] = r.json() if isinstance(r.json(), list) else []
            for item in _devto_cache[tag]:
                published = item.get("published_at", "")[:10]
                if published:
                    pub_dt = datetime.datetime.strptime(published, "%Y-%m-%d")
                    if pub_dt < _date_cutoff:
                        continue
                add(
                    platform="dev.to",
                    title=item.get("title", "(no title)"),
                    url=item.get("url", ""),
                    score=item.get("positive_reactions_count", 0),
                    keyword=keyword,
                )
    except Exception as e:
        print(f"    ✗ dev.to error: {e}")


# ─── RUN ──────────────────────────────────────────────
print("\n" + "═" * 60)
print("  Social Listening Tracker")
print(f"  Time range: {TIME_RANGE}")
print("  Keywords:", ", ".join(KEYWORDS))
print("═" * 60)
print("\nFetching...\n")

for kw in KEYWORDS:
    fetch_hn(kw)
    fetch_reddit(kw)
    fetch_google_news(kw)
    fetch_lobsters(kw)
    fetch_stackoverflow(kw)
    fetch_devto(kw)

# Sort all results by score descending
results.sort(key=lambda x: x["score"], reverse=True)


# ─── DISPLAY (top 20 per keyword per platform) ────────
DISPLAY_LIMIT = 20

counts  = defaultdict(int)
display = []
for r in results:
    key = (r["keyword"], r["platform"])
    if counts[key] < DISPLAY_LIMIT:
        display.append(r)
        counts[key] += 1

print(f"\n\n{'Rank':<5} {'Score':>6}  {'Platform':<14} {'Keyword':<22} Title")
print("─" * 105)

for i, r in enumerate(display, 1):
    title_preview = r["title"][:52] + ("…" if len(r["title"]) > 52 else "")
    kw_short      = r["keyword"][:20]
    print(f"{i:<5} {r['score']:>6}  {r['platform']:<14} {kw_short:<22} {title_preview}")
    print(f"       {'':>6}  {'':14} {'':22} {r['url']}")
    print()

print(f"  Showing {len(display)} results (top {DISPLAY_LIMIT} per keyword per platform, {TIME_RANGE})")


# ─── SAVE CSV (all results) ───────────────────────────
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
csv_path  = f"results/tracker_{timestamp}.csv"

with open(csv_path, "w", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=["platform", "keyword", "title", "url", "score", "fetched_at"]
    )
    writer.writeheader()
    writer.writerows(results)

print(f"\n{'─'*60}")
print(f"  {len(results)} total results saved → {csv_path}")
print(f"{'─'*60}\n")
