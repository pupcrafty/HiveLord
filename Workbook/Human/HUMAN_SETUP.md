# HUMAN SETUP MANUAL

### Base Project Wiring & API Verification

> **Goal:**
> By the end of this document, your local project should:
>
> * Start without errors
> * Message you on Discord
> * Successfully post to Bluesky
> * Successfully connect to Lovense events
> * Log *everything* to SQLite
> * Enter and exit SAFE MODE reliably

No “intelligence” yet. Just plumbing.

---

## PHASE 0 — BEFORE YOU TOUCH CODE

### ✅ What you need ready

* A computer with:

  * Python **3.11 or newer**
  * Git
* Accounts for:
  
  * Bluesky
  * Discord
  * Lovense (with Lovense Remote app)

---

## PHASE 1 — LOCAL PROJECT SETUP

### 1. Clone or open the project

* Open the folder Cursor generated
* You should see:

  * `app/`, `core/`, `ingest/`, `outputs/`, `storage/`
  * `CURSOR_BOOTSTRAP.md`
  * `.env.example`

### 2. Create a virtual environment

Do **not** skip this.

```bash
python -m venv .venv
source .venv/bin/activate  # mac/linux
.venv\Scripts\activate     # windows
```

### 3. Install dependencies

Use whatever method Cursor set up (`pip`, `poetry`, or `uv`).

Confirm these install without errors:

* httpx
* pydantic
* sqlalchemy
* discord.py
* websockets
* rich

### 4. Create `.env`

* Copy `.env.example` → `.env`
* Leave it empty for now

---

## PHASE 2 — DISCORD (PRIMARY CONTROL CHANNEL)

This is **non-optional**. Everything else depends on it.

### 1. Create a Discord application + bot

1. Go to Discord Developer Portal
2. **New Application**
3. Name it something obvious (e.g. “Authority System”)
4. Open **Bot** → **Add Bot**
5. Copy the **Bot Token**

Paste into `.env`:

```
DISCORD_BOT_TOKEN=PASTE_TOKEN_HERE
```

### 2. Invite the bot

1. OAuth2 → URL Generator
2. Scopes:

   * `bot`
3. Permissions:

   * Send Messages
   * Read Message History
4. Generate URL → open it → add to a private server

### 3. Get your User ID

1. Discord → Settings → Advanced → enable **Developer Mode**
2. Right-click your username → **Copy User ID**

Paste into `.env`:

```
DISCORD_USER_ID=YOUR_ID
```

### 4. First test

Run the app.

**Expected result:**

* You receive a **DM** saying:
  **“System online”**

❌ If not:

* Check bot token
* Check DM privacy
* Make sure you share a server with the bot

Do **not proceed** until this works.

---

## PHASE 3 — BLUESKY (POSTING TEST)

This is the **first write-enabled API**.

### 1. Create an App Password

1. Bluesky → Settings
2. Privacy & Security
3. App Passwords → Create
4. Copy it immediately

### 2. Fill `.env`

```
BSKY_HANDLE=yourhandle.bsky.social
BSKY_APP_PASSWORD=APP_PASSWORD
BSKY_PDS_HOST=https://bsky.social
```

### 3. Test

Run the app.

**Expected result:**

* A post appears on your Bluesky account:

  > “Hello from API (wiring test)”

❌ If not:

* Check handle spelling
* Confirm app password, not account password

---

## PHASE 4 — LOVENSE (EVENTS ONLY)

⚠️ No control commands yet.

### 1. Install Lovense Remote

* Phone app
* Update to latest version

### 2. Enable Toy Events / Game Mode

* In Lovense Remote:

  * Enable Game Mode
  * Enable LAN / Local API access

### 3. Configure project

In `.env`:

```
LOVENSE_MODE=events
```

(Other Lovense values can stay blank for now.)

### 4. Test

Run the app.

**Expected result:**

* Console/log shows:

  * WebSocket connected
  * Device events received
* Events stored in SQLite

❌ If not:

* Game Mode not enabled
* Phone and computer not on same network

---

## PHASE 5 — SAFE MODE TEST (MANDATORY)

This confirms **you can shut everything down instantly**.

### 1. In Discord DM, send:

```
SAFE MODE
```

### 2. Expected result:

* System logs SAFE MODE event
* Consent disabled
* Scheduled tasks canceled
* Lovense actions blocked

### 3. Send:

```
ARM
```

Expected:

* Consent temporarily enabled

### 4. Send:

```
DISARM
```

Expected:

* Consent disabled again

If SAFE MODE fails → **stop and fix it before anything else**.

---

## PHASE 6 — FINAL CHECKLIST

You are done with base wiring when:

* ✅ Discord DM works
* ✅ Bluesky post succeeds
* ✅ Lovense events connect
* ✅ SQLite logs everything
* ✅ SAFE MODE works every time

---

## WHAT COMES NEXT (DO NOT IMPLEMENT YET)

* Recommendation engine
* Authority tone layer
* Human-in-the-loop adult platform workflows
* Lovense control commands
* Content analysis & scoring

---
