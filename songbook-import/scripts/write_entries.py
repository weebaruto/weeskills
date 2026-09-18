#!/usr/bin/env python3
"""Plan and write songbook entries, then mark them completed in the CSV.

Reads a JSON array of song entries (the output of resolve_song.py, optionally
with tags added and fields corrected). There is no duplicate detection: the
inventory CSV's Completed column decides what is new, because resolve_song.py
only emits rows not yet marked Y. Prints a plan for every entry so the approval
table can be built from real data, and only touches the disk when --write is
passed. With --csv, every entry actually written gets Completed = Y in the CSV,
so the next run skips it.

Usage:
    python write_entries.py --lyrics-dir external/lyrics < entries.json
    python write_entries.py --lyrics-dir external/lyrics --write --csv inventory.csv < entries.json
"""

import argparse
import json
import os
import re
import sys
import unicodedata

from inventory import mark_completed

STATUS_NEW = "new"
STATUS_BLOCKED = "blocked"

FIELD_ORDER = ["title", "artist", "year", "album", "writer", "tags", "geniusUrl", "note"]


def slugify(title):
    """Kebab-case filename slug, matching the repo's existing entries."""
    decomposed = unicodedata.normalize("NFKD", title or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")
    return slug or "untitled"


def existing_slugs(lyrics_dir):
    """Filenames (without .md) already in the repo, so a new file never clobbers one."""
    return {
        name[:-3]
        for name in os.listdir(lyrics_dir)
        if name.endswith(".md") and name.lower() != "readme.md"
    }


def yaml_scalar(value):
    """Quote only when a plain scalar would be misread.

    The existing entries are written plainly ("note: I should have said...") and
    matching that keeps diffs readable, but a value carrying a colon-space, a
    leading indicator character, or a quote needs wrapping or the file silently
    parses wrong.
    """
    text = str(value)
    needs_quotes = (
        not text
        or text[0] in "-?:,[]{}#&*!|>'\"%@`"
        or ": " in text
        or " #" in text
        or text != text.strip()
        or "\n" in text
    )
    if not needs_quotes:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render(entry):
    """Frontmatter-only markdown: no body, because no lyric text is ever stored."""
    lines = ["---"]
    for field in FIELD_ORDER:
        value = entry.get(field)
        if value in (None, "", []):
            continue
        if field == "tags":
            lines.append(f"tags: [{', '.join(str(t) for t in value)}]")
        elif field == "year":
            lines.append(f"year: {int(value)}")
        else:
            lines.append(f"{field}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def plan(entries, taken):
    """Give each entry a filename, or block it if it can't be written."""
    planned = []
    for entry in entries:
        row = dict(entry)
        if not entry.get("title") or not entry.get("artist"):
            row["status"] = STATUS_BLOCKED
            row["detail"] = entry.get("reason") or "Title or artist missing -- cannot import."
        else:
            slug = entry.get("slug") or slugify(entry["title"])
            if slug in taken:
                # No dedupe any more, so a clash is either the same song already
                # in the repo (should have been marked Y in the CSV) or a
                # different song with the same title -- pass "slug" to rename it.
                row["status"] = STATUS_BLOCKED
                row["detail"] = f"{slug}.md already exists -- set a different \"slug\" if this is another song."
            else:
                taken.add(slug)
                row["status"] = STATUS_NEW
                row["slug"] = slug
                row["file"] = f"{slug}.md"
                row["detail"] = "New entry."
        planned.append(row)
    return planned


def main():
    # Same reason as resolve_song.py: notes contain characters cp1252 cannot
    # encode, and the JSON summary has to survive being redirected to a file.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lyrics-dir", required=True, help="path to the weelyrics checkout")
    parser.add_argument("--write", action="store_true", help="actually create the files")
    parser.add_argument("--json", help="read entries from this file instead of stdin")
    parser.add_argument(
        "--csv", help="inventory CSV: mark Completed = Y on each row written (needs --write)"
    )
    args = parser.parse_args()

    source = open(args.json, encoding="utf-8") if args.json else sys.stdin
    entries = json.load(source)
    if isinstance(entries, dict):
        entries = [entries]

    planned = plan(entries, existing_slugs(args.lyrics_dir))

    written = []
    if args.write:
        for row in planned:
            if row["status"] != STATUS_NEW:
                continue
            path = os.path.join(args.lyrics_dir, row["file"])
            # Never clobber: losing an existing entry is far worse than stopping.
            if os.path.exists(path):
                row["status"] = STATUS_BLOCKED
                row["detail"] = f"{row['file']} already exists on disk -- refusing to overwrite."
                continue
            entry = {k: row.get(k) for k in FIELD_ORDER}
            entry["geniusUrl"] = row.get("url") or row.get("geniusUrl")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(render(entry))
            written.append(row["file"])
            row["written"] = True

    marked = []
    if args.write and args.csv:
        # Only rows that really made it to disk -- a blocked row stays pending.
        marked = mark_completed(
            args.csv, [r.get("url") or r.get("geniusUrl") for r in planned if r.get("written")]
        )

    summary = {
        "written": written,
        "csv_marked": marked,
        "counts": {
            status: sum(1 for r in planned if r["status"] == status)
            for status in (STATUS_NEW, STATUS_BLOCKED)
        },
        "entries": planned,
    }
    json.dump(summary, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
