#!/usr/bin/env python3
"""
DEV PASS TRACKER — Retro Streamlit Dashboard
"""

import datetime
import random
import time
import urllib.parse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import feedparser
import plotly.graph_objects as go
import requests
import streamlit as st
from io import BytesIO
from textblob import TextBlob
from wordcloud import WordCloud, STOPWORDS
import pandas as pd

# ─── PAGE CONFIG ─────────────────────────────────────────
st.set_page_config(
    page_title="CROWE COMMAND CENTER",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── RETRO CSS ───────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

html, body, .stApp {
    background-color: #050505 !important;
    font-family: 'Share Tech Mono', 'Courier New', monospace !important;
}

/* CRT scanlines */
.stApp::after {
    content: "";
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0,0,0,0.07) 2px,
        rgba(0,0,0,0.07) 4px
    );
    pointer-events: none;
    z-index: 9999;
}

h1, h2, h3, h4, h5 {
    color: #00ff41 !important;
    font-family: 'Share Tech Mono', monospace !important;
    text-shadow: 0 0 12px rgba(0,255,65,0.55);
    letter-spacing: 2px;
}

p, div, span, li, label {
    font-family: 'Share Tech Mono', monospace !important;
    color: #00aa2a;
}

a { color: #00ff41 !important; }

/* Metrics */
div[data-testid="metric-container"] {
    background: #090f09;
    border: 1px solid rgba(0,255,65,0.25);
    border-radius: 2px;
    padding: 16px !important;
    box-shadow: 0 0 18px rgba(0,255,65,0.06), inset 0 0 40px rgba(0,0,0,0.6);
}
div[data-testid="stMetricValue"] {
    color: #00ff41 !important;
    text-shadow: 0 0 10px rgba(0,255,65,0.8);
    font-size: 2rem !important;
    font-family: 'Share Tech Mono', monospace !important;
}
div[data-testid="stMetricLabel"] {
    color: #00661a !important;
    font-family: 'Share Tech Mono', monospace !important;
    letter-spacing: 1px;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #020902 !important;
    border-right: 1px solid rgba(0,255,65,0.15);
}
section[data-testid="stSidebar"] * {
    color: #00cc33 !important;
    font-family: 'Share Tech Mono', monospace !important;
}

/* Radio buttons */
div[role="radiogroup"] label { color: #00cc33 !important; }

/* Multiselect */
div[data-baseweb="select"] > div {
    background-color: #090f09 !important;
    border-color: rgba(0,255,65,0.35) !important;
}

/* Buttons */
.stButton > button {
    background: transparent !important;
    border: 1px solid #00ff41 !important;
    color: #00ff41 !important;
    font-family: 'Share Tech Mono', monospace !important;
    letter-spacing: 1px;
    width: 100%;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: rgba(0,255,65,0.1) !important;
    box-shadow: 0 0 14px rgba(0,255,65,0.35) !important;
}

/* Text input */
input {
    background: #090f09 !important;
    color: #00ff41 !important;
    border-color: rgba(0,255,65,0.3) !important;
    font-family: 'Share Tech Mono', monospace !important;
}

/* Dataframe */
div[data-testid="stDataFrame"] {
    border: 1px solid rgba(0,255,65,0.2);
}

/* Horizontal rule */
hr { border-color: rgba(0,255,65,0.15) !important; }

/* Spinner */
div[data-testid="stSpinner"] p { color: #00ff41 !important; }

/* Tabs */
div[data-baseweb="tab"] { background: transparent !important; }
button[data-baseweb="tab"] {
    color: #00aa2a !important;
    font-family: 'Share Tech Mono', monospace !important;
    background: transparent !important;
    border-bottom: 2px solid transparent;
}
button[aria-selected="true"][data-baseweb="tab"] {
    color: #00ff41 !important;
    border-bottom: 2px solid #00ff41 !important;
}
</style>
""", unsafe_allow_html=True)


# ─── KEYWORDS ────────────────────────────────────────────
KEYWORDS = [
    "Fireworks AI", "fireworks.ai", "FireAttention", "Fireworks inference",
    "Kimi k2.5 turbo", "Kimi k2", "Moonshot AI", "kimi.ai",
    "open source LLM inference", "LLM API pricing", "fast inference", "MoE model",
]

ALL_PLATFORMS = ["Hacker News", "Reddit", "Google News", "Stack Overflow", "Lobsters", "dev.to"]

PLOTLY_BASE = dict(
    paper_bgcolor="#050505",
    plot_bgcolor="#050505",
    font=dict(family="Share Tech Mono, monospace", color="#00aa2a"),
    margin=dict(l=20, r=20, t=40, b=20),
    title_font=dict(color="#00ff41", size=13),
)


# ─── HELPERS ─────────────────────────────────────────────
def is_relevant(title, keyword):
    t = title.lower()
    if " " not in keyword:
        return keyword.lower() in t
    if keyword.lower() in t:
        return True
    return max(keyword.split(), key=len).lower() in t

def get_sentiment(text):
    p = TextBlob(text).sentiment.polarity
    if p > 0.1:   return "POSITIVE", "#00ff41"
    if p < -0.1:  return "NEGATIVE", "#ff3333"
    return "NEUTRAL", "#ffaa00"

def green_color(*args, **kwargs):
    return f"hsl(130, 100%, {random.randint(40, 75)}%)"


# ─── DATA FETCHING (cached 30 min) ───────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all(time_range):
    reddit_t    = {"24h": "day", "week": "week", "month": "month"}[time_range]
    hn_cutoff   = int(time.time() - {"24h": 86400, "week": 604800, "month": 2592000}[time_range])
    date_cutoff = datetime.datetime.now() - {
        "24h": datetime.timedelta(days=1),
        "week": datetime.timedelta(weeks=1),
        "month": datetime.timedelta(days=30),
    }[time_range]

    rows = []

    def add(platform, title, url, score, keyword):
        if not title or not is_relevant(title, keyword):
            return
        sentiment, _ = get_sentiment(title)
        rows.append({
            "platform":  platform,
            "keyword":   keyword,
            "title":     title[:150],
            "url":       url,
            "score":     int(score),
            "sentiment": sentiment,
            "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    for kw in KEYWORDS:
        # Hacker News
        try:
            r = requests.get("https://hn.algolia.com/api/v1/search", timeout=10, params={
                "query": kw, "tags": "story", "hitsPerPage": 20,
                "numericFilters": f"created_at_i>{hn_cutoff}",
            })
            for h in r.json().get("hits", []):
                add("Hacker News", h.get("title", ""),
                    h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                    h.get("points", 0), kw)
        except: pass

        # Reddit
        try:
            r = requests.get("https://www.reddit.com/search.json", timeout=10,
                headers={"User-Agent": "dev-pass-tracker/1.0"},
                params={"q": kw, "sort": "top", "t": reddit_t, "limit": 20})
            for post in r.json()["data"]["children"]:
                d = post["data"]
                add("Reddit", d["title"], f"https://reddit.com{d['permalink']}", d["score"], kw)
        except: pass

        # Google News
        try:
            q    = urllib.parse.quote(f'"{kw}"')
            feed = feedparser.parse(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
            for e in feed.entries[:20]:
                if hasattr(e, "published_parsed") and e.published_parsed:
                    if datetime.datetime(*e.published_parsed[:6]) < date_cutoff:
                        continue
                add("Google News", e.get("title", ""), e.get("link", ""), 0, kw)
        except: pass

        # Stack Overflow
        try:
            r = requests.get("https://api.stackexchange.com/2.3/search", timeout=10, params={
                "order": "desc", "sort": "relevance", "intitle": kw,
                "site": "stackoverflow", "pagesize": 20, "fromdate": hn_cutoff,
            })
            for item in r.json().get("items", []):
                add("Stack Overflow", item.get("title", ""), item.get("link", ""), item.get("score", 0), kw)
        except: pass

    # Lobsters (tag feeds — cached once per run)
    try:
        for tag in ["llm", "ai", "programming"]:
            r = requests.get(f"https://lobste.rs/t/{tag}.json", timeout=10)
            for s in (r.json() if isinstance(r.json(), list) else []):
                c = s.get("created_at", "")[:10]
                if c and datetime.datetime.strptime(c, "%Y-%m-%d") < date_cutoff:
                    continue
                for kw in KEYWORDS:
                    add("Lobsters", s.get("title", ""),
                        s.get("url") or f"https://lobste.rs{s.get('comments_url','')}",
                        s.get("score", 0), kw)
    except: pass

    # dev.to (tag feeds — cached once per run)
    try:
        for tag in ["llm", "ai", "machinelearning"]:
            r = requests.get("https://dev.to/api/articles", timeout=10,
                headers={"User-Agent": "dev-pass-tracker/1.0"},
                params={"tag": tag, "per_page": 30, "state": "rising"})
            for item in (r.json() if isinstance(r.json(), list) else []):
                pub = item.get("published_at", "")[:10]
                if pub and datetime.datetime.strptime(pub, "%Y-%m-%d") < date_cutoff:
                    continue
                for kw in KEYWORDS:
                    add("dev.to", item.get("title", ""), item.get("url", ""),
                        item.get("positive_reactions_count", 0), kw)
    except: pass

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["platform","keyword","title","url","score","sentiment","fetched_at"]
    )


@st.cache_data(ttl=1800, show_spinner=False)
def make_wordcloud(titles_tuple):
    text = " ".join(titles_tuple)
    stopwords = set(STOPWORDS) | {
        "AI", "LLM", "model", "using", "new", "just", "use", "one", "get",
        "like", "can", "will", "says", "via", "s", "vs", "us", "also", "now",
    }
    wc = WordCloud(
        width=1100, height=320, background_color="#050505",
        color_func=green_color, stopwords=stopwords,
        max_words=80, prefer_horizontal=0.8,
    ).generate(text)
    fig, ax = plt.subplots(figsize=(14, 4), facecolor="#050505")
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    plt.tight_layout(pad=0)
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="#050505", dpi=130)
    plt.close()
    buf.seek(0)
    return buf


# ─── SIDEBAR ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ◈ CONTROLS")
    st.markdown("---")
    time_range = st.radio("TIME RANGE", ["24h", "week", "month"], index=1)
    st.markdown("---")
    st.markdown("### ◈ PLATFORMS")
    selected_platforms = st.multiselect("ACTIVE FEEDS", ALL_PLATFORMS, default=ALL_PLATFORMS)
    st.markdown("---")
    st.markdown("### ◈ KEYWORDS")
    selected_keywords = st.multiselect("TRACKING", KEYWORDS, default=KEYWORDS)
    st.markdown("---")
    if st.button("⟳  REFRESH DATA"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.markdown(
        f"<small style='color:rgba(0,255,65,0.35);'>"
        f"LAST SCAN<br/>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"<br/>CACHE: 30 MIN</small>",
        unsafe_allow_html=True,
    )


# ─── HEADER ──────────────────────────────────────────────
st.markdown("""
<pre style="color:#00ff41; font-size:0.62rem; line-height:1.3; text-shadow:0 0 8px rgba(0,255,65,0.45); margin-bottom:0;">
 ██████╗██████╗  ██████╗ ██╗    ██╗███████╗
██╔════╝██╔══██╗██╔═══██╗██║    ██║██╔════╝
██║     ██████╔╝██║   ██║██║ █╗ ██║█████╗
██║     ██╔══██╗██║   ██║██║███╗██║██╔══╝
╚██████╗██║  ██║╚██████╔╝╚███╔███╔╝███████╗
 ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚══╝╚══╝╚══════╝

 ██████╗ ██████╗ ███╗   ███╗███╗   ███╗ █████╗ ███╗   ██╗██████╗
██╔════╝██╔═══██╗████╗ ████║████╗ ████║██╔══██╗████╗  ██║██╔══██╗
██║     ██║   ██║██╔████╔██║██╔████╔██║███████║██╔██╗ ██║██║  ██║
██║     ██║   ██║██║╚██╔╝██║██║╚██╔╝██║██╔══██║██║╚██╗██║██║  ██║
╚██████╗╚██████╔╝██║ ╚═╝ ██║██║ ╚═╝ ██║██║  ██║██║ ╚████║██████╔╝
 ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝

 ██████╗███████╗███╗   ██╗████████╗███████╗██████╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██╔════╝██╔══██╗
██║     █████╗  ██╔██╗ ██║   ██║   █████╗  ██████╔╝
██║     ██╔══╝  ██║╚██╗██║   ██║   ██╔══╝  ██╔══██╗
╚██████╗███████╗██║ ╚████║   ██║   ███████╗██║  ██║
 ╚═════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
</pre>
<p style="color:#00661a; font-size:0.78rem; letter-spacing:3px; margin-top:4px;">
▸ v1.0 &nbsp;·&nbsp; MONITORING: FIREWORKS AI · KIMI K2 · LLM LANDSCAPE &nbsp;·&nbsp; 6 PLATFORMS
</p>
""", unsafe_allow_html=True)

st.markdown("---")


# ─── FETCH ───────────────────────────────────────────────
with st.spinner("◈  SCANNING NETWORKS..."):
    df = fetch_all(time_range)

if df.empty:
    st.error("◈  NO SIGNAL DETECTED. CHECK YOUR CONNECTION AND REFRESH.")
    st.stop()

# Apply filters
df = df[df["platform"].isin(selected_platforms) & df["keyword"].isin(selected_keywords)]

if df.empty:
    st.warning("No results match your current filters.")
    st.stop()


# ─── METRICS ─────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
top_kw     = df.groupby("keyword").size().idxmax()
pos_count  = len(df[df["sentiment"] == "POSITIVE"])
neg_count  = len(df[df["sentiment"] == "NEGATIVE"])
top_plat   = df.groupby("platform").size().idxmax()

c1.metric("TOTAL SIGNALS",   f"{len(df):,}")
c2.metric("PLATFORMS",       df["platform"].nunique())
c3.metric("TOP KEYWORD",     top_kw.split()[0])
c4.metric("POSITIVE",        f"{pos_count:,}")
c5.metric("NEGATIVE",        f"{neg_count:,}")

st.markdown("---")


# ─── TABS ────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "◈  TOP SIGNALS", "◈  CHARTS", "◈  WORD CLOUD", "◈  ALL DATA"
])


# ── TAB 1: HIGHLIGHTS ────────────────────────────────────
with tab1:
    st.markdown("#### TOP POSTS BY ENGAGEMENT SCORE")
    top = df[df["score"] > 0].sort_values("score", ascending=False).head(10)
    if top.empty:
        top = df.head(10)

    for _, row in top.iterrows():
        s_color = {"POSITIVE": "#00ff41", "NEGATIVE": "#ff3333", "NEUTRAL": "#ffaa00"}[row["sentiment"]]
        st.markdown(f"""
<div style="background:#090f09; border:1px solid rgba(0,255,65,0.18);
     border-left:3px solid {s_color}; padding:12px 16px; margin-bottom:10px; border-radius:2px;">
  <span style="color:{s_color}; font-size:0.68rem; letter-spacing:1px;">◆ {row['sentiment']}</span>
  <span style="color:rgba(0,255,65,0.38); font-size:0.68rem; float:right;">
    {row['platform']} &nbsp;·&nbsp; ▲ {row['score']} &nbsp;·&nbsp; {row['fetched_at']}
  </span>
  <br/>
  <a href="{row['url']}" target="_blank"
     style="color:#00ff41; font-size:0.92rem; font-weight:bold; text-decoration:none;
            text-shadow:0 0 6px rgba(0,255,65,0.3);">
    {row['title']}
  </a>
  <br/>
  <span style="color:rgba(0,255,65,0.32); font-size:0.7rem;">⌗ {row['keyword']}</span>
</div>""", unsafe_allow_html=True)


# ── TAB 2: CHARTS ────────────────────────────────────────
with tab2:
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### MENTIONS BY KEYWORD")
        kw_df = df.groupby("keyword").size().reset_index(name="count").sort_values("count")
        kw_df["kw_short"] = kw_df["keyword"].str[:22]
        fig1 = go.Figure(go.Bar(
            x=kw_df["count"], y=kw_df["kw_short"], orientation="h",
            marker=dict(color="#00ff41", opacity=0.75, line=dict(color="rgba(0,255,65,0.25)", width=1)),
            text=kw_df["count"], textposition="outside", textfont=dict(color="#00ff41"),
        ))
        fig1.update_layout(**PLOTLY_BASE, title="KEYWORD FREQUENCY",
            xaxis=dict(showgrid=True, gridcolor="rgba(0,255,65,0.07)", color="#00661a", title=""),
            yaxis=dict(showgrid=False, color="#00661a", title=""))
        st.plotly_chart(fig1, use_container_width=True)

    with col_b:
        st.markdown("#### SENTIMENT BY PLATFORM")
        sent_df = df.groupby(["platform", "sentiment"]).size().reset_index(name="count")
        fig2 = go.Figure()
        for sentiment, color in [("POSITIVE","#00ff41"),("NEUTRAL","#ffaa00"),("NEGATIVE","#ff3333")]:
            sub = sent_df[sent_df["sentiment"] == sentiment]
            fig2.add_trace(go.Bar(name=sentiment, x=sub["platform"], y=sub["count"],
                marker_color=color, marker_opacity=0.75))
        fig2.update_layout(**PLOTLY_BASE, title="SENTIMENT DISTRIBUTION", barmode="stack",
            xaxis=dict(showgrid=False, color="#00661a", title=""),
            yaxis=dict(showgrid=True, gridcolor="rgba(0,255,65,0.07)", color="#00661a", title=""),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#00aa2a")))
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")

    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("#### PLATFORM SHARE")
        plat_df = df.groupby("platform").size().reset_index(name="count")
        fig3 = go.Figure(go.Pie(
            labels=plat_df["platform"], values=plat_df["count"],
            marker=dict(colors=["#00ff41","#00cc33","#009922","#006611","#ffaa00","#ff6b35"]),
            textfont=dict(family="Share Tech Mono", color="#050505"),
            hole=0.4,
        ))
        fig3.update_layout(**PLOTLY_BASE, title="SIGNAL SOURCES",
            legend=dict(font=dict(color="#00aa2a", family="Share Tech Mono")))
        st.plotly_chart(fig3, use_container_width=True)

    with col_d:
        st.markdown("#### TOP KEYWORD GROUPS")
        kw_group = {
            "Fireworks AI": ["Fireworks AI","fireworks.ai","FireAttention","Fireworks inference"],
            "Kimi / Moonshot": ["Kimi k2.5 turbo","Kimi k2","Moonshot AI","kimi.ai"],
            "LLM Landscape": ["open source LLM inference","LLM API pricing","fast inference","MoE model"],
        }
        group_counts = {g: df[df["keyword"].isin(kws)].shape[0] for g, kws in kw_group.items()}
        fig4 = go.Figure(go.Bar(
            x=list(group_counts.keys()), y=list(group_counts.values()),
            marker=dict(color=["#00ff41","#ffaa00","#ff6b35"], opacity=0.75),
            text=list(group_counts.values()), textposition="outside",
            textfont=dict(color="#00aa2a"),
        ))
        fig4.update_layout(**PLOTLY_BASE, title="SIGNALS BY TOPIC GROUP",
            xaxis=dict(showgrid=False, color="#00661a", title=""),
            yaxis=dict(showgrid=True, gridcolor="rgba(0,255,65,0.07)", color="#00661a", title=""))
        st.plotly_chart(fig4, use_container_width=True)


# ── TAB 3: WORD CLOUD ────────────────────────────────────
with tab3:
    st.markdown("#### TRENDING TERMS ACROSS ALL SIGNALS")
    titles = tuple(df["title"].tolist())
    if len(titles) < 5:
        st.warning("Not enough data for word cloud. Try a wider time range.")
    else:
        try:
            buf = make_wordcloud(titles)
            st.image(buf, use_container_width=True)
        except Exception as e:
            st.error(f"Word cloud error: {e}")

    st.markdown("---")
    st.markdown("#### SENTIMENT BREAKDOWN")
    sent_counts = df["sentiment"].value_counts()
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("◆ POSITIVE", sent_counts.get("POSITIVE", 0))
    sc2.metric("◆ NEUTRAL",  sent_counts.get("NEUTRAL", 0))
    sc3.metric("◆ NEGATIVE", sent_counts.get("NEGATIVE", 0))


# ── TAB 4: ALL DATA ──────────────────────────────────────
with tab4:
    st.markdown("#### ALL SIGNALS")
    search = st.text_input("SEARCH TITLES", placeholder="filter by keyword...")

    display = df.sort_values("score", ascending=False).reset_index(drop=True)
    display.index += 1

    if search:
        display = display[display["title"].str.contains(search, case=False, na=False)]

    st.dataframe(
        display[["platform","keyword","sentiment","score","title","url","fetched_at"]],
        use_container_width=True,
        height=500,
        column_config={
            "url":      st.column_config.LinkColumn("URL"),
            "score":    st.column_config.NumberColumn("▲ SCORE"),
            "sentiment": st.column_config.TextColumn("SENTIMENT"),
        },
    )

    csv = display.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇  EXPORT CSV",
        data=csv,
        file_name=f"dev_pass_tracker_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ─── FOOTER ──────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f"<p style='color:rgba(0,255,65,0.2); font-size:0.7rem; text-align:center; letter-spacing:2px;'>"
    f"CROWE COMMAND CENTER v1.0 &nbsp;·&nbsp; {len(df):,} SIGNALS &nbsp;·&nbsp; "
    f"6 PLATFORMS &nbsp;·&nbsp; CACHE 30 MIN &nbsp;·&nbsp; "
    f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    f"</p>",
    unsafe_allow_html=True,
)
