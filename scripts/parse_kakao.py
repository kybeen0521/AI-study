#!/usr/bin/env python3
"""
KakaoTalk OpenChat export -> incremental, per-month chunks.

The export always contains the FULL history. This script keeps a small state
file (.kakao_state.json) with the timestamp of the last message that was already
summarized, and emits only the messages newer than that, grouped by month.

Typical workflow
----------------
1. Export the chat as .txt (PC KakaoTalk recommended) into this repo.
2. python scripts/parse_kakao.py KakaoTalkChats.txt
     -> writes raw/pending/YYYY-MM.txt for every month that has NEW messages
     -> prints a summary; does NOT touch state yet.
3. Summarize the pending chunks into YYYY-MM.md / .en.md (hand them to Claude).
4. python scripts/parse_kakao.py --advance
     -> advances state to the newest processed message and clears raw/pending/.

Supported export formats (auto-detected)
----------------------------------------
- PC / Windows:  "--------------- 2025년 12월 1일 월요일 ---------------"
                 "[name] [오전 1:23] message"
- Android:       "2025년 12월 1일 오전 1:23, name : message"
- iOS:           "2025. 12. 1. 오전 1:23, name : message"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / ".kakao_state.json"
PENDING_DIR = ROOT / "raw" / "pending"
MAX_TS_MARKER = PENDING_DIR / ".max_ts"

# --- date/time helpers -------------------------------------------------------

_AMPM = {"오전": 0, "오후": 12}


def _to_24h(ampm: str, hour: int) -> int:
    """Convert Korean 오전/오후 + 12h hour to 24h."""
    hour = hour % 12
    if ampm == "오후":
        hour += 12
    return hour


# --- message model -----------------------------------------------------------


@dataclass
class Message:
    ts: datetime
    author: str
    text: str

    @property
    def month_key(self) -> str:
        return f"{self.ts.year:04d}-{self.ts.month:02d}"


# --- parsers -----------------------------------------------------------------

# Android:  2025년 12월 1일 오전 1:23, 홍길동 : 메시지
RE_ANDROID = re.compile(
    r"^(?P<y>\d{4})년\s*(?P<mo>\d{1,2})월\s*(?P<d>\d{1,2})일\s*"
    r"(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<mi>\d{2}),\s*"
    r"(?P<author>.*?)\s*:\s(?P<text>.*)$"
)

# iOS:  2025. 12. 1. 오전 1:23, 홍길동 : 메시지
RE_IOS = re.compile(
    r"^(?P<y>\d{4})\.\s*(?P<mo>\d{1,2})\.\s*(?P<d>\d{1,2})\.\s*"
    r"(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<mi>\d{2}),\s*"
    r"(?P<author>.*?)\s*:\s(?P<text>.*)$"
)

# PC separator:  --------------- 2025년 12월 1일 월요일 ---------------
RE_PC_DATE = re.compile(
    r"^-+\s*(?P<y>\d{4})년\s*(?P<mo>\d{1,2})월\s*(?P<d>\d{1,2})일.*?-+\s*$"
)

# PC message:  [홍길동] [오전 1:23] 메시지
RE_PC_MSG = re.compile(
    r"^\[(?P<author>.*?)\]\s*\[(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<mi>\d{2})\]\s?(?P<text>.*)$"
)

# Any timestamped line prefix (used to detect date-header / system lines that
# start with a timestamp but are NOT real messages, e.g.
#   "2025년 12월 12일 오전 5:57"                       <- session date header
#   "2025년 12월 11일 오전 8:14, 홍길동님이 들어왔습니다."  <- join/leave notice
# These must be skipped, never appended as a continuation of the prior message.
RE_TS_PREFIX = re.compile(
    r"^\d{4}년\s*\d{1,2}월\s*\d{1,2}일\s*(오전|오후)\s*\d{1,2}:\d{2}\b"
)


def _mk(y, mo, d, ampm, h, mi, author, text) -> Message:
    dt = datetime(int(y), int(mo), int(d), _to_24h(ampm, int(h)), int(mi))
    return Message(ts=dt, author=author.strip(), text=text)


def parse(lines: list[str]) -> list[Message]:
    """Parse lines from any supported format. Continuation lines are appended
    to the previous message."""
    messages: list[Message] = []
    cur_date = None  # for PC format (date carried from separator line)

    for raw in lines:
        line = raw.rstrip("\n")

        # PC date separator
        m = RE_PC_DATE.match(line)
        if m:
            cur_date = (m["y"], m["mo"], m["d"])
            continue

        # Android / iOS single-line message
        m = RE_ANDROID.match(line) or RE_IOS.match(line)
        if m:
            messages.append(
                _mk(m["y"], m["mo"], m["d"], m["ampm"], m["h"], m["mi"],
                    m["author"], m["text"])
            )
            continue

        # PC message line (needs a current date)
        m = RE_PC_MSG.match(line)
        if m and cur_date is not None:
            messages.append(
                _mk(cur_date[0], cur_date[1], cur_date[2], m["ampm"], m["h"],
                    m["mi"], m["author"], m["text"])
            )
            continue

        # Timestamped but not a real message: session date header or a
        # join/leave/system notice. Skip — do NOT treat as a continuation.
        if RE_TS_PREFIX.match(line):
            continue

        # Continuation of previous message (multi-line text)
        if messages and line.strip():
            messages[-1].text += "\n" + line

    return messages


# --- state -------------------------------------------------------------------


def load_state() -> datetime | None:
    if not STATE_FILE.exists():
        return None
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    ts = data.get("last_timestamp")
    return datetime.fromisoformat(ts) if ts else None


def save_state(ts: datetime) -> None:
    STATE_FILE.write_text(
        json.dumps({"last_timestamp": ts.isoformat()}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


# --- commands ----------------------------------------------------------------


def cmd_parse(txt_path: Path, since: datetime | None) -> int:
    if not txt_path.exists():
        print(f"[error] file not found: {txt_path}", file=sys.stderr)
        return 1

    # KakaoTalk exports are UTF-8 (BOM on some Windows exports).
    text = txt_path.read_text(encoding="utf-8-sig", errors="replace")
    messages = parse(text.splitlines())
    if not messages:
        print("[warn] no messages parsed — is this a KakaoTalk export? "
              "Check the format.", file=sys.stderr)
        return 1

    cutoff = since if since is not None else load_state()
    if cutoff is not None:
        new = [m for m in messages if m.ts > cutoff]
    else:
        new = messages

    print(f"parsed:  {len(messages)} messages "
          f"({messages[0].ts:%Y-%m-%d} → {messages[-1].ts:%Y-%m-%d})")
    print(f"cutoff:  {cutoff:%Y-%m-%d %H:%M}" if cutoff else "cutoff:  (none — first run)")
    print(f"new:     {len(new)} messages")

    if not new:
        print("nothing new. done.")
        return 0

    # Group new messages by month and write pending files.
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[Message]] = {}
    for m in new:
        by_month.setdefault(m.month_key, []).append(m)

    for month, msgs in sorted(by_month.items()):
        out = PENDING_DIR / f"{month}.txt"
        body = "\n".join(f"[{m.ts:%Y-%m-%d %H:%M}] {m.author}: {m.text}" for m in msgs)
        out.write_text(body + "\n", encoding="utf-8")
        print(f"  wrote {out.relative_to(ROOT)}  ({len(msgs)} messages)")

    # Record the newest processed timestamp for --advance.
    max_ts = max(m.ts for m in new)
    MAX_TS_MARKER.write_text(max_ts.isoformat(), encoding="utf-8")

    print()
    print("Next: summarize raw/pending/*.txt into YYYY-MM.md / .en.md,")
    print("then run:  python scripts/parse_kakao.py --advance")
    return 0


def cmd_advance() -> int:
    if not MAX_TS_MARKER.exists():
        print("[error] no pending run found. Run a parse first.", file=sys.stderr)
        return 1
    max_ts = datetime.fromisoformat(MAX_TS_MARKER.read_text(encoding="utf-8").strip())
    save_state(max_ts)
    # Clear pending chunks + marker.
    for f in PENDING_DIR.glob("*.txt"):
        f.unlink()
    MAX_TS_MARKER.unlink()
    print(f"state advanced to {max_ts:%Y-%m-%d %H:%M}. pending cleared.")
    return 0


def main() -> int:
    # Windows consoles default to cp949; force UTF-8 so Korean / arrows print.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("txt", nargs="?", default="KakaoTalkChats.txt",
                    help="path to the KakaoTalk export .txt (default: KakaoTalkChats.txt)")
    ap.add_argument("--advance", action="store_true",
                    help="advance state to the last parsed run and clear pending")
    ap.add_argument("--since", metavar="YYYY-MM-DD",
                    help="override cutoff; ignore saved state for this run")
    ap.add_argument("--all", action="store_true",
                    help="emit everything (ignore state)")
    args = ap.parse_args()

    if args.advance:
        return cmd_advance()

    since = None
    if args.all:
        since = None
    elif args.since:
        since = datetime.fromisoformat(args.since)

    # --all forces cutoff to None explicitly (parse() default reads state).
    if args.all:
        return cmd_parse(Path(args.txt), since=datetime.min)
    return cmd_parse(Path(args.txt), since=since)


if __name__ == "__main__":
    raise SystemExit(main())
