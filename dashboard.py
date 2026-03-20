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
import streamlit.components.v1 as components
from io import BytesIO
from textblob import TextBlob
from wordcloud import WordCloud, STOPWORDS
import pandas as pd

# ─── PAGE CONFIG ─────────────────────────────────────────
st.set_page_config(
    page_title="CROWE COMMAND",
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
                params={"q": f'"{kw}"', "sort": "top", "t": reddit_t, "limit": 20})
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
components.html("""
<!DOCTYPE html>
<html>
<head>
<style>
  body { margin:0; background:#050505; overflow:hidden; }
  canvas { display:block; }
</style>
</head>
<body>
<canvas id="c"></canvas>
<script>
const W = window.innerWidth || 900;
const H = 200;
const c = document.getElementById('c');
c.width = W; c.height = H;
const ctx = c.getContext('2d');

// ── STARS ─────────────────────────────────────────────
const stars = Array.from({length:80}, () => ({
  x: Math.random()*W, y: Math.random()*H,
  s: Math.random()*0.8+0.2, spd: Math.random()*0.4+0.1
}));

// ── ENEMY SPRITES (pixel arrays, 1=body, 2=wing, 3=eye) ──
const BEE = [
  [0,0,1,0,0,0,1,0,0],
  [0,1,1,1,1,1,1,1,0],
  [2,1,3,1,1,1,3,1,2],
  [2,1,1,1,1,1,1,1,2],
  [0,2,1,0,0,0,1,2,0],
  [0,0,2,0,0,0,2,0,0],
];
const BUTTERFLY = [
  [0,2,0,1,1,0,2,0],
  [2,2,1,1,1,1,2,2],
  [2,1,3,1,1,3,1,2],
  [0,1,1,1,1,1,1,0],
  [0,0,1,0,0,1,0,0],
];
const BOSS = [
  [0,0,1,1,1,1,0,0],
  [0,1,1,1,1,1,1,0],
  [1,1,3,1,1,3,1,1],
  [1,1,1,1,1,1,1,1],
  [0,1,1,0,0,1,1,0],
  [0,1,0,0,0,0,1,0],
];

const PALETTES = [
  {1:'#ff4466', 2:'#ff88aa', 3:'#ffffff'}, // red
  {1:'#4488ff', 2:'#88bbff', 3:'#ffffff'}, // blue
  {1:'#ffcc00', 2:'#ffee88', 3:'#ffffff'}, // gold (boss)
];

function drawSprite(sprite, palette, cx, cy, scale=2) {
  sprite.forEach((row, ry) => {
    row.forEach((px, rx) => {
      if (!px) return;
      ctx.fillStyle = palette[px];
      ctx.fillRect(
        cx + (rx - row.length/2) * scale,
        cy + (ry - sprite.length/2) * scale,
        scale, scale
      );
    });
  });
}

// ── FORMATION ─────────────────────────────────────────
const COLS = 10, GAP_X = 60, GAP_Y = 28;
const START_X = W/2 - (COLS-1)*GAP_X/2;
const enemies = [];
for (let r = 0; r < 3; r++) {
  for (let c = 0; c < COLS; c++) {
    enemies.push({
      col: c, row: r,
      bx: START_X + c*GAP_X,
      by: 28 + r*GAP_Y,
      alive: true,
      sprite: r===0 ? BOSS : r===1 ? BUTTERFLY : BEE,
      palette: PALETTES[r===0 ? 2 : r===1 ? 1 : 0],
      wingOpen: Math.random()>0.5,
      wingTimer: Math.floor(Math.random()*30),
    });
  }
}

let formX = 0, formDir = 1, formSpd = 0.4;

// ── PLAYER ────────────────────────────────────────────
const player = { x: W/2, y: H-28, dir: 1, spd: 0.5 };

// ── BULLETS ───────────────────────────────────────────
const bullets = [];
let bTimer = 0;

// ── EXPLOSIONS ────────────────────────────────────────
const explosions = [];

function explode(x, y) {
  for (let i=0; i<8; i++) {
    const a = (i/8)*Math.PI*2;
    explosions.push({x, y, vx:Math.cos(a)*2, vy:Math.sin(a)*2, life:18, color:'#ff8800'});
  }
}

// ── DIVE ──────────────────────────────────────────────
let diveEnemy = null, diveTimer = 120;

// ── MAIN LOOP ─────────────────────────────────────────
let frame = 0;

function draw() {
  frame++;
  ctx.fillStyle = '#050505';
  ctx.fillRect(0,0,W,H);

  // Stars
  stars.forEach(s => {
    s.y += s.spd;
    if (s.y > H) { s.y=0; s.x=Math.random()*W; }
    ctx.fillStyle = `rgba(255,255,255,${0.4+Math.random()*0.3})`;
    ctx.fillRect(s.x, s.y, s.s, s.s);
  });

  // Formation sway
  formX += formSpd * formDir;
  if (Math.abs(formX) > 55) formDir *= -1;

  // Wing flap
  enemies.forEach(e => {
    if (!e.alive) return;
    e.wingTimer++;
    if (e.wingTimer > 22) { e.wingOpen = !e.wingOpen; e.wingTimer=0; }
  });

  // Draw enemies
  enemies.forEach(e => {
    if (!e.alive) return;
    const ex = e.bx + formX;
    const ey = e.by;
    drawSprite(e.sprite, e.palette, ex, ey, 2);
  });

  // Dive enemy
  diveTimer--;
  if (diveTimer <= 0 && !diveEnemy) {
    const alive = enemies.filter(e=>e.alive);
    if (alive.length > 0) {
      const pick = alive[Math.floor(Math.random()*alive.length)];
      diveEnemy = {
        x: pick.bx + formX, y: pick.by,
        tx: player.x, ty: player.y,
        sprite: pick.sprite, palette: pick.palette,
        t: 0,
      };
      pick.alive = false;
      diveTimer = 180 + Math.random()*120;
    }
  }
  if (diveEnemy) {
    diveEnemy.t += 0.018;
    // arc dive path
    const t = diveEnemy.t;
    const cx1 = diveEnemy.x + 80, cy1 = diveEnemy.y + 80;
    const cx2 = diveEnemy.tx - 80, cy2 = diveEnemy.ty - 80;
    const bx = Math.pow(1-t,3)*diveEnemy.x + 3*Math.pow(1-t,2)*t*cx1 + 3*(1-t)*t*t*cx2 + t*t*t*diveEnemy.tx;
    const by = Math.pow(1-t,3)*diveEnemy.y + 3*Math.pow(1-t,2)*t*cy1 + 3*(1-t)*t*t*cy2 + t*t*t*diveEnemy.ty;
    drawSprite(diveEnemy.sprite, diveEnemy.palette, bx, by, 2);
    if (diveEnemy.t >= 1) {
      explode(bx, by);
      // put it back in formation
      const slot = enemies.find(e=>!e.alive);
      if (slot) slot.alive = true;
      diveEnemy = null;
    }
  }

  // Player drift
  player.x += player.spd * player.dir;
  if (player.x > W-60 || player.x < 60) player.dir *= -1;

  // Draw player ship
  const px = player.x, py = player.y;
  ctx.fillStyle = '#00ff41';
  ctx.shadowBlur = 6; ctx.shadowColor = '#00ff41';
  // body
  ctx.fillRect(px-2, py-10, 4, 16);
  ctx.fillRect(px-8, py-2, 16, 6);
  ctx.fillRect(px-11, py+2, 5, 5);
  ctx.fillRect(px+6,  py+2, 5, 5);
  // cockpit
  ctx.fillStyle = '#88ffff';
  ctx.fillRect(px-2, py-8, 4, 5);
  // engine
  ctx.fillStyle = frame%4<2 ? '#ff8800' : '#ffcc00';
  ctx.fillRect(px-2, py+6, 4, 4);
  ctx.shadowBlur = 0;

  // Shoot
  bTimer++;
  if (bTimer > 40) {
    bullets.push({x:px, y:py-12, spd:-6, enemy:false});
    const alive = enemies.filter(e=>e.alive);
    if (alive.length) {
      const s = alive[Math.floor(Math.random()*alive.length)];
      bullets.push({x:s.bx+formX, y:s.by+10, spd:3.5, enemy:true});
    }
    bTimer = 0;
  }

  // Bullets
  for (let i=bullets.length-1; i>=0; i--) {
    const b = bullets[i];
    b.y += b.spd;
    if (b.y<-5 || b.y>H+5) { bullets.splice(i,1); continue; }
    ctx.fillStyle = b.enemy ? '#ff4444' : '#ffff44';
    ctx.shadowBlur = 5; ctx.shadowColor = ctx.fillStyle;
    ctx.fillRect(b.x-1, b.y-5, 2, 10);
    ctx.shadowBlur = 0;
    // hit enemy?
    if (!b.enemy) {
      enemies.forEach(e => {
        if (!e.alive) return;
        if (Math.abs(b.x-(e.bx+formX))<10 && Math.abs(b.y-e.by)<10) {
          e.alive = false;
          explode(e.bx+formX, e.by);
          bullets.splice(i,1);
          setTimeout(()=>{ e.alive=true; }, 3000);
        }
      });
    }
  }

  // Explosions
  for (let i=explosions.length-1; i>=0; i--) {
    const e = explosions[i];
    e.x+=e.vx; e.y+=e.vy; e.life--;
    if (e.life<=0) { explosions.splice(i,1); continue; }
    ctx.globalAlpha = e.life/18;
    ctx.fillStyle = e.life>9 ? '#ffcc00' : '#ff4400';
    ctx.fillRect(e.x-2, e.y-2, 4, 4);
    ctx.globalAlpha = 1;
  }

  // Title overlay
  ctx.font = 'bold 20px "Share Tech Mono", "Courier New", monospace';
  ctx.fillStyle = '#00ff41';
  ctx.shadowBlur = 12; ctx.shadowColor = '#00ff41';
  ctx.textAlign = 'center';
  ctx.fillText('CROWE COMMAND', W/2, H-38);
  ctx.shadowBlur = 0;
  ctx.font = '10px "Share Tech Mono", "Courier New", monospace';
  ctx.fillStyle = '#00dd44';
  ctx.fillText('▸ MONITORING: FIREWORKS AI  ·  KIMI K2  ·  LLM LANDSCAPE  ·  6 PLATFORMS', W/2, H-20);

  requestAnimationFrame(draw);
}
draw();
</script>
</body>
</html>
""", height=205)

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
    top = df[df["score"] > 0].sort_values("score", ascending=False).head(8)

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

    # Latest news from Google News (no score, sorted by recency)
    st.markdown("#### LATEST NEWS")
    news = df[df["platform"] == "Google News"].sort_values("fetched_at", ascending=False).head(8)
    if news.empty:
        st.markdown("<small style='color:#006620;'>No recent news articles found.</small>", unsafe_allow_html=True)
    for _, row in news.iterrows():
        s_color = {"POSITIVE": "#00ff41", "NEGATIVE": "#ff3333", "NEUTRAL": "#ffaa00"}[row["sentiment"]]
        st.markdown(f"""
<div style="background:#090f09; border:1px solid rgba(0,255,65,0.12);
     border-left:3px solid {s_color}; padding:10px 16px; margin-bottom:8px; border-radius:2px;">
  <span style="color:{s_color}; font-size:0.68rem;">◆ {row['sentiment']}</span>
  <span style="color:rgba(0,255,65,0.38); font-size:0.68rem; float:right;">
    Google News &nbsp;·&nbsp; {row['fetched_at']}
  </span>
  <br/>
  <a href="{row['url']}" target="_blank"
     style="color:#00cc33; font-size:0.88rem; text-decoration:none;">
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
    f"CROWE COMMAND v1.0 &nbsp;·&nbsp; {len(df):,} SIGNALS &nbsp;·&nbsp; "
    f"6 PLATFORMS &nbsp;·&nbsp; CACHE 30 MIN &nbsp;·&nbsp; "
    f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    f"</p>",
    unsafe_allow_html=True,
)
