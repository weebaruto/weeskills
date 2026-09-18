"""Read and update Bobby's lyrics inventory CSV.

The CSV is the source of truth for what still needs importing. Its third column,
"Completed", is marked Y once a song has been written to weelyrics, so a re-run
only picks up the rows that aren't done yet -- no need to compare against the
repo to work out what is new.

Run directly to mark rows done by hand:
    python inventory.py --csv inventory.csv --mark URL [URL ...]

Columns are matched by header name when there is a header (a column containing
"url" or "link", one containing "note"/"comment"/"line", one containing
"complete"/"done"), and fall back to position otherwise: URL, note, completed.
"""

import csv

COMPLETED_MARK = "Y"


def _load(path):
    """Rows plus the file details needed to write it back unchanged."""
    with open(path, "rb") as handle:
        raw = handle.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(text.splitlines()))
    return rows, bom, newline, text.endswith(("\n", "\r"))


def _columns(rows):
    """(has_header, url_index, note_index, completed_index)."""
    url_index, note_index, completed_index = 0, 1, 2
    if not rows:
        return False, url_index, note_index, completed_index
    header = [c.strip().lower() for c in rows[0]]
    has_header = any("url" in c or "link" in c for c in header)
    if has_header:
        for i, name in enumerate(header):
            if "url" in name or "link" in name:
                url_index = i
            elif "complete" in name or "done" in name:
                completed_index = i
            elif "note" in name or "comment" in name or "line" in name:
                note_index = i
    return has_header, url_index, note_index, completed_index


def _cell(row, index):
    return row[index].strip() if len(row) > index else ""


def is_completed(value):
    return value.strip().upper() == COMPLETED_MARK


def read_inventory(path):
    """Return (pending, skipped): (url, note) pairs still to import, and the
    number of rows already marked completed."""
    rows, _, _, _ = _load(path)
    has_header, url_i, note_i, done_i = _columns(rows)
    if has_header:
        rows = rows[1:]
    pending, skipped = [], 0
    for row in rows:
        url = _cell(row, url_i)
        if not url:
            continue
        if is_completed(_cell(row, done_i)):
            skipped += 1
            continue
        pending.append((url, _cell(row, note_i)))
    return pending, skipped


def mark_completed(path, urls):
    """Set the completed column to Y on every row whose URL is in `urls`.

    Rewrites the file keeping its encoding (BOM or not) and line endings, so it
    still opens cleanly in Excel. Returns the URLs that were marked; any URL not
    found in the CSV is simply not in the result.
    """
    wanted = {u.strip() for u in urls if u}
    if not wanted:
        return []
    rows, bom, newline, trailing = _load(path)
    has_header, url_i, _, done_i = _columns(rows)

    if has_header and len(rows[0]) <= done_i:
        rows[0] += [""] * (done_i - len(rows[0])) + ["Completed"]

    marked = []
    for row in rows[1:] if has_header else rows:
        url = _cell(row, url_i)
        if url in wanted:
            if len(row) <= done_i:
                row += [""] * (done_i + 1 - len(row))
            row[done_i] = COMPLETED_MARK
            marked.append(url)

    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator=newline)
        writer.writerows(rows)
    if not trailing:
        # Match the original: no newline after the last row.
        with open(path, "rb+") as handle:
            handle.seek(-len(newline.encode()), 2)
            handle.truncate()
    return marked


def main():
    """Mark rows done by hand -- e.g. a song that turned out to be in the
    songbook already, so the next run stops offering it."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--csv", required=True, help="inventory CSV")
    parser.add_argument("--mark", nargs="+", required=True, metavar="URL", help="URLs to mark Completed = Y")
    args = parser.parse_args()
    marked = mark_completed(args.csv, args.mark)
    for url in args.mark:
        print(("marked   " if url.strip() in marked else "NOT FOUND ") + url)


if __name__ == "__main__":
    main()
