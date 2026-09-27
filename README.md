**English** | [한국어](README.ko.md)

# AI study Monthly Digest

A repository that summarizes `AI study` discussions **month by month**,
focused on **trends, new releases, and perspectives** from an AI / ML / model standpoint.

## What's In / Out

**Included**
- AI/ML/model trends and currents
- New releases (models, papers, tools, benchmarks) and news
- Substantive perspectives and debates from the discussion

**Excluded**
- Course/seminar announcements by individual instructors
- Promotional content (contests, events, recruiting, product ads)
- Personal daily chatter (photos, small talk, greetings)

**Attribution policy (public)**
- **No speaker attribution** for participants (no names, affiliations, or handles). Opinions and debates are summarized by content only, without "who said it."
- Public figures cited in news/papers, and company/organization/model names, are kept as-is.

## File Layout

- `YYYY-MM.md` — monthly summary (Korean)
- `YYYY-MM.en.md` — monthly summary (English)
- `raw/`, `KakaoTalkChats*.txt` — raw chat export (not committed, see `.gitignore`)

## Index

| Month | Summary |
|-------|---------|
| 2025-12 | [December 2025](2025-12.en.md) |
| 2026-01 | [January 2026](2026-01.en.md) |
| 2026-02 | [February 2026](2026-02.en.md) |
| 2026-03 | [March 2026](2026-03.en.md) |
| 2026-04 | [April 2026](2026-04.en.md) |
| 2026-05 | [May 2026](2026-05.en.md) |
| 2026-06 | [June 2026](2026-06.en.md) |
| 2026-07 | [July 2026](2026-07.en.md) |
| 2026-08 | [August 2026](2026-08.en.md) |
| 2026-09 | [September 2026 (through 09-27)](2026-09.en.md) |

## How to Update

The export always contains the **full** conversation, so already-summarized
messages are filtered out automatically by `scripts/parse_kakao.py`, which
tracks the timestamp of the last processed message in a state file
(`.kakao_state.json`).

1. Drop the chat export into the repo root as `KakaoTalkChats.txt`.
2. Extract only the new messages, grouped by month:
   ```bash
   python scripts/parse_kakao.py KakaoTalkChats.txt
   ```
   This writes `raw/pending/YYYY-MM.txt` for each month with new messages (state is left untouched).
3. Summarize `raw/pending/*.txt` into `YYYY-MM.md` (and `YYYY-MM.en.md`).
4. Once summarized, advance the state and clear pending:
   ```bash
   python scripts/parse_kakao.py --advance
   ```
5. Commit and push: `git add . && git commit && git push`.

**Options**
- `--all` — re-extract everything, ignoring state (for initial build / rebuild)
- `--since YYYY-MM-DD` — override the cutoff for this run only

The export format (PC / Android / iOS) is auto-detected; date separators and
join/leave system notices are dropped automatically.
