# SSE (Server-Sent Events) Stream

> Specifies how the backend streams real-time data to the frontend.

## Overview

`GET /api/topics/stream` delivers real-time data over Server-Sent Events. SSE falls outside the OpenAPI standard, so the spec is documented here.

For the REST API endpoint spec, see the Swagger UI that FastAPI generates automatically (`http://localhost:8000/docs`).

## Event list

| Event name | Frequency | Contents |
|---|---|---|
| `topic_stats` | On connect + every 10s | Full snapshot: statistics for all topics (Hz, status, loss_rate, etc.) |
| `topic_stats_delta` | Every 1s (between snapshots) | `{ changed, removed }`: rows that changed since the previous tick (including newly discovered topics) and names of rows that vanished |
| `log` | On occurrence | New log entry (severity, message, timestamp) |

Together, `topic_stats` + `topic_stats_delta` preserve the "one row per topic" contract of `GET /api/topics`: replaying the latest snapshot plus subsequent deltas always yields the current full list. The periodic snapshot also bounds staleness after a missed delta. The diff is computed per connection (`backend/app/features/topics/stream.py`), so a reconnect always starts with a fresh snapshot.

## Connection example

```javascript
const es = new EventSource("/api/topics/stream");

es.addEventListener("topic_stats", (e) => {
  const stats = JSON.parse(e.data);
  // [ { name, actual_hz, status, loss_rate, ... }, ... ] — replace the local list
});

es.addEventListener("topic_stats_delta", (e) => {
  const { changed, removed } = JSON.parse(e.data);
  // changed: [ { name, actual_hz, ... }, ... ] — upsert into the local list
  // removed: [ "/topic_name", ... ] — drop from the local list
});

es.addEventListener("log", (e) => {
  const log = JSON.parse(e.data);
  // { severity, message, timestamp }
});
```

## How it's used on the frontend

The `use-topics-stream.ts` hook manages the SSE connection and writes received data directly into the TanStack Query cache. Components then read the data through the regular Query hooks (`useTopicStats()`, etc.).
