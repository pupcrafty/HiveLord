

# CURSOR_BOOTSTRAP.md

## Authority-Driven Multi-API System — Initial Wiring Phase

---

## 0. PURPOSE (READ FIRST)

This document defines **all steps, structure, rules, and constraints** required to generate a **local-first Python project** that wires together:

* Bluesky (AT Protocol, open API)
* Discord (bot, DM-first control channel)
* Lovense (official developer APIs: events first, control gated)

The system **must not**:

* Perform explicit sexual actions
* Bypass Terms of Service
* Issue device commands without explicit consent gates

This phase is **wiring only**:

* Auth
* Connectivity
* Logging
* Consent & safety infrastructure
* “Hello world” validation for each integration

No recommendation logic yet.

---

## 1. GLOBAL CONSTRAINTS

* Language: **Python 3.11+**
* Architecture: **local-first**
* Storage: **SQLite**
* Secrets: **environment variables only**
* All external actions must be **logged**
* All device actions must be **blocked unless consent gates pass**

---

## 2. PROJECT STRUCTURE (MUST MATCH EXACTLY)

```
project/
  README.md
  CURSOR_BOOTSTRAP.md
  .env.example
  .gitignore
  pyproject.toml

  app/
    main.py

    config/
      settings.py

    core/
      logger.py
      consent.py
      scheduler.py

    ingest/
      bluesky_client.py
      lovense_client.py

    outputs/
      discord_client.py

    storage/
      db.py
      models.py
```

---

## 3. DEPENDENCIES (pyproject.toml)

Install and configure the following libraries:

* `httpx`
* `python-dotenv`
* `pydantic`
* `sqlalchemy`
* `discord.py`
* `websockets`
* `rich` (for readable local logs)

---

## 4. ENVIRONMENT VARIABLES (.env.example)

```env
# =====================
# Bluesky
# =====================
BSKY_HANDLE=
BSKY_APP_PASSWORD=
BSKY_PDS_HOST=https://bsky.social

# =====================
# Discord
# =====================
DISCORD_BOT_TOKEN=
DISCORD_USER_ID=
DISCORD_GUILD_ID=

# =====================
# Lovense
# =====================
LOVENSE_DEVELOPER_TOKEN=
LOVENSE_CALLBACK_URL=
LOVENSE_MODE=events  # events | standard | socket
```

---

## 5. CONFIGURATION LAYER (`config/settings.py`)

* Load all environment variables using `pydantic.BaseSettings`
* Fail fast if required variables are missing
* Expose settings as a singleton
* Never print secrets to logs

---

## 6. STORAGE LAYER (`storage/db.py`, `storage/models.py`)

### SQLite database: `local.db`

#### Tables

### `runs`

| column     | type     |
| ---------- | -------- |
| id         | int      |
| started_at | datetime |
| ended_at   | datetime |
| version    | text     |
| notes      | text     |

### `events`

| column       | type     |
| ------------ | -------- |
| id           | int      |
| ts           | datetime |
| source       | text     |
| type         | text     |
| payload_json | text     |

### `consent_ledger`

| column              | type     |
| ------------------- | -------- |
| id                  | int      |
| ts                  | datetime |
| consent_active      | boolean  |
| allowed_modes_json  | text     |
| revoked_topics_json | text     |
| armed_until_ts      | datetime |

---

## 7. LOGGING (`core/logger.py`)

Implement a logger that:

* Writes **every external interaction** to `events`
* Redacts secrets
* Logs:

  * API requests (metadata only)
  * API responses (sanitized)
  * Messages sent to Discord
  * Lovense events
  * Errors
* Supports replay/debug from DB alone

---

## 8. CONSENT SYSTEM (`core/consent.py`)

### Rules (MANDATORY)

* No Lovense commands unless:

  * `consent_active == true`
  * `armed_until_ts > now`
  * topic `"device"` is allowed
* Consent expires automatically (default: 10 minutes)
* Implement **SAFE MODE**:

  * Any "SAFE MODE" message from Discord:

    * Sets `consent_active = false`
    * Clears `armed_until_ts`
    * Cancels scheduled tasks
    * Logs event

---

## 9. OUTPUT CHANNELS

### Discord (`outputs/discord_client.py`)

* Bot must:

  * DM a single user (via `DISCORD_USER_ID`)
  * Send:

    * “System online”
    * Error notifications
    * Consent prompts
* Support receiving commands:

  * `ARM`
  * `DISARM`
  * `SAFE MODE`

---

## 10. INGEST CLIENTS

### Bluesky (`ingest/bluesky_client.py`)

* Implement:

  1. `createSession`
  2. `createRecord` (post)
* Allow posting a single test message:

  > “Hello from API (wiring test)”

### Lovense (`ingest/lovense_client.py`)

**Phase 1: EVENTS ONLY**

* Connect using official Lovense Events API
* WebSocket connection
* Log:

  * Connection success
  * Device connect/disconnect
  * Event payloads
* DO NOT issue commands in this phase

---

## 11. SCHEDULER (`core/scheduler.py`)

* Lightweight task scheduler
* Used for:

  * Periodic API polling
  * Consent expiration checks
* Must be cancelable by SAFE MODE

---

## 12. MAIN ENTRYPOINT (`app/main.py`)

On startup:

1. Initialize database
2. Start run record
3. Initialize logger
4. Initialize consent system
5. Start Discord bot
6. Validate:

   * Bluesky post
   * Lovense event connection
7. Send "System online" to Discord
8. Block until shutdown

On shutdown:

* Close connections
* Mark run ended

---

## 13. MILESTONE DEFINITION (STOP HERE)

This wiring phase is **complete** when:

* Discord DM works
* Bluesky post succeeds
* Lovense events stream connects
* All actions are logged to SQLite
* SAFE MODE reliably disables everything

No intelligence, no recommendations, no device control yet.

---

## 14. IMPORTANT INSTRUCTION TO CURSOR

> Generate this project exactly as described.
> Prefer clarity and safety over cleverness.
> Do not invent features not listed here.
> Do not skip logging, consent, or safety gates.

