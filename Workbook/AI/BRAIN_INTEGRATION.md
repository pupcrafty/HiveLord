
# WORKBOOK PAGE (FOR CURSOR)

## Wire OpenAI Responses API into Dom Bot (Tools + Memory + Scheduler)

### Mission

Implement a Dom Bot controller that:

1. generates **directive**, cohesive freeform text
2. emits **structured, parseable results** every turn
3. calls **approved tools** to schedule and execute actions:

   * Discord send now / schedule message
   * Bluesky schedule post (text + optional image)
   * DB memory search / upsert
   * in-app scheduler one-shot jobs

Use:

* **Responses API** ([OpenAI Platform][1])
* **Tool calling (function calling)** ([OpenAI Platform][2])
* **Structured Outputs with strict JSON Schema** ([OpenAI Platform][3])

---

## 0) Non-negotiable Dom Mode Contract

Dom mode exists because the user explicitly consents by running the app and enabling the setting.

**You enforce consent with code.** If dom mode is off, you do not send directives and you do not schedule/post.

Add a helper:

* `app/core/settings.py`: `is_dom_mode_enabled() -> bool`

Enforce it at the Discord ingress point (before calling OpenAI).

---

## 1) Create the “Dom Bot brain” module

Create directory:

* `app/ai/`

Create files:

* `app/ai/dom_bot.py`  ✅ main loop (Responses API + tools)
* `app/ai/tools.py` ✅ tool definitions (JSON schema for each)
* `app/ai/contracts.py` ✅ final response JSON schema
* `app/ai/tool_handlers.py` ✅ executes tool calls via existing integrations
* `app/ai/audit.py` ✅ logs every tool call/result + final JSON

---

## 2) Final output contract (strict JSON schema)

Create: `app/ai/contracts.py`

Define one schema the model must output **every turn**.

Keys:

* `message` (string): directive response to send immediately
* `actions` (array): every action taken/scheduled
* `memory_write` (array optional): DB writes
* `needs_followup` (bool)
* `followup_question` (string|null)

Use strict mode. Structured Outputs guarantees the response matches schema. ([OpenAI Platform][3])

---

## 3) Define tool surface (only what the bot may do)

Create: `app/ai/tools.py`

Define function tools for:

* `memory_search`
* `memory_upsert`
* `discord_send_now`
* `discord_schedule_message`
* `bsky_schedule_post`

Tool calling is the only way the model touches external systems. ([OpenAI Platform][2])

**Rule:** if it isn’t a tool, it doesn’t exist.

---

## 4) Add one-shot scheduling to the in-app scheduler

Your scheduler exists in `app/core/scheduler.py` and runs an asyncio loop in a background thread.

You need a one-shot scheduling primitive.

Add:

* `schedule_at(when_dt_utc, coro_fn, name=None) -> task_id`

This method sleeps until `when_dt_utc`, then runs `coro_fn()` once. It returns a cancelable task id.

Also add:

* `cancel_task(task_id)`
* ensure idempotency at the job handler level (DB job record or dedupe key)

---

## 5) Tool handlers: connect tools to your existing scaffold

Create: `app/ai/tool_handlers.py`

Implement:

* `memory_search(args)` → DB query (your memory/events table)
* `memory_upsert(args)` → DB insert/upsert
* `discord_send_now(args)` → your Discord send function
* `discord_schedule_message(args)` → `get_scheduler().schedule_at(...)` which calls Discord send
* `bsky_schedule_post(args)` → `get_scheduler().schedule_at(...)` which calls Bluesky post (text/image)

**Return structured result objects** (task_id, message_id, post_uri). The model uses these results to honestly confirm actions.

---

## 6) Build the Responses API agent loop (this is the wiring you asked for)

Create: `app/ai/dom_bot.py`

Implement:

### A) System instruction (Dom voice + tool discipline)

Dom voice rules:

* use active voice
* issue directives
* do not hedge
* ask exactly one blocking question when needed
  Tool discipline:
* call tools for actions/memory
* never claim execution without tool output
* always return final strict JSON

### B) Call OpenAI Responses API with tools + strict JSON output

Responses API is the path. ([OpenAI Platform][1])
Function calling is how it takes actions. ([OpenAI Platform][2])
Structured Outputs (strict) is how you get guaranteed parseable final JSON. ([OpenAI Platform][3])

### C) Loop

1. Send user text + minimal context
2. If model returns tool calls:

   * execute each tool
   * append `function_call_output` items
   * repeat
3. When model returns final structured JSON:

   * validate against schema
   * return to caller

(Use the Responses “Items” model; Responses uses items rather than ChatCompletions messages. ([OpenAI Platform][4]))

---

## 7) Wire it into Discord ingress

Find your Discord inbound handler (where you receive DMs).

Flow:

1. If dom mode off → send neutral “Dom mode disabled” response and exit
2. Call `dom_bot.respond(user_text, channel_id, user_id)`
3. Send `final.message` immediately to Discord
4. Write `final.memory_write` to DB (or let the model call `memory_upsert`—pick one approach and stick to it)
5. Persist `final.actions` + tool audit log

---

## 8) Required safety rails (code-enforced)

You enforce these rules in server code, not in prompts.

1. **Tool allowlist**
   Reject unknown tools.

2. **Time sanity**
   Reject scheduling in the past. If it’s “tomorrow 9,” resolve timezone explicitly (America/New_York unless user overrides).

3. **Bluesky posting intent**
   Require explicit user intent in the current message or an opt-in flag stored in DB preferences. If missing, the bot asks one direct question.

4. **No silent side effects**
   Every scheduler job logs: tool name, args, when, task_id, status.

---

## 9) Acceptance tests (run these)

You’re done when all pass:

1. “Remind me tomorrow at 9am to hydrate.”

* Tool calls: `discord_schedule_message`
* Bot message: directive confirmation
* DB: action log includes task_id

2. “Post this image to Bluesky tomorrow at noon with a caption.”

* Tool calls: `bsky_schedule_post`
* Bot message: directive confirmation + what it scheduled
* Scheduler: job exists

3. “Post later.”

* No tool calls
* Bot asks one direct question: “Give me the exact time.”

4. Dom mode disabled

* Bot refuses directives and takes no actions

---

## 10) Model selection

Pick a tool-capable model and keep it consistent across dev/prod.

(Responses + tool calling + structured outputs works across supported tool-capable models.) ([OpenAI Platform][2])

you can start implementing now with the steps above.

[1]: https://platform.openai.com/docs/api-reference/responses?utm_source=chatgpt.com "Responses | OpenAI API Reference"
[2]: https://platform.openai.com/docs/guides/function-calling?utm_source=chatgpt.com "Function calling | OpenAI API"
[3]: https://platform.openai.com/docs/guides/structured-outputs?utm_source=chatgpt.com "Structured model outputs | OpenAI API"
[4]: https://platform.openai.com/docs/guides/migrate-to-responses?utm_source=chatgpt.com "Migrate to the Responses API"
