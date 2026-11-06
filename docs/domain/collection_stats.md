# Today's collection summary

Operators can check how much they have collected today without leaving the
recording page: the recording bar shows the day's **usable** episode count and
total duration, followed by the total count and a breakdown of the rest.

```
Today  10 usable · 32m 10s
12 total · 1 failed · 1 pending
```

## Off by default

Seeing collected volume can push operators to chase duration at the expense of
quality, so the summary is **hidden unless the deploying side enables it** in
the active recording config (`config/<robot>.yaml`, selected via
`RECORDING_CONFIG`):

```yaml
collection_stats:
  enabled: true   # default: false (also when the section is omitted)
```

The value is served to the UI as `collection_stats_enabled` on
`GET /api/config`; restart the backend after changing it. When it is `false`
the summary is not rendered anywhere and the recording page issues no extra
request. Operators have no UI control to turn it on.

This is a **display switch, not a security control**: the app has no
authentication, anyone with shell access to the host can edit the YAML, and the
recordings list still shows each recording's own duration.

## What is counted

| Overall validation status | Counted as |
|---|---|
| `pass`, `warn` | **usable** — the headline count and duration |
| `fail` | failed |
| `error` | validation error (a validator crashed; see [custom validators](custom_validators.md)) |
| none yet | pending — validation has not finished |

- Only usable recordings feed the headline, so adding volume requires takes
  that pass validation. Unknown statuses count as pending, never as usable.
- A freshly stopped recording appears as pending and moves to usable (or
  failed) when its automatic validation completes — no reload needed. Deleting
  a recording removes it from the summary.
- The recording in progress is not counted; it is added when it stops.

## What "today" means

Today is the operator's **local calendar day** in the browser's time zone, from
local midnight to the next local midnight, matched against each recording's
start time. A recording that starts at 23:50 and ends after midnight belongs to
the day it started. The summary rolls over to the new day at midnight on its
own.

The summary fetches only that day through the `started_after` /
`started_before` filter of `GET /api/recordings` (half-open interval, bounds as
RFC 3339 with the browser's UTC offset).
