# Courtside Kiki — Weekly Storylines Report

Looks ahead at the upcoming week of D1 women's volleyball and builds a
Markdown report (`docs/reports/latest.md`) flagging what's worth writing
about:

- 🔥 **Marquee matchups** — Top 25 vs. Top 25 games
- ⚔️ **Rivalry games** — matched against `data/rivalries.json`, a starter
  list you should edit and expand
- 👀 **Players & freshmen to watch** — any upcoming game featuring a player
  currently on a national stat leaderboard (kills, assists, aces per set),
  with freshmen tagged separately
- 🏅 **Conference weekly honors** (Player/Freshman of the Week) — best
  effort; see the note below

This is meant to feed your twice-weekly recap articles and weekly "kiki"
piece — run it, read `docs/reports/latest.md`, write from there.

## Setup

1. Create a new GitHub repo and push these files.
2. Enable GitHub Actions if prompted (Settings → Actions → General → Allow
   all actions).
3. That's it. The workflow runs Monday morning for the matchups preview,
   then again Monday evening, Tuesday (twice) and Wednesday to catch the
   conference weekly honors as they post. Each run rebuilds the same
   week's report in `docs/reports/`, so it fills in as the week goes. You
   can also trigger it manually anytime from the Actions tab ("Run
   workflow"). Edit the cron times in `.github/workflows/weekly.yml` to
   match when your conferences actually post.

## Running locally

```bash
python fetch_weekly_report.py            # this week (Monday–Sunday)
python fetch_weekly_report.py 2026-10-06 # a specific week's Monday
```

Output goes to `docs/reports/week-<date>.md` and `docs/reports/latest.md`.
Raw API responses get saved to `data/raw/` for debugging.

## Editing the rivalry list

`data/rivalries.json` is a flat list of `["Team A", "Team B"]` pairs,
matched against ncaa.com's short team names. It's a starting point covering
well-known rivalries — realignment has scrambled some conference
affiliations recently, so add/remove pairs as you see fit. If a rivalry
isn't being flagged, check a saved `data/raw/scoreboard_*.json` for the
exact team name ncaa.com is using and match it in the list.

## About the conference honors section

This part (`fetch_conference_honors` in the script) tries to scrape each
conference's volleyball news page for "Player of the Week" / "Freshman of
the Week" headlines. It was written without live network access to test
against, so treat it as best-effort — if a conference always comes back
empty, open the matching `data/raw/honors_<conference>.html` file after a
run to see the actual page, and the regex in the script can be adjusted to
match. It's a bonus layered on top of the rest of the report, not something
the rest of the script depends on.

## Companion repo

This pairs with
[`courtside-kiki-stats`](https://github.com/courtsidekiki/courtside-kiki-stats),
the daily stats dashboard — that one recaps what already happened, this one
looks ahead at what's coming up.
