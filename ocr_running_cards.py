"""
ocr_running_cards.py — Convert all running_cards/*.png to a single
running_cards.json file using Claude Haiku 4.7 vision.

Output schema (per box):
{
  "BOX_NO": {
    "location": "BELGRADE & COLBERG AVS",
    "district": 10,
    "division": 2,
    "respond": {
      "1st": {"engines": ["E30","E53","E55"], "rit": "E28-RIT",
              "ladders": ["L25","L16"], "spec": ["R02"], "chiefs": ["D10"]},
      "ss":  {...},
      "2nd": {...}, ... "10th": {...}
    },
    "covering": {
      "1st": {"engines": [...], "ladders": [...]}, ...
    }
  }
}

Resumable: writes one JSONL row per card to ocr_progress.jsonl as it goes;
already-processed boxes are skipped. Final consolidation step merges JSONL
into running_cards.json (and gz).

Run: python ocr_running_cards.py [--limit N] [--concurrency 10]
"""
import argparse
import asyncio
import base64
import gzip
import json
import os
import re
import sys
from pathlib import Path

from anthropic import AsyncAnthropic

CARDS_DIR = Path("running_cards")
PROGRESS = Path("ocr_progress.jsonl")
OUTPUT_JSON = Path("running_cards.json")
OUTPUT_GZ = Path("running_cards.json.gz")
MODEL = "claude-haiku-4-5"  # fast + cheap; bump to sonnet if accuracy issues

PROMPT = """Extract the data from this Boston Fire Department running card image and return ONLY valid JSON. No prose, no code fences.

Schema:
{
  "location": "string (e.g. 'BELGRADE & COLBERG AVS')",
  "district": integer or null,
  "division": integer or null,
  "respond": {
    "1st":  {"engines": [...], "rit": "string or null", "ladders": [...], "spec": [...], "chiefs": [...]},
    "ss":   {"engines": [...], "rit": "string or null", "ladders": [...], "spec": [...], "chiefs": [...]},
    "2nd":  {...},
    "3rd":  {...},
    "4th":  {...},
    "5th":  {...},
    "6th":  {...},
    "7th":  {...},
    "8th":  {...},
    "9th":  {...},
    "10th": {...}
  },
  "covering": {
    "1st":  {"engines": [...], "ladders": [...]},
    ... (same alarm levels)
  }
}

Rules:
- "engines" / "ladders" / "spec" / "chiefs" are arrays of company codes (e.g. "E30", "L25", "R02", "D10"). Empty array if cell is blank.
- "rit" is the single RIT engine if present (e.g. "E28-RIT"). null if no RIT marker.
- Codes use letter prefix + number, no spaces (E30 not "E 30"). Preserve any suffix like -RIT.
- The covering side may have ">" arrow notation (e.g. "E48>E30"). Keep them as-is in the array.
- Some rows may be empty — return empty arrays for those cells.
- Output JSON only. No markdown, no explanation."""


def encode_image(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


def already_processed() -> set:
    done = set()
    if PROGRESS.exists():
        for line in PROGRESS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("box"):
                    done.add(rec["box"])
            except json.JSONDecodeError:
                continue
    return done


def extract_json(text: str) -> dict:
    """Robust JSON extraction from model output."""
    text = text.strip()
    # Strip code fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError(f"No JSON found in: {text[:200]!r}")


async def ocr_one(client: AsyncAnthropic, sem: asyncio.Semaphore, path: Path):
    box = path.stem
    async with sem:
        try:
            img_b64 = encode_image(path)
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                        {"type": "text", "text": PROMPT},
                    ],
                }],
            )
            raw = resp.content[0].text
            data = extract_json(raw)
            return {"box": box, "ok": True, "data": data}
        except Exception as e:
            return {"box": box, "ok": False, "error": str(e)[:200]}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Process at most N cards (for testing)")
    ap.add_argument("--concurrency", type=int, default=10)
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: set ANTHROPIC_API_KEY env var", file=sys.stderr)
        sys.exit(1)

    cards = sorted(CARDS_DIR.glob("*.png"))
    done = already_processed()
    todo = [p for p in cards if p.stem not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f"Total cards: {len(cards)}")
    print(f"Already done: {len(done)}")
    print(f"To process now: {len(todo)}  (concurrency={args.concurrency})")

    if not todo:
        print("Nothing to do. Run with --limit to retry, or delete ocr_progress.jsonl to start fresh.")
        consolidate()
        return

    client = AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(args.concurrency)
    progress_fp = PROGRESS.open("a", encoding="utf-8")

    completed = 0
    failed = 0
    tasks = [asyncio.create_task(ocr_one(client, sem, p)) for p in todo]
    for fut in asyncio.as_completed(tasks):
        rec = await fut
        progress_fp.write(json.dumps(rec) + "\n")
        progress_fp.flush()
        completed += 1
        if not rec["ok"]:
            failed += 1
            print(f"  FAIL {rec['box']}: {rec['error']}")
        if completed % 25 == 0:
            print(f"  ...{completed}/{len(todo)} (fails: {failed})")

    progress_fp.close()
    print(f"Done. {completed} processed, {failed} failed.")
    consolidate()


def consolidate():
    """Merge ocr_progress.jsonl → running_cards.json (only successful entries)."""
    if not PROGRESS.exists():
        print("No progress file to consolidate.")
        return
    out = {}
    fails = 0
    for line in PROGRESS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("ok"):
            out[rec["box"]] = rec["data"]
        else:
            fails += 1

    payload = json.dumps(out, separators=(",", ":"))
    OUTPUT_JSON.write_text(payload, encoding="utf-8")
    with gzip.open(OUTPUT_GZ, "wb", compresslevel=9) as f:
        f.write(payload.encode())
    print(f"Wrote {OUTPUT_JSON} ({len(out)} cards, {len(payload):,} bytes)")
    print(f"Wrote {OUTPUT_GZ} ({os.path.getsize(OUTPUT_GZ):,} bytes)")
    if fails:
        print(f"  ({fails} cards failed and are NOT in the JSON; rerun the script to retry.)")


if __name__ == "__main__":
    asyncio.run(main())
