# Treasury Bot (Slash Commands)

Treasury-grade Discord bot for KHK:
- `/summary`, `/category <name>`
- `/pending`, `/markpaid <row>`
- `/export`
- Background notifier for new reimbursement rows with a **Mark Paid** button
- Budget↔Reimbursement auto-sync, audit log

## Google Sheets
- Spreadsheet: **Fall 2025 Budget**
- **Budget** at index **0**, **Reimbursement** at index **1** (as provided):contentReference[oaicite:4]{index=4}:contentReference[oaicite:5]{index=5}.
- A **LedgerLog** sheet is auto-created for audits.

## Setup
1. `pip install -r requirements.txt`
2. Put your Google service account file as `credentials.json`.
3. Copy `config.example.json` → `config.json` and fill values:
   - `bot_token`, `guild_id`, `treasury_channel_id`, `moderator_channel_id`
   - `treasurer_role_id` (or null)
4. Run: `python main.py`

## Permissions
- The **Mark Paid** button and `/markpaid` are restricted by `treasurer_role_id` if set.

## Notes
- Header names in both sheets are **matched flexibly**; you can rename columns like “Amount (in $)” or “What is the amount of money requested?” and the bot will still detect them.
- If a category in Reimbursement doesn’t match a Budget row, the bot will mark as paid but **won’t** update any category (to avoid misallocations). You can refine the fuzzy match in `sheet_handler.py`.
