# C Project Sync

Last updated: 2026-09-04
Maintainer on this update: Zainab's ChatGPT
Repository: `https://github.com/zaynab-3/C.git`
Working branch used in this session: `feat/fastapi-foundation`

## Purpose

This file is the shared technical handoff between:
- Zainab + Zainab's ChatGPT
- Hoteit + Hoteit's ChatGPT

Authority order:
1. Actual repository code and migrations
2. Verified test/log output
3. This sync file
4. Chat memory / verbal summaries

Do not claim something is implemented unless the repository and/or test evidence supports it.

When either side makes technical progress, update this file with:
- what changed
- what was verified
- what remains pending
- exact next recommended action
- any decision/question the other side must answer

## Current checkpoint

Working local end-to-end mock inbound pipeline:

```text
Mock WhatsApp HTTP event
        ↓
FastAPI
        ↓
Pydantic validation
        ↓
Normalization
        ↓
PostgreSQL persistence
        ↓
Deduplication
        ↓
if NEW → Redis queue
        ↓
Celery worker in Docker/Linux
        ↓
worker reloads message from PostgreSQL
        ↓
background processing confirmed
```

A duplicate webhook is acknowledged without creating or processing the message twice.

## Verified today

### Development environment
- Python 3.13.15 via `uv`
- FastAPI 0.141.1
- SQLAlchemy 2.0.52
- Alembic 1.19.1
- psycopg 3.3.5
- Celery 5.6.3
- WSL 2 working
- Docker Desktop working

### Infrastructure
- PostgreSQL 18.6: `c-postgres` — healthy
- Redis 8 Alpine: `c-redis` — healthy
- Celery worker: `c-worker` — running on Linux/WSL2
- Redis connectivity tested with `PONG`

### API
Current endpoints:
- `GET /health`
- `POST /webhooks/whatsapp`

Current WhatsApp endpoint is a MOCK/internal contract, not yet the real Meta Cloud API payload.

### Validation / normalization
Implemented:
- strict Pydantic mock WhatsApp text schema
- sender/type/text/timestamp validation
- extra fields rejected
- normalized internal message schema

### Persistence
Created `messages` table via Alembic with:
- UUID internal `id`
- `channel`
- `external_id`
- `sender_id`
- `content_type`
- `content`
- `received_at`
- `raw_payload` JSONB
- `created_at`

Deduplication rule:
`UNIQUE(channel, external_id)`

Verified:
- first insert succeeds
- duplicate provider message is rejected by PostgreSQL
- Python repository maps the expected duplicate violation to `duplicate`
- unexpected DB errors are re-raised
- exactly one row remains

### Webhook → DB
Verified:
- first webhook request returns `stored`
- repeated same request returns `duplicate`
- database contains one message only

### Redis / Celery
Verified:
`Python → Redis → Celery worker → task succeeded`

Current worker task:
`c.process_message`

Behavior:
- receives `channel` + `external_id`
- queries PostgreSQL
- loads saved `Message`
- processes/logs it in the worker

Verified E2E test:
- message ID: `wamid.queue.test.001`
- worker received `c.process_message`
- worker loaded the database row
- worker logged:
  `C worker processing: whatsapp / wamid.queue.test.001 / Hello worker from webhook`
- worker task succeeded

This proves the local mock pipeline from HTTP webhook through persistence, queue, and background worker.

## Important current limitations

Not implemented yet:
- real Meta WhatsApp Cloud API webhook payload
- Meta webhook verification challenge
- `X-Hub-Signature-256` signature verification
- WhatsApp sender authorization / allowlist
- real outbound WhatsApp reply
- Gemini/OpenAI intelligence
- LangGraph orchestration
- audio/image/document handling
- action proposal / policy / approvals
- Calendar / Drive / Gmail / MTC adapters
- durable audit model
- retry/dead-letter policy
- transactional outbox / durable DB→queue handoff
- production monitoring/tests/hardening

Known dev issues:
- Celery container currently runs as root; fix before production.
- Docker builds are slow because dependencies download inside the image; optimize caching later.

## Important reliability note

Current flow:

```text
DB commit
   ↓
Celery enqueue
```

There is a small failure window if the DB commit succeeds but queue submission fails.

This is acceptable for the development proof, but not for production.
Before production, implement a transactional outbox / reliable enqueue-retry design.

## Exact next recommended checkpoint

Do not jump to Gemini yet.

Next:
1. Commit the latest webhook→worker integration.
2. Commit this sync file.
3. Add automated tests:
   - new webhook → stored + queued once
   - duplicate webhook → duplicate + not queued again
   - invalid payload → 422
4. Fix Docker worker non-root execution and improve Docker build caching.
5. Begin real Meta Cloud API adapter:
   - webhook verification
   - signature verification
   - real Meta payload parser/adapter
   - sender authorization
6. Only after the real inbound gateway is reliable: connect the AI provider behind a provider abstraction.

## Architecture direction

Keep Python-first:

```text
FastAPI
PostgreSQL
Redis
Celery
SQLAlchemy
Alembic
Pydantic
LangGraph later
Gemini for free development/testing
OpenAI later if Hoteit chooses it
```

AI interprets/proposes.
Deterministic Python owns:
- validation
- identity/authorization
- DB writes
- deduplication
- policy
- approvals
- tool execution
- audit

## Hoteit-side handoff protocol

Hoteit's ChatGPT should inspect the repository and this file before advising Hoteit.

If Hoteit's side makes a decision, finds a conflict, or implements something, its handoff should contain:

- `HOTEIT DECISION`
- `REPO FINDING`
- `WHAT CHANGED`
- `WHAT WAS VERIFIED`
- `CONFLICT / RISK`
- `REQUEST TO ZAINAB`
- `NEXT RECOMMENDED ACTION`

Zainab will bring that handoff back to her ChatGPT. Her ChatGPT will reconcile it against the repository and update this shared sync file.

The GitHub repository is the common technical reference between both sides.

## 2026-09-05 � Gateway hardening checkpoint

### WHAT CHANGED
- Created branch `feat/gateway-hardening`.
- Optimized Docker dependency caching.
- Celery worker now runs as a non-root user.
- Added pytest test suite for the WhatsApp gateway.

### WHAT WAS VERIFIED
- Celery worker starts without the previous root-user warning.
- Worker registers `c.process_message`.
- Worker connects to Redis and reaches ready state.
- Docker rebuild dropped from many minutes to roughly 50 seconds on the first optimized build; future source-only rebuilds can reuse dependency layers.
- Automated gateway tests pass:
  - new webhook -> stored and queued once
  - duplicate webhook -> not queued
  - invalid webhook -> HTTP 422
- Test result: 3 passed.

### NEXT RECOMMENDED ACTION
Start the real Meta webhook adapter, beginning with the GET verification handshake, then POST signature verification and real Meta payload parsing.


## 2026-09-05 � Meta-shaped E2E inbound checkpoint

### WHAT CHANGED
- Replaced the old flat mock WhatsApp payload with Meta-style webhook models.
- Added Meta payload adapter.
- Added POST X-Hub-Signature-256 verification.
- Kept the existing PostgreSQL ? Redis ? Celery flow.

### WHAT WAS VERIFIED
- 7 automated webhook/security tests pass.
- GET webhook verification works.
- Missing/invalid POST signatures are rejected.
- Real Meta-shaped text payload is normalized successfully.
- End-to-end local signed webhook test returned:
  - accepted
  - messages: 1
  - stored: 1
  - duplicates: 0
  - queued: 1
- Celery worker loaded and processed the stored message successfully.

### CURRENT STATUS
The inbound gateway is Meta-compatible in local development.

It is NOT yet connected to the real Meta WhatsApp Cloud API.

### NEXT RECOMMENDED ACTION
Add sender authorization / allowlist before exposing the webhook publicly or connecting a real WhatsApp number.

