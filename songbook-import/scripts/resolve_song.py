#!/usr/bin/env python3
"""Resolve songbook frontmatter from a lyrics URL, using MusicBrainz only.

Why this exists: the lyrics sites Bobby links to (azlyrics.com, genius.com) both
block Claude's fetcher, so the page behind the URL can never be read. That turns
out fine -- the URL is only needed as an *identifier*. This script treats the URL
slug as the identity of the song and resolves the real metadata (title, artist,
year, album, writer) from MusicBrainz, an open music database with a public API.

The hard part is that azlyrics squashes slugs with no word boundaries
("alifeofsundays"). There is no way to segment that reliably in isolation, so
instead we browse every recording MusicBrainz has for the artist, normalise each
candidate title down to bare lowercase letters and digits, and look for an exact
match. "A Life of Sundays" -> "alifeofsundays" matches, unambiguously.

Usage:
    python resolve_song.py URL [URL ...]        # resolve one or more URLs
    python resolve_song.py --csv inventory.csv  # resolve every CSV row not yet
                                                # marked Completed = Y
    python resolve_song.py --csv inventory.csv --artist "Van Morrison" URL
                                                # re-resolve one row, keeping
                                                # its note from the CSV

Prints a JSON array to stdout, one object per URL. Every object has a "status"
of "resolved", "partial", or "unresolved" -- never guess past what it reports.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from inventory import read_inventory

MB = "https://musicbrainz.org/ws/2"
# MusicBrainz requires a descriptive User-Agent with contact info, and allows at
# most one request per second. Exceeding either gets the caller blocked, so the
# throttle below is not optional politeness -- it keeps the skill working.
UA = "weelyrics-songbook-import/1.0 (https://github.com/weebaruto/weelyrics)"
RATE_LIMIT_SECONDS = 1.1
_last_request = [0.0]

CACHE_DIR = os.path.join(
    os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp",
    "songbook-import-cache",
)


def normalise(text):
    """Reduce a title to bare lowercase alphanumerics for slug comparison.

    Accents are folded and punctuation dropped, because the lyrics-site slug has
    already thrown all of that away: "Don't Bang the Drum" -> "dontbangthedrum".
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def get(path, **params):
    """GET a MusicBrainz endpoint as JSON, respecting the 1 req/sec limit.

    MusicBrainz answers 503 when it is busy or when a caller has been going too
    fast. That is a "come back shortly", not a real failure, so back off and
    retry rather than losing the row -- a whole batch can otherwise fail
    halfway through and leave the import half-done.
    """
    params["fmt"] = "json"
    url = f"{MB}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})

    delay = 2.0
    for attempt in range(5):
        elapsed = time.time() - _last_request[0]
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == 4:
                raise
            time.sleep(delay)
            delay *= 2
        finally:
            _last_request[0] = time.time()
    raise RuntimeError("unreachable")


# --- URL parsing ------------------------------------------------------------
# Each supported host encodes artist and song differently. We extract whatever
# the host gives us; the matching stage tolerates the differences.

def parse_url(url):
    """Return {source, artist_hint, song_slug} or None if the host is unknown."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [p for p in parsed.path.split("/") if p]

    if host == "azlyrics.com" and len(parts) >= 3 and parts[0] == "lyrics":
        # /lyrics/waterboys/alifeofsundays.html -- both slugs are squashed.
        return {
            "source": "azlyrics",
            "artist_hint": parts[1],
            "song_slug": normalise(parts[2].removesuffix(".html")),
        }

    if host == "genius.com" and parts and parts[-1].endswith("-lyrics"):
        # /The-waterboys-a-life-of-sundays-lyrics -- artist and title run
        # together, but unlike azlyrics the words are still separated. Keep the
        # tokens: where the artist ends and the title begins is unknown, and
        # trying each split point is far more reliable than guessing.
        return {
            "source": "genius",
            "artist_hint": None,
            "song_slug": normalise(parts[-1].removesuffix("-lyrics")),
            "tokens": parts[-1].removesuffix("-lyrics").split("-"),
            "combined": True,
        }

    return {"source": host or "unknown", "artist_hint": None, "song_slug": None}


# --- MusicBrainz lookups ----------------------------------------------------

def find_artist(hint):
    """Search MusicBrainz for an artist by squashed slug, e.g. "waterboys"."""
    if not hint:
        return None
    target = normalise(hint)
    data = get("artist/", query=f'artist:"{hint}"', limit=10)
    candidates = data.get("artists", [])
    # Prefer a name (or alias) that normalises to exactly the slug -- "waterboys"
    # should find "The Waterboys" rather than some higher-scoring near-miss.
    for artist in candidates:
        names = [artist.get("name", "")] + [
            a.get("name", "") for a in artist.get("aliases") or []
        ]
        if any(normalise(n) == target for n in names):
            return artist
        if normalise(artist.get("name", "")).removeprefix("the") == target:
            return artist
    return candidates[0] if candidates else None


def split_artist_title(tokens):
    """Find where the artist ends and the song begins in a Genius slug.

    "The-waterboys-a-life-of-sundays" could split after any token, so try each
    plausible split: take the first k words as an artist name, and accept the
    split only if that artist exists *and* has a recording matching the rest.
    Both halves having to agree is what makes this reliable -- a wrong split
    fails the artist lookup or the title match, rarely both by coincidence.
    Two-word names are tried first because "The X" is the common shape.
    """
    for k in (2, 1, 3, 4):
        if k >= len(tokens):
            continue
        artist = find_artist(" ".join(tokens[:k]))
        if not artist:
            continue
        title = match_title(artist_recordings(artist["id"]), normalise("".join(tokens[k:])))
        if title:
            return artist, title
    return None, None


def artist_recordings(mbid):
    """All recording titles for an artist, cached on disk (browse is paged)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"recordings-{mbid}.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as handle:
            return json.load(handle)

    recordings, offset = [], 0
    while True:
        page = get("recording", artist=mbid, limit=100, offset=offset)
        batch = page.get("recordings", [])
        recordings.extend({"id": r["id"], "title": r["title"]} for r in batch)
        offset += len(batch)
        if not batch or offset >= page.get("recording-count", 0):
            break
    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(recordings, handle)
    return recordings


def match_title(recordings, song_slug, combined=False):
    """Find the canonical song title whose normalised form matches the slug."""
    exact = [r for r in recordings if normalise(r["title"]) == song_slug]
    if exact:
        return exact[0]["title"]
    if combined:
        # Genius slugs bundle artist and title, so the title is a suffix of the
        # slug. Longest match wins: it is the most specific title that fits.
        suffix = [r for r in recordings if song_slug.endswith(normalise(r["title"]))]
        if suffix:
            return max(suffix, key=lambda r: len(normalise(r["title"])))["title"]
    return None


def album_rank(album):
    """Order releases by how well they represent 'the album this song is on'.

    A title like "Open" can match a dozen recordings -- the studio cut, a live
    album, a BBC compilation, a radio session. The answer a listener would give
    is the studio album, so that tier comes first; a single or EP (often the
    first outing for a song) comes next, then live albums, then compilations and
    loose sessions. Within a tier the earliest official release wins, which skips
    later reissues and deluxe editions that merely happen to carry the track.
    """
    primary = album.get("primary_type")
    secondary = album.get("secondary_types") or []
    if primary == "Album" and not secondary:
        tier = 0
    elif primary in ("EP", "Single") and not secondary:
        tier = 1
    elif "Live" in secondary:
        tier = 2
    elif "Compilation" in secondary:
        tier = 3
    else:
        tier = 4
    return (tier, 0 if album.get("status") == "Official" else 1, album.get("date") or "9999")


def rank_candidates(artist_mbid, title):
    """All recordings of `title` by this artist, best release first.

    Uses the search endpoint because it returns each recording's releases inline
    -- one request instead of a detail fetch per candidate, which matters under
    the one-request-per-second limit.
    """
    # Page through every hit: a well-known song has dozens of live takes and
    # compilation appearances, and the studio recording is often not in the
    # first page -- stopping early is how "The Whole of the Moon" ended up
    # credited to a 2005 live album.
    query = f'arid:{artist_mbid} AND recording:"{title}"'
    recordings, offset = [], 0
    while True:
        page = get("recording/", query=query, limit=100, offset=offset)
        batch = page.get("recordings", [])
        recordings.extend(batch)
        offset += len(batch)
        if not batch or offset >= page.get("count", 0):
            break
    target = normalise(title)
    candidates = []
    for recording in recordings:
        if normalise(recording["title"]) != target:
            continue
        albums = []
        for release in recording.get("releases", []):
            group = release.get("release-group") or {}
            albums.append(
                {
                    "title": release.get("title"),
                    "date": release.get("date") or group.get("first-release-date") or "",
                    "primary_type": group.get("primary-type"),
                    "secondary_types": group.get("secondary-types") or [],
                    "status": release.get("status"),
                }
            )
        if not albums:
            continue
        best = sorted(albums, key=album_rank)[0]
        if not best["date"]:
            best = dict(best, date=recording.get("first-release-date") or "")
        candidates.append(
            {"id": recording["id"], "title": recording["title"], "album": best, "albums": albums}
        )
    candidates.sort(key=lambda c: album_rank(c["album"]))
    return candidates


def credits_from_work(work_mbid):
    """Composer/lyricist names attached to a MusicBrainz work."""
    detail = get(f"work/{work_mbid}", inc="artist-rels")
    writers = []
    for rel in detail.get("relations", []):
        artist = rel.get("artist")
        if artist and rel.get("type") in ("composer", "lyricist", "writer"):
            if artist["name"] not in writers:
                writers.append(artist["name"])
    return writers


def writers_for(recording_mbid):
    """Songwriter credits, via the recording's linked work."""
    data = get(f"recording/{recording_mbid}", inc="work-rels")
    writers = []
    for relation in data.get("relations", []):
        work = relation.get("work")
        if work:
            writers.extend(w for w in credits_from_work(work["id"]) if w not in writers)
    return writers


def writers_by_title(artist_mbid, title):
    """Fallback: find the work by name when no recording links to one.

    Live and session recordings are often left unlinked in MusicBrainz even
    though the song's work exists with full credits, so searching for the work
    directly rescues credits that the recording route misses.
    """
    data = get("work/", query=f'work:"{title}" AND arid:{artist_mbid}', limit=5)
    target = normalise(title)
    for work in data.get("works", []):
        if normalise(work.get("title", "")) == target:
            writers = credits_from_work(work["id"])
            if writers:
                return writers
    return []


def resolve(url, note="", artist_override=None):
    """Resolve one URL into songbook frontmatter fields.

    `artist_override` exists because azlyrics squashes the artist name into an
    unsegmented slug ("vanmorrison"), and no MusicBrainz query can split that
    back apart -- but a reader can, instantly. When the script reports it cannot
    find the artist, the caller supplies the real name and re-runs.
    """
    result = {
        "url": url,
        "note": note,
        "status": "unresolved",
        "title": None,
        "artist": None,
        "year": None,
        "album": None,
        "writer": None,
        "unconfirmed": [],
        "album_candidates": [],
        "source": None,
        "reason": None,
    }

    parsed = parse_url(url)
    result["source"] = parsed["source"]
    if artist_override and parsed["song_slug"]:
        parsed["artist_hint"] = artist_override
    if not parsed["song_slug"]:
        result["reason"] = (
            f"Unsupported host '{parsed['source']}' -- cannot derive the song "
            "from this URL. Needs the title and artist supplied by hand."
        )
        return result

    try:
        if parsed["artist_hint"]:
            artist = find_artist(parsed["artist_hint"])
            if not artist:
                result["reason"] = (
                    f"No MusicBrainz artist matched '{parsed['artist_hint']}'. "
                    "If that is a squashed multi-word name, re-run with "
                    "--artist \"Proper Name\"."
                )
                return result
            result["artist"] = artist["name"]
            title = match_title(
                artist_recordings(artist["id"]),
                parsed["song_slug"],
                combined=parsed.get("combined", False),
            )
            if not title:
                result["reason"] = (
                    f"No recording by {artist['name']} normalises to "
                    f"'{parsed['song_slug']}'."
                )
                return result
        elif parsed.get("tokens"):
            artist, title = split_artist_title(parsed["tokens"])
            if not artist:
                result["reason"] = (
                    f"Could not split artist from title in '{parsed['song_slug']}'. "
                    'Re-run with --artist "Proper Name".'
                )
                return result
            result["artist"] = artist["name"]
        else:
            result["reason"] = f"No way to identify the song in '{parsed['song_slug']}'."
            return result

        result["title"] = title
        candidates = rank_candidates(artist["id"], title)
        if candidates:
            best = candidates[0]
            result["album"] = best["album"]["title"]
            if best["album"]["date"]:
                result["year"] = int(best["album"]["date"][:4])
            # Show the runners-up so the approval table can expose the choice
            # rather than hiding it -- "which album" is often a judgement call.
            result["album_candidates"] = [
                {"title": c["album"]["title"], "date": c["album"]["date"]}
                for c in candidates[:5]
            ]
            # A live take often has no work attached while the studio cut does,
            # so fall through the ranked candidates until a credit turns up.
            for candidate in candidates[:3]:
                writers = writers_for(candidate["id"])
                if writers:
                    result["writer"] = ", ".join(writers)
                    break
            if not result["writer"]:
                writers = writers_by_title(artist["id"], title)
                if writers:
                    result["writer"] = ", ".join(writers)

        for field in ("year", "album", "writer"):
            if not result[field]:
                result["unconfirmed"].append(field)
        result["status"] = "partial" if result["unconfirmed"] else "resolved"

    except urllib.error.HTTPError as error:
        result["reason"] = f"MusicBrainz returned HTTP {error.code}."
    except Exception as error:  # noqa: BLE001 - report, never crash the batch
        result["reason"] = f"{type(error).__name__}: {error}"

    return result


def main():
    # Notes carry curly apostrophes and accented names; on Windows stdout
    # defaults to cp1252 and redirecting the JSON to a file would fail on them.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="lyrics URLs to resolve")
    parser.add_argument("--csv", help="inventory CSV (url, note, completed); rows marked Y are skipped")
    parser.add_argument(
        "--artist",
        help='real artist name, when the URL slug is squashed (e.g. "Van Morrison")',
    )
    args = parser.parse_args()

    pairs, skipped = read_inventory(args.csv) if args.csv else ([], 0)
    if args.csv and args.urls:
        # Re-resolving a few rows (typically with --artist): take their notes
        # from the CSV rather than dropping them, and resolve only those rows.
        notes = dict(pairs)
        pairs = [(u, notes.get(u, "")) for u in args.urls]
    elif args.csv:
        # stderr, so the JSON on stdout stays clean for redirecting.
        print(f"{len(pairs)} pending, {skipped} already completed (skipped)", file=sys.stderr)
    else:
        pairs = [(u, "") for u in args.urls]
    if not pairs:
        if args.csv:
            print("[]")
            return
        parser.error("give at least one URL or --csv")

    results = [resolve(url, note, args.artist) for url, note in pairs]
    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
