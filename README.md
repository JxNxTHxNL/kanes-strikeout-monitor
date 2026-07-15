# Kane's Strikeout Monitor

Pings a Discord channel when a new [Kane's Strikeout](https://kanesstrikeout.com/)
offer opens — i.e. when Rays pitchers throw 10 strikeouts in a home game and a
voucher for a free Busch Gardens ticket becomes redeemable.

Vouchers expire 5 days after the game, so the point is to not find out late.

## How it works

`kanesstrikeout.com` is a frameset around `rays.kanesfurniture.com`. On that
page, `<div id="openEvents">` is **empty in the served HTML** — the
`Game Date: ...` markup sitting in the source is a commented-out template, not
live data. The real data arrives at runtime from:

```
GET https://rays.kanesfurniture.com/getOpenEvents/
      ?empCd=KF_PROMO_RAYS_EXT&partner=RAYS&periodType=REG
```

`/js/index` renders `rows[i][9]` (`EVENT_DATE`) under the "Game Date" header,
and bounces to `/nopromo` when `rows` is empty. So we poll that JSON directly —
no browser, no HTML parsing.

A sample row:

| Column | Value |
| --- | --- |
| `PROMO_NAME` | `RAYS 10 FIRST STRIKEOUT` |
| `EVENT_ID` | `845` |
| `EVENT_DATE` | `07-11-2026` ← the "Game Date" |
| `EVENT_STATUS` | `OPEN` |
| `REGISTRATION_EXPIRED_DATE` | `07-16-2026` |

Two deliberate choices:

- **Keyed on `EVENT_ID`, not `EVENT_DATE`.** A doubleheader can produce two
  offers on one date; IDs stay unique.
- **Columns read by `metaData` name, not index.** The site's own JS hardcodes
  `rows[9]`, which breaks silently if the query ever gains a column.

## Setup

1. Create a Discord webhook: Server Settings → Integrations → Webhooks → New.
2. Store it as a repo secret (the value never touches the source tree):
   ```sh
   gh secret set DISCORD_WEBHOOK_URL
   ```
3. Actions → **Check for new offers** → **Run workflow** to test immediately.

## Behaviour

- Polls every 15 minutes. Free on public repos; a private repo would blow past
  the 2,000 min/month tier at this cadence, since Actions rounds each run up to
  a full minute.
- `state.json` records seen `EVENT_ID`s and is committed back — only when an
  offer actually changes, so a handful of commits a month. It's durable and
  doubles as a log of every offer ever seen. (The Actions cache was the
  alternative, but it evicts after 7 days, which would mean silent duplicate or
  missed alerts.)
- `rows: []` is normal — that's the off-season / no-qualifying-game state.
- Network blips are swallowed. Eight consecutive failures (~2 hours) sends one
  Discord warning, because a monitor that dies quietly is worse than none.
- `keepalive.yml` commits monthly. GitHub disables cron after 60 days of repo
  inactivity, and the off-season is longer than that.

## Local run

```sh
DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' python3 monitor.py
```

No dependencies — Python 3 stdlib only.
