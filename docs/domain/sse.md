# SSE (Server-Sent Events) Stream

> Specifies how the backend streams real-time data to the frontend.

## Overview

`GET /api/topics/stream` delivers real-time data over Server-Sent Events. SSE falls outside the OpenAPI standard, so the spec is documented here.

For the REST API endpoint spec, see the Swagger UI that FastAPI generates automatically (`http://localhost:8000/docs`).

## Event list

| Event name | Frequency | Contents |
|---|---|---|
| `topic_stats` | Every 1s | Statistics rows that changed since the previous event on this connection (Hz, status, loss_rate, etc.). The first event on a connection carries every row; a tick with no changes sends an empty array (keep-alive) |
| `log` | On occurrence | New log entry (severity, message, timestamp) |

The diff is computed per connection (`backend/app/features/topics/stream.py`) against an empty initial state, so the first `topic_stats` after a (re)connect is always a full snapshot — clients replace their list on that event and merge changed rows afterwards. Rows are never removed within a backend's lifetime (a topic whose publisher vanished stays visible as an idle row), so replaying the first event plus subsequent diffs always yields the current full list and the "one row per topic" contract of `GET /api/topics` is preserved.

## Connection example

```javascript
const es = new EventSource("/api/topics/stream");

let replaceNext = true;
es.onopen = () => {
  replaceNext = true; // reconnected: the next event carries every row
};

es.addEventListener("topic_stats", (e) => {
  const changed = JSON.parse(e.data);
  // [ { name, actual_hz, status, loss_rate, ... }, ... ]
  // replaceNext ? replace the local list : upsert into the local list
  replaceNext = false;
});

es.addEventListener("log", (e) => {
  const log = JSON.parse(e.data);
  // { severity, message, timestamp }
});
```

## How it's used on the frontend

The `use-topics-stream.ts` hook manages the SSE connection and writes received data directly into the TanStack Query cache. Components then read the data through the regular Query hooks (`useTopicStats()`, etc.).
