# Today's collection summary

Operators can check how much they have collected today without leaving the
recording page. The right edge of the app header has a **Today's collection**
button, so it is reachable from every page; clicking it opens a dialog that
breaks today's recordings down by validation result:

```
[Today's collection]
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

The summary is on demand: today's recordings are fetched when the dialog
opens, and again each time it is reopened. Nothing is fetched while the dialog
is closed.

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
reload the page after changing it. When it is `false`
the button is not rendered. Operators have no UI control to turn it on.

This is a **display switch, not a security control**: the app has no
authentication, anyone with shell access to the host can edit the YAML, and the
recordings list still shows each recording's own duration.

## What is counted

| Overall validation status | Shown as |
|---|---|
| `pass`, `warn` | **OK**: counted with their total duration |
| `fail` | Failed |
| `error`, or a status the UI does not recognize | Validation error: a validator crashed, see [custom validators](custom_validators.md). The row is listed only when non-zero |
| none | No result: validation is still running, or never produced a result |

- Only OK recordings count toward the collected duration, so adding volume
  requires takes that pass validation. Unknown statuses count as Validation
  error, never as OK, the same way the recording's detail page shows them.
- With no validators at all (no `validators:` entries and no
  [custom validators](custom_validators.md)), every recording passes and counts
  as OK, so the summary reflects quality only as far as the validators check
  it.
- Only recordings with a start time are counted. The start time comes from
  the `metadata.yaml` that `ros2 bag` writes when recording stops, so the
  recording in progress, and a take whose recorder exited before writing it
  (for example on a crash or power loss), appear in no row, not even Total
  recorded.
- A freshly stopped recording appears as No result and moves to OK (or Failed)
  once its automatic validation has completed. If the validation job itself
  fails (for example the quality report could not be generated), no
  result is written and the recording stays under No result. Opening the
  recording's detail page runs a missing quality analysis again; once it has
  finished, opening the **Validation** tab starts validation. A recording whose
  quality analysis cannot run at all stays under No result. Deleting a
  recording removes it from the summary.

## What "today" means

Today is the operator's **local calendar day** in the browser's time zone, from
local midnight to the next local midnight, matched against each recording's
start time. A recording that starts at 23:50 and ends after midnight belongs to
the day it started. The day is taken from the browser's clock when the dialog
opens.

The summary fetches only that day through the `started_after` /
`started_before` filter of `GET /api/recordings` (half-open interval, bounds as
RFC 3339 with the browser's UTC offset).
