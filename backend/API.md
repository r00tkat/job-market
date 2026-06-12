# API Reference

All responses are JSON. All timestamps are ISO 8601 UTC. Every response carries an `X-Request-ID` header with a UUID request id, which is also included in logs and error bodies. Duplicate jobs are excluded from all public responses.

## Error format

All errors use this shape:

```json
{
  "error": "Human-readable description",
  "code": "SNAKE_CASE_CODE",
  "request_id": "uuid"
}
```

### Error codes

| Code | Status | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Invalid query parameter or unknown sort field |
| `BAD_REQUEST` | 400 | Malformed request |
| `NOT_FOUND` | 404 | Unknown path |
| `METHOD_NOT_ALLOWED` | 405 | Wrong HTTP method |
| `SERVICE_UNAVAILABLE` | 503 | Database unreachable (health) |
| `INTERNAL_SERVER_ERROR` | 500 | Unexpected server error |

Stack traces, secrets, and internal paths are never exposed.

---

## GET /health

Service, database, and data freshness status.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "db_latency_ms": 12,
  "last_scrape_at": "2026-06-11T10:00:00Z",
  "jobs_total": 1247,
  "freshness_ok": true
}
```

- `status`: `ok` (DB reachable, latency <= 500 ms), `degraded` (latency > 500 ms), or `error` (DB unreachable).
- HTTP 200 for `ok` and `degraded`; HTTP 503 for `error`.
- `jobs_total` counts non-duplicate jobs only.
- `freshness_ok` is `false` if no successful scrape run exists within `FRESHNESS_THRESHOLD_HOURS` (default 25).

---

## GET /jobs

Paginated job listings.

### Query parameters

| Param | Type | Default | Constraint |
|---|---|---|---|
| `limit` | integer | 20 | min 1, max 100 |
| `offset` | integer | 0 | min 0 |
| `sort` | string | `-posted_at` | `posted_at`, `collected_at`, `title`; prefix `-` for descending |
| `source` | string | none | optional, e.g. `remoteok` |
| `remote_type` | string | none | `remote`, `hybrid`, `onsite`, `unknown` |
| `employment_type` | string | none | `full_time`, `part_time`, `contract`, `internship`, `unknown` |
| `skill` | string | none | canonical skill name or alias, case-insensitive |

Unknown sort fields return 422 with the standard error shape. An unknown `skill` returns an empty result set.

### Example

```bash
curl "http://localhost:8000/jobs?limit=5&skill=python&remote_type=remote"
```

```json
{
  "items": [
    {
      "id": "8e7a...",
      "title": "Senior Backend Engineer",
      "company": { "id": "f3b1...", "name": "Acme Corp", "website": null },
      "location": "Remote",
      "remote_type": "remote",
      "employment_type": "full_time",
      "salary_min": 120000,
      "salary_max": 160000,
      "salary_currency": "USD",
      "source": "remoteok",
      "source_url": "https://remoteok.com/remote-jobs/example",
      "posted_at": "2026-06-11T10:00:00Z",
      "collected_at": "2026-06-11T11:00:00Z",
      "skills": [
        { "canonical_name": "Python", "category": "languages", "confidence": 1.0 }
      ]
    }
  ],
  "total": 1,
  "limit": 5,
  "offset": 0
}
```

`total` is the full filtered count, not the page size.

---

## GET /top-skills

Skill demand counts within a time window, with trend direction versus the previous window of equal length.

### Query parameters

| Param | Type | Default | Constraint |
|---|---|---|---|
| `limit` | integer | 20 | min 1, max 100 |
| `category` | string | none | `languages`, `frameworks`, `cloud`, `databases`, `infrastructure`, `data`, `ml_adjacent` |
| `days` | integer | 30 | min 1, max 365 |

### Example

```bash
curl "http://localhost:8000/top-skills?days=30&category=languages"
```

```json
{
  "items": [
    {
      "skill": "Python",
      "category": "languages",
      "count": 234,
      "rank": 1,
      "prev_count": 198,
      "trend_direction": "up"
    }
  ],
  "window_days": 30,
  "as_of": "2026-06-11T11:00:00Z"
}
```

- Time windows use `coalesce(posted_at, collected_at)`.
- `trend_direction`: `new` (no previous count), `up` (> 5% above previous), `down` (> 5% below previous), `stable` otherwise.
- `prev_count` is `null` for `new`.
- Only non-duplicate jobs are counted.
