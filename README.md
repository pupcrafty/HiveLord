# HiveLord - Multi-API System (Wiring Phase)

A local-first Python system that wires together Instagram, Bluesky, Discord, Telegram, and Lovense APIs with comprehensive logging, consent gates, and safety infrastructure.

## Status

⚠️ **Initial Wiring Phase** - This is the foundation setup phase. No recommendation logic or device control is implemented yet.

## Requirements

- Python 3.11+
- SQLite (local database)
- API credentials for all integrated services (see `.env.example`)

## Setup

1. Install dependencies:
   ```bash
   pip install -e .
   ```

2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

3. Run the application:
   ```bash
   python -m app.main
   ```

## Architecture

- **Local-first**: All data stored in SQLite
- **Safety-first**: Consent gates block device actions unless explicitly armed
- **Logging**: All external interactions are logged to the database
- **DM Control**: Discord (required) and Telegram (optional) serve as control channels

## Features (Wiring Phase)

- ✅ Instagram Graph API integration (read-only)
- ✅ Bluesky AT Protocol integration (session + post)
- ✅ Discord bot (DM-based control)
- ✅ Telegram bot (optional mirror)
- ✅ Lovense Events API (events only, no commands)
- ✅ Consent system with SAFE MODE
- ✅ Comprehensive logging
- ✅ SQLite storage

## Safety Features

- **SAFE MODE**: Send "SAFE MODE" to Discord/Telegram to immediately disable all consent
- **Consent Expiration**: Default 10-minute expiration for device commands
- **Event Logging**: All actions logged to SQLite for audit
- **No Auto-Control**: Device commands are blocked in this phase

## Project Structure

See `CURSOR_BOOTSTRAP.md` for complete specification.

