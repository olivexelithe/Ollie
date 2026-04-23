# Ollie Bot

Ollie is a Discord logistics assistant for roster checking.

She compares a Google Sheet roster across one or more tabs against Discord members with the `pvp`, `n0va`, and `guest pass` roles, then posts a daily report in `Logistic Council` if she finds anything that needs attention.

## What This Version Does
- Runs a daily automatic scan.
- Stays quiet if there is nothing to report.
- Reads every channel in the Logistics category.
- Watches for natural replies like `sorted`, `snooze`, `ignore`, `needs vera`, `draft dm`, `send it`, and `show me buttons`.
- Treats unmatched `pvp` and `n0va` members as likely Vera cases.
- Understands keepshare roles and avoids flagging shared accounts if their server name includes the keep name.
- Matches roster names if the IGN appears anywhere inside the Discord server name, rather than requiring one exact name format.
- Falls back to the `name change` channel with a tag if a DM cannot be delivered.

## Environment Variables
Copy `.env.example` and fill in the real values in Railway.

Important notes:
- `GOOGLE_SERVICE_ACCOUNT_JSON` should be the full JSON content of your Google service account key as one env var.
- Share the Google Sheet with the service account email so Railway can read it.
- `KEEP_SHARE_ROLE_IDS` can be left blank if you want Ollie to infer keep roles by prefix.
- `KEEP_ROLE_PREFIXES` controls which role names are treated as keep-share roles.
- Leave `GOOGLE_WORKSHEET_NAMES` blank if Ollie should read every tab in the sheet.

## Google Sheet Expectations
This version is now wired for your current sheet layout:

- `PvP Roster`
- `n0va Roster`
- `n0va3 Roster`

It reads the range `B1:F32` on each tab and treats every filled cell in that range as a roster name that should be accounted for in Discord.

There are no required sheet headers in this version.

## Railway
Recommended start command:

```bash
python main.py
```

This repo also includes:
- `Procfile` for a simple worker process
- `railway.json` with a basic restart policy
- `.gitignore` for local env files, caches, and the SQLite database

## Limitations In This First Build
- Matching is based on IGN and display name because the sheet does not contain Discord user IDs.
- If several roster names appear inside the same Discord name, Ollie will leave that for review instead of guessing.
- Message understanding is intentionally narrow and rule-based for safety.
- Buttons are only shown when someone in Logistics asks for them.
- Keepshare awareness is based on keep-share roles and whether the keep name appears in the member's server name.

## Next Things To Tune
- Keep-share role naming rules
- The daily report time
- The DM wording
- Whether roster-unmatched entries should always be reported or filtered further
