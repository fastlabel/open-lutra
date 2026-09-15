# SSE (Server-Sent Events) Streams

> Specifies how the backend streams real-time data to the frontend. SSE falls outside the OpenAPI standard, so the spec is documented here.

For the REST API endpoint spec, see the Swagger UI that FastAPI generates automatically (`http://localhost:8000/docs`).

## `GET /api/topics/stream` — topic monitoring

| Event name | Frequency | Contents |
|---|---|---|
| `topic_stats` | Every 1s | Statistics for all topics (Hz, status, loss_rate, etc.) |
| `log` | On occurrence | New log entry (severity, message, timestamp) |

### Connection example

```javascript
const es = new EventSource("/api/topics/stream");

es.addEventListener("topic_stats", (e) => {
  const stats = JSON.parse(e.data);
  // { "/topic_name": { actual_hz, status, loss_rate, ... }, ... }
});

es.addEventListener("log", (e) => {
  const log = JSON.parse(e.data);
  // { severity, message, timestamp }
});
```

## `GET /api/jobs/stream` — background job progress

Sends the current queue snapshot on connect, then streams status-change events. The payload schemas live in `backend/app/features/jobs/schemas.py` (`QueueSnapshotEvent` / `JobChangeEvent`).

| Event name | Frequency | Contents |
|---|---|---|
| `queue_snapshot` | On connect | All jobs currently known to the queue |
| `job_added` / `job_started` / `job_progress` / `job_completed` / `job_failed` | On occurrence | The affected job (id, type, folder, status, progress, error) |

## `GET /api/topics/live/stream?topic=...` — Live-mode sensor positions

Unnamed `data:` events (the default `message` event) carrying the latest position array of the selected sensor topic, sent at 30fps while Live mode is on.

## How SSE data reaches the UI

The `use-topics-stream.ts` and `use-jobs-stream.ts` hooks manage the connections and write received data directly into the TanStack Query cache. Components then read the data through the regular Query hooks (`useTopicStats()`, etc.).
