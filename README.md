# Ollie Bot

Ollie is a small Discord helper for the stats team.

She reads the PvP roster and the Nova Stats tab from the same Google spreadsheet, compares the names in the configured ranges, and reports missing stats to the stats team channel.

## What Ollie Does

- Runs a daily automatic PvP-roster-vs-stats check.
- Stays quiet if the daily check finds no differences.
- Posts a purple Ollie report if names are missing from the stats sheet.
- Supports `/statscheck`, `/scan`, `/olliestatus`, and `/olliehelp`.
- Also responds to phrases like `ollie show me the list`, `ollie show me missing stats`, and `ollie who hasnt submitted stats`.
- If someone mentions Ollie and she is not sure what they mean, she asks whether they want the missing-stats list.

## Environment Variables

Copy `.env.example` and fill in the real values in Railway.

`GOOGLE_SERVICE_ACCOUNT_JSON` should be the full JSON content of your Google service account key as one env var.

Share the Google Sheet with the service account email so Railway can read it.

## Sheet Settings

Default roster tab:

- `PvP Roster`

Default roster range:

- `B1:F32`

Default stats tab:

- `Nova Stats`

Default stats range:

- `C1:C500`

Change these with:

- `ROSTER_WORKSHEET_NAMES`
- `ROSTER_RANGE`
- `STATS_WORKSHEET_NAME`
- `STATS_RANGE`

Ollie treats every filled cell in those ranges as a name, normalizes punctuation/capitalisation, and reports names on the PvP roster that are missing from Nova Stats.

## Railway

Recommended start command:

```bash
python main.py
```
