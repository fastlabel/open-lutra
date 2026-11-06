# Today's collection summary

Operators can check how much they have collected today without leaving the
recording page. The recording bar shows a chip with the day's **OK** episode
count and total duration. A red dot appears when any take failed. Clicking the
chip opens the breakdown:

```
[Today  10 episodes · 32m 10s  (o) v]
   +--------------------------------+
   | Today's collection             |
   | * OK (pass / warn)   10 32m 10s|
   | * Failed              1        |
   | * No result           1        |
   | ------------------------------ |
   |   Total recorded     12        |
   +--------------------------------+
```

Durations read as `16s`, `32m 10s`, or `1h 05m`.

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
`GET /api/config`. A page that is already open keeps the value it loaded, so
reload the recording page after changing it. When it is `false`
the summary is not rendered anywhere and the recording page issues no extra
request. Operators have no UI control to turn it on.

This is a **display switch, not a security control**: the app has no
authentication, anyone with shell access to the host can edit the YAML, and the
recordings list still shows each recording's own duration.

## What is counted

| Overall validation status | Shown as |
|---|---|
| `pass`, `warn` | **OK**: the chip's count and duration |
| `fail` | Failed (also lights the red dot) |
| `error`, or a status the UI does not recognize | Validation error: a validator crashed, see [custom validators](custom_validators.md). Also lights the red dot; the row is listed only when non-zero |
| none | No result: validation is still running, or never produced a result |

- Only OK recordings feed the chip, so adding volume requires takes that pass
  validation. Unknown statuses count as Validation error, never as OK, the same
  way the recording's detail page shows them.
- With no validators at all (no `validators:` entries and no
  [custom validators](custom_validators.md)), every recording passes and counts
  as OK, so the summary reflects quality only as far as the validators check
  it.
- A freshly stopped recording appears as No result and moves to OK (or Failed)
  when its automatic validation completes, with no reload. If the validation
  job itself fails (for example the quality report could not be generated), no
  result is written and the recording stays under No result. Opening the
  recording's detail page starts validation again. Deleting a recording
  removes it from the summary.
- The recording in progress is not counted; it is added when it stops.

## What "today" means

Today is the operator's **local calendar day** in the browser's time zone, from
local midnight to the next local midnight, matched against each recording's
start time. A recording that starts at 23:50 and ends after midnight belongs to
the day it started. The summary rolls over to the new day on its own within a
minute of midnight, or of waking the machine if it slept through it.

The summary fetches only that day through the `started_after` /
`started_before` filter of `GET /api/recordings` (half-open interval, bounds as
RFC 3339 with the browser's UTC offset).
