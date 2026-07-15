#!/usr/bin/env python3
"""Alert a Discord channel when a new Kane's Strikeout offer opens.

kanesstrikeout.com is a frameset around rays.kanesfurniture.com, whose
#openEvents div is empty in the HTML and filled at runtime from the JSON
endpoint below. We poll that endpoint directly -- no browser, no scraping.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = (
    "https://rays.kanesfurniture.com/getOpenEvents/"
    "?empCd=KF_PROMO_RAYS_EXT&partner=RAYS&periodType=REG"
)
SITE_URL = "https://kanesstrikeout.com/"
STATE_PATH = Path(__file__).parent / "state.json"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
RAYS_NAVY = 0x092C5C
DISCORD_EMBED_LIMIT = 10

# Consecutive failures before we bother Discord. ~2 hours at a 15 min cadence.
FAILURE_ALERT_THRESHOLD = 8


def fetch_events():
    """Return open-promo rows as dicts keyed by column name."""
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": UA, "Referer": SITE_URL, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    # Key by metaData name rather than position. The site's own JS reads
    # rows[9] for the game date, which would break silently if the query
    # ever grows a column.
    names = [col["name"] for col in payload["metaData"]]
    return [dict(zip(names, row)) for row in payload["rows"]]


def load_state():
    if not STATE_PATH.exists():
        return {"seen_event_ids": [], "consecutive_failures": 0}
    with STATE_PATH.open() as fh:
        state = json.load(fh)
    state.setdefault("seen_event_ids", [])
    state.setdefault("consecutive_failures", 0)
    return state


def save_state(state):
    with STATE_PATH.open("w") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")


def post_discord(webhook, embeds):
    body = json.dumps({"embeds": embeds}).encode()
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def offer_embed(event):
    rules = (event.get("PROMO_RULES") or "").strip() or "--"
    return {
        "title": "New Kane's Strikeout offer is open",
        "description": event.get("PROMO_NAME") or "Rays 10 strikeout promo",
        "url": SITE_URL,
        "color": RAYS_NAVY,
        "fields": [
            {
                "name": "Game Date",
                "value": str(event.get("EVENT_DATE")),
                "inline": True,
            },
            {
                "name": "Redeem By",
                "value": str(event.get("REGISTRATION_EXPIRED_DATE")),
                "inline": True,
            },
            {"name": "Rules", "value": rules[:1000], "inline": False},
        ],
        "footer": {"text": f"EVENT_ID {event.get('EVENT_ID')}"},
    }


def failure_embed(error, count):
    return {
        "title": "Kane's Strikeout monitor is failing",
        "description": (
            f"{count} consecutive failed checks. The endpoint may have moved "
            f"or changed shape.\n```{str(error)[:500]}```"
        ),
        "color": 0xC8102E,
    }


def main():
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        return 1

    state = load_state()

    try:
        events = fetch_events()
    except Exception as exc:  # transient network/5xx, or the schema moved
        state["consecutive_failures"] += 1
        streak = state["consecutive_failures"]
        print(f"fetch failed ({streak} in a row): {exc}", file=sys.stderr)
        # Fire once when crossing the threshold, not on every run after it.
        if streak == FAILURE_ALERT_THRESHOLD:
            try:
                post_discord(webhook, [failure_embed(exc, streak)])
            except Exception as post_exc:
                print(f"failure alert did not send: {post_exc}", file=sys.stderr)
        save_state(state)
        return 0  # a blip shouldn't paint the whole run red

    state["consecutive_failures"] = 0

    open_events = [
        e for e in events if str(e.get("EVENT_STATUS") or "").upper() == "OPEN"
    ]
    seen = set(state["seen_event_ids"])
    # EVENT_ID, not EVENT_DATE: a doubleheader can put two offers on one date.
    new = [e for e in open_events if e.get("EVENT_ID") not in seen]

    print(f"{len(events)} row(s), {len(open_events)} open, {len(new)} new")

    if not new:
        save_state(state)
        return 0

    for i in range(0, len(new), DISCORD_EMBED_LIMIT):
        chunk = new[i : i + DISCORD_EMBED_LIMIT]
        post_discord(webhook, [offer_embed(e) for e in chunk])
        # Record only what Discord actually accepted, so a mid-way failure
        # retries the stragglers next run instead of dropping them.
        seen.update(e.get("EVENT_ID") for e in chunk)
        state["seen_event_ids"] = sorted(seen)
        save_state(state)

    for e in new:
        print(f"alerted: EVENT_ID {e.get('EVENT_ID')} game {e.get('EVENT_DATE')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
