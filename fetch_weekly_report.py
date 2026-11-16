#!/usr/bin/env python3
"""
Courtside Kiki — Weekly Storylines Report
==========================================

Looks ahead at the upcoming week of D1 women's volleyball and builds a
Markdown report flagging the games worth writing about:

  - Top 25 vs. Top 25 matchups ("marquee games")
  - Known rivalry games (see data/rivalries.json — edit freely, this is a
    starting list, not a complete one)
  - Games featuring a current national stat leader or a freshman standout
    (pulled from ncaa.com's individual stat leaderboards)
  - (Best-effort, see note below) conference Player/Freshman of the Week
    honors, if a conference's site exposes something this script can parse

Meant to be the input for your recap + "kiki" articles each week — run it,
skim docs/reports/latest.md, then write from there.

Data source: the same free ncaa-api project used in courtside-kiki-stats
(https://github.com/henrygd/ncaa-api), plus (best-effort) each conference's
own news pages for weekly honors.

FIRST RUN / TUNING NOTE
------------------------
Like courtside-kiki-stats, this was written without live network access to
test against. The scoreboard and stat-leader parsing reuse field names
already confirmed working in that repo, so those parts should be solid out
of the box.

The conference-honors scraping (fetch_conference_honors, near the bottom)
is the genuinely untested part — conference athletic sites don't share a
common API, so this just fetches each conference's volleyball news page and
looks for headlines containing "player of the week" / "freshman of the
week". If a conference comes back empty, check data/raw/honors_<conf>.html
(the raw page is always saved) and send it back — it's usually a five
minute fix to the regex. This section is a nice-to-have layered on top of
the rest of the report, not a dependency for it; everything else works
without it.
"""

import json
import os
import re
import sys
import time
import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

NCAA_API_BASE = "https://ncaa-api.henrygd.me"
SPORT = "volleyball-women"
DIVISION = "d1"

# Same confirmed category IDs as courtside-kiki-stats. Add more once
# confirmed at https://www.ncaa.com/stats/volleyball-women/d1
STAT_CATEGORIES = {
    "Kills Per Set": 552,
    "Assists Per Set": 3,
    "Aces Per Set": 42,
}

LEADER_POOL_SIZE = 25  # how far into each leaderboard counts as "a name to watch"
REQUEST_DELAY_SECONDS = 0.3
TIMEOUT_SECONDS = 20

RIVALRIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rivalries.json")


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


def api_get(path):
    url = f"{NCAA_API_BASE}{path}"
    req = Request(url, headers={"User-Agent": "courtside-kiki-weekly/1.0"})
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
        return json.loads(raw)
    except HTTPError as e:
        log(f"HTTP {e.code} for {url}")
    except URLError as e:
        log(f"Network error for {url}: {e}")
    except json.JSONDecodeError:
        log(f"Non-JSON response for {url}")
    except Exception as e:
        log(f"Unexpected error for {url}: {e}")
    return None


def dump_raw(name, data, ext="json"):
    os.makedirs("data/raw", exist_ok=True)
    path = f"data/raw/{name}.{ext}"
    with open(path, "w") as f:
        if ext == "json":
            json.dump(data, f, indent=2, default=str)
        else:
            f.write(data)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def get_scoreboard(date):
    path = f"/scoreboard/{SPORT}/{DIVISION}/{date.year}/{date.month:02d}/{date.day:02d}"
    data = api_get(path)
    if data:
        dump_raw(f"scoreboard_{date.isoformat()}", data)
    return data


def extract_games(scoreboard_json):
    if not scoreboard_json:
        return []
    games_raw = scoreboard_json.get("games") or scoreboard_json.get("data") or []
    games = []
    for g in games_raw:
        game = g.get("game", g) if isinstance(g, dict) else g
        games.append(game)
    return games


def build_week_games(start_date, days=7):
    all_games = []
    for i in range(days):
        date = start_date + datetime.timedelta(days=i)
        for g in extract_games(get_scoreboard(date)):
            g["_date"] = date.isoformat()
            all_games.append(g)
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_games


def team_label(team):
    names = (team or {}).get("names") or {}
    return names.get("short") or names.get("full") or "?"


def team_rank(team):
    try:
        return int((team or {}).get("rank"))
    except (TypeError, ValueError):
        return None


def _norm(name):
    """Loose team-name key for matching across endpoints: lowercase, periods
    and extra whitespace collapsed."""
    return re.sub(r"[.\s]+", " ", (name or "").strip().lower()).strip()


# ---------------------------------------------------------------------------
# Rivalries
# ---------------------------------------------------------------------------

def load_rivalries():
    try:
        with open(RIVALRIES_FILE) as f:
            pairs = json.load(f)
    except FileNotFoundError:
        log(f"No rivalries file at {RIVALRIES_FILE} — skipping rivalry flags.")
        return set()
    except json.JSONDecodeError as e:
        log(f"data/rivalries.json is not valid JSON: {e}")
        return set()
    return {frozenset(_norm(n) for n in pair) for pair in pairs}


def is_rivalry(rivalry_set, home, away):
    return frozenset({_norm(team_label(home)), _norm(team_label(away))}) in rivalry_set


# ---------------------------------------------------------------------------
# National stat leaders -> "players to watch" watchlist
# ---------------------------------------------------------------------------

def get_stat_leaders(category_id):
    time.sleep(REQUEST_DELAY_SECONDS)
    data = api_get(f"/stats/{SPORT}/{DIVISION}/current/individual/{category_id}")
    if data:
        dump_raw(f"leaders_{category_id}", data)
    return data


def _is_freshman(entry):
    """Defensive: the leaderboard JSON's class/year field name isn't
    confirmed, so check the common candidates."""
    for key in ("Cl", "Class", "Yr", "Year"):
        val = str(entry.get(key, "")).strip().upper()
        if val in ("FR", "FR.", "FRESHMAN", "1ST"):
            return True
    return False


def build_watchlist():
    """{normalized_team_name: [(player, stat_label, value, is_freshman), ...]}
    built from the top of each national leaderboard."""
    watch = {}
    for label, cat_id in STAT_CATEGORIES.items():
        data = get_stat_leaders(cat_id)
        if not data:
            continue
        entries = data.get("data") or data.get("stats") or []
        for e in entries[:LEADER_POOL_SIZE]:
            if not isinstance(e, dict):
                continue
            name = e.get("Name") or e.get("name") or "?"
            team = e.get("Team") or e.get("team") or ""
            val = e.get("Per Set") or e.get("value") or ""
            watch.setdefault(_norm(team), []).append((name, label, val, _is_freshman(e)))
    return watch


def watchlist_hits(watch, team):
    return watch.get(_norm(team_label(team)), [])


# ---------------------------------------------------------------------------
# Conference weekly honors (best-effort — see FIRST RUN NOTE at top of file)
# ---------------------------------------------------------------------------

CONFERENCE_NEWS_URLS = {
    "Big Ten": "https://bigten.org/sports/wvball/news",
    "SEC": "https://www.secsports.com/sport/wvolleyball",
    "ACC": "https://theacc.com/sports/wvball/news",
    "Pac-12": "https://pac-12.com/sport/womens-volleyball",
}

HONOR_KEYWORDS = (
    "player of the week", "freshman of the week", "setter of the week",
    "defensive player of the week", "offensive player of the week",
    "newcomer of the week",
)


def fetch_conference_honors():
    """{conference: [headline, ...]} for any headline that looks like a
    weekly-honors announcement. Skips a conference silently if its page
    can't be fetched or nothing matches — see FIRST RUN NOTE at top."""
    honors = {}
    for conf, url in CONFERENCE_NEWS_URLS.items():
        req = Request(url, headers={"User-Agent": "courtside-kiki-weekly/1.0"})
        try:
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            log(f"Could not fetch {conf} news page ({url}): {e}")
            continue
        dump_raw(f"honors_{_norm(conf).replace(' ', '_')}", html, ext="html")

        heads = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.IGNORECASE | re.DOTALL)
        found = []
        for h in heads:
            text = re.sub(r"<[^>]+>", "", h).strip()
            if text and any(k in text.lower() for k in HONOR_KEYWORDS):
                found.append(text)
        if found:
            honors[conf] = found
        time.sleep(REQUEST_DELAY_SECONDS)
    return honors


# ---------------------------------------------------------------------------
# Classify the week's games
# ---------------------------------------------------------------------------

def classify_games(games, rivalry_set, watch):
    marquee, rivalry, watch_games = [], [], []
    for g in games:
        home, away = g.get("home") or {}, g.get("away") or {}
        if team_rank(home) and team_rank(away):
            marquee.append(g)
        if is_rivalry(rivalry_set, home, away):
            rivalry.append(g)
        hits = watchlist_hits(watch, home) + watchlist_hits(watch, away)
        if hits:
            watch_games.append((g, hits))
    return marquee, rivalry, watch_games


# ---------------------------------------------------------------------------
# Render the Markdown report
# ---------------------------------------------------------------------------

def _matchup_line(g):
    home, away = g.get("home") or {}, g.get("away") or {}
    hr, ar = team_rank(home), team_rank(away)
    h = f"#{hr} {team_label(home)}" if hr else team_label(home)
    a = f"#{ar} {team_label(away)}" if ar else team_label(away)
    return f"- **{a} @ {h}** — {g.get('_date', '')}"


def render_report(start_date, end_date, marquee, rivalry, watch_games, honors):
    lines = [f"# Courtside Kiki — Week of {start_date.isoformat()} to {end_date.isoformat()}", ""]

    lines.append("## 🔥 Marquee Matchups (Top 25 vs. Top 25)")
    lines.append("")
    lines += [_matchup_line(g) for g in marquee] if marquee else ["_None this week._"]
    lines.append("")

    lines.append("## ⚔️ Rivalry Games")
    lines.append("")
    if rivalry:
        lines += [_matchup_line(g) for g in rivalry]
    else:
        lines.append("_None flagged this week — check data/rivalries.json if that's unexpected._")
    lines.append("")

    lines.append("## 👀 Players & Freshmen to Watch")
    lines.append("")
    if watch_games:
        for g, hits in watch_games:
            lines.append(_matchup_line(g))
            seen = set()
            for name, stat_label, val, fr in hits:
                key = (name, stat_label)
                if key in seen:
                    continue
                seen.add(key)
                tag = " (FR)" if fr else ""
                lines.append(f"    - {name}{tag} — {stat_label}: {val}")
    else:
        lines.append("_No current national leaders on this week's rosters._")
    lines.append("")

    lines.append("## 🏅 Conference Honors (for last week's play)")
    lines.append("")
    if honors:
        for conf, heads in honors.items():
            lines.append(f"**{conf}**")
            lines += [f"- {h}" for h in heads]
            lines.append("")
    else:
        lines.append(
            "_Nothing picked up yet — honors usually post Monday evening through Tuesday, and "
            "this report refreshes automatically then. If it's still empty after Wednesday, "
            "see the FIRST RUN NOTE in fetch_weekly_report.py to tune the scraper._"
        )
    lines.append("")

    lines.append(f"_Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M UTC')}_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------

def parse_start_date(argv):
    """No arg: Monday of the current week. One arg: that date as the start."""
    if argv:
        return datetime.date.fromisoformat(argv[0])
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


if __name__ == "__main__":
    start = parse_start_date([a for a in sys.argv[1:] if a])
    end = start + datetime.timedelta(days=6)

    rivalry_set = load_rivalries()
    watch = build_watchlist()
    games = build_week_games(start)
    marquee, rivalry, watch_games = classify_games(games, rivalry_set, watch)
    honors = fetch_conference_honors()

    report = render_report(start, end, marquee, rivalry, watch_games, honors)

    os.makedirs("docs/reports", exist_ok=True)
    out_path = f"docs/reports/week-{start.isoformat()}.md"
    with open(out_path, "w") as f:
        f.write(report)
    with open("docs/reports/latest.md", "w") as f:
        f.write(report)

    log(
        f"Wrote {out_path} — {len(games)} games, {len(marquee)} marquee, "
        f"{len(rivalry)} rivalry, {len(watch_games)} watch-list games"
    )
