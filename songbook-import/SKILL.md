---
name: songbook-import
description: Import songs into Bobby's Songbook (the weelyrics repo behind weewebsite's /songbook section) from a CSV inventory of lyrics URLs, personal notes and a Completed flag. Use this skill whenever Bobby mentions a lyrics CSV or song inventory, wants to add songs/tracks/lyrics to the songbook or weelyrics, asks to import or ingest lyrics links, or wants the songbook submodule pointer updated — even if he doesn't say "songbook", "weelyrics", or name the skill. Trigger on things like "add the new songs from my spreadsheet", "here's my lyrics csv", "import these tracks", "update the songbook from the inventory", or "bump the lyrics submodule". It asks which CSV to use, resolves title/artist/year/album/writer from MusicBrainz (the lyrics sites themselves cannot be fetched), skips rows already marked Completed = Y, shows an approval table of every entry before touching anything, and on approval writes the frontmatter-only Markdown files, marks those CSV rows Completed = Y, commits and pushes weelyrics, then updates the submodule commit hash in weewebsite.
---

# Songbook Import

Turn a CSV inventory of lyrics links into new entries in Bobby's songbook, with the metadata filled in and the two repos left consistent.

The songbook is deliberately **metadata only**: title, artist, year, album, writer, tags, a personal note, and an outbound link to where the lyrics actually live. That design is what keeps the site clear of copyright problems, so it is a constraint to protect, not a detail. Read "The one rule" below before writing anything.

## The two repos

The content lives in its own repo, wired into the site as a git submodule:

- **`weelyrics`** — checked out at `external/lyrics/` inside the site repo. One flat `.md` file per song, containing *only* frontmatter and no body. This is where new songs go.
- **`weewebsite`** — the Docusaurus site, usually at `C:\Development\Projects\weewebsite`. It records *which commit* of weelyrics to build against. Adding songs to weelyrics changes nothing on the site until that recorded commit is moved forward — this is the "commit hash" half of the job, and forgetting it is the classic way for an import to look finished but change nothing.

An entry looks like this, and new ones should look the same:

```markdown
---
title: A Life of Sundays
artist: The Waterboys
year: 1990
album: Room to Roam
writer: Mike Scott
tags: [folk, joy]
geniusUrl: https://www.azlyrics.com/lyrics/waterboys/alifeofsundays.html
note: Fine! To be in your company. Funny! To be in your day. A miracle! Just to be with you
---
```

`geniusUrl` is a historical field name — it holds whatever lyrics URL Bobby uses, most often azlyrics.com. The file has no body at all.

## The one rule

**Never fetch lyrics, and never add lyric text of your own.** The songbook links out to a licensed lyrics site precisely so the site itself never reproduces the words. Files have no body, and the only place words from a song can appear is Bobby's `note`.

The `note` is his, and it often *is* a short quote: the line that made the song matter to him ("Fine! To be in your company…"). That's allowed. A single remembered line, chosen by him, is commentary, not a copy of the song. Store it exactly as he wrote it. What you must not do is add to it: don't expand his line into more of the verse, don't "fix" it against the real lyrics, and don't write a note for a row where he left it blank.

This is convenient as well as principled: azlyrics.com and genius.com both block Claude's fetcher outright, so there is no route to the page behind the URL even if you wanted one. Do not burn time trying `WebFetch`, `WebSearch`, or `curl` against those hosts. The URL is an **identifier**, and everything below is built around resolving it without reading it.

## The shape of the job

1. Ask which CSV to use.
2. Resolve the metadata of each row not yet marked Completed, from MusicBrainz.
3. Fill the gaps the script reports — artist names, missing credits, tags.
4. Show Bobby an approval table. Change nothing until he says yes.
5. Write the files and mark those rows Completed = Y in the CSV.
6. Commit and push weelyrics, then move weewebsite's submodule pointer.

## Step 1 — Ask which CSV

Ask Bobby for the CSV path rather than assuming one, but say where you'd look: `sandbox/weelyrics.csv` in the site repo is the usual one. If he names a file that doesn't exist, check the obvious neighbours (`sandbox/`, `~/Downloads`) before asking again.

The CSV has three columns, in this order: the lyrics URL, Bobby's note, and **Completed**. The usual header is `geniusurl,note,Completed`. Columns are matched by name when a header exists (a name containing "url"/"link", "note"/"comment"/"line", "complete"/"done") and by position when it doesn't.

**Completed is what decides what's new.** A row marked `Y` (any case) has already been imported and is skipped. A blank cell means it still needs importing. There is no duplicate check against the repo: the CSV is the record of what's done. That's why Step 5 marks each row `Y` as soon as its file is written, and a row left blank gets imported again on the next run. If Bobby adds a song to weelyrics by hand, its CSV row needs a `Y` too.

Locate the site repo the same way the blog skill does: a folder containing both `docusaurus.config.js` and `external/lyrics/`. Confirm the path once, briefly.

## Step 2 — Resolve the metadata

```bash
python <skill>/scripts/resolve_song.py --csv <path-to-csv>
```

This prints a JSON array, one object per **pending** row (Completed not `Y`), and a line on stderr like `3 pending, 4 already completed (skipped)`. Mention that count to Bobby. If nothing is pending it prints `[]`; say so and stop. It parses artist and song out of the URL slug, then resolves the real metadata from **MusicBrainz**, an open music database with a free API. Each row comes back with a `status`:

- **`resolved`** — title, artist, year, album and writer all found.
- **`partial`** — the song was identified but some fields are missing; they are listed in `unconfirmed`.
- **`unresolved`** — the song could not be identified at all; `reason` says why.

Two things about it are worth understanding, because they shape what you do next.

**Why it browses the artist's whole catalogue.** azlyrics squashes slugs to bare letters — `alifeofsundays` — and nothing can segment that in isolation. So the script fetches every recording MusicBrainz has for the artist, strips each title down to bare letters, and looks for an exact match. `A Life of Sundays` → `alifeofsundays`, unambiguous. The catalogue is cached per artist, so the first song by an artist is slow (a few seconds; MusicBrainz permits one request per second) and the rest are quick. A batch of songs by one artist is much cheaper than the same number spread across many.

**Why it sometimes picks an album you wouldn't.** A title like `Open` matches a dozen recordings — the album cut, a live take, a BBC compilation, a radio session. The script reads every matching recording (a famous song can have 70+, and the studio cut is often not on the first page). It then prefers a studio album, then a single or EP, then a live album, then compilations, and the earliest official release within that tier, which skips later reissues. A song that only ever came out live, like The Waterboys' "Open" on *Karma to Burn*, rightly gets its live album. It gets this right most of the time, but "which album is this song *from*" is genuinely a judgement call, so the runners-up come back in `album_candidates`. If a year or album looks off to you, say so in the table rather than quietly accepting it.

## Step 3 — Fill the gaps

Take the script's output and close the gaps before showing Bobby anything. There are three kinds.

**A squashed artist name.** `No MusicBrainz artist matched 'vanmorrison'` means the slug is a multi-word name with the spaces stripped. You can read it instantly where a database lookup cannot — re-run that one URL with the name supplied:

```bash
python <skill>/scripts/resolve_song.py --csv <path-to-csv> --artist "Van Morrison" "https://www.azlyrics.com/lyrics/vanmorrison/intothemystic.html"
```

Keep the `--csv`. With it, the re-run resolves just the URLs you name and carries each note across from the CSV. Without it, the note comes back empty, and a silently lost note is easy to miss in the table.

That is what the override is for; use it freely. If you genuinely can't tell whose song it is, leave the row unresolved and let the table say so.

**A missing credit.** `writer` is the field MusicBrainz most often lacks, especially for live recordings. A web search usually settles it in one go (`"<song>" "<artist>" songwriter`), and Wikipedia is generally reliable here. If a search doesn't confirm it, leave the field empty and mark it unconfirmed in the table — a wrong credit is worse than an absent one, and the frontmatter is happy without it.

**Tags.** These are curatorial and the script does not attempt them. The existing vocabulary is small and worth reusing so the songbook's tag filter stays meaningful rather than sprouting a tag per song:

> folk · americana · jazz · standard · comfort · joy · hope · regret · live

The pattern is one tag for the *kind* of music and one for the *feeling*. The feeling is usually sitting right there in Bobby's note — "I should have said I love you, I couldn't find a way" is `regret`. Propose tags, show them in the table, and let him overrule you; reach for a new tag only when nothing existing fits. Read the current entries in `external/lyrics/` first if you're unsure what's in use.

**Non-lyrics-site URLs.** Some rows point at an artist's own site rather than a lyrics host, and the script can't parse those. Identify the song yourself from the URL and any context in the note, then resolve it with `--artist` and the title, or ask Bobby which song it is.

## Step 4 — The approval table

Save the entries, with your tags and corrections merged in, as JSON **next to the CSV**, named after it (for `sandbox/weelyrics.csv`, use `sandbox/weelyrics.entries.json`). A fixed name in a shared temp folder can be overwritten by another session, which means writing the wrong songs. The CSV's own folder belongs to this repo and is already out of git. Keep each entry's `url` exactly as it appears in the CSV: that's how Step 5 finds the row to mark. This applies to hand-built entries too.

```bash
python <skill>/scripts/write_entries.py --lyrics-dir external/lyrics --json <entries.json>
```

Without `--write` this touches nothing; it only reports what *would* happen. Every entry comes back as one of:

- **`new`**: will become `<slug>.md`.
- **`blocked`**: can't be imported. Say why. Most often, title or artist is unresolved, or `<slug>.md` already exists. A filename clash means one of two things. The song may already be in the songbook with its CSV row never marked `Y`: tell Bobby, and mark the row rather than importing it:

  ```bash
  python <skill>/scripts/inventory.py --csv <path-to-csv> --mark "<url>"
  ```

  Or it's a different song with the same title: add a `"slug"` field (e.g. `"open-foy-vance"`) to that entry and re-run.

Then show Bobby a table — every entry, one row each, with the status plainly visible:

| # | Status | Title | Artist | Year | Album | Writer | Tags | Note |
|---|--------|-------|--------|------|-------|--------|------|------|

Mark anything unconfirmed so it's obvious at a glance (an empty cell plus a footnote reads better than a confident guess). Put the `new` rows first, since those are the ones he's actually deciding on. Summarise the rest in a line underneath: how many rows were skipped as already completed, and how many are blocked and why.

Then stop and ask. **Nothing is written, committed, or pushed before he approves.** The approval is the point where he catches a wrong album or a tag he doesn't like, and after the push those mistakes are public. Expect him to correct a few cells; apply the corrections and re-show the table rather than pressing on.

If he has explicitly approved in advance ("consider the table approved", "just do it"), go straight on, but still put the table in your final message so he can review what went in.

## Step 5 — Write the files

On approval:

```bash
python <skill>/scripts/write_entries.py --lyrics-dir external/lyrics --json <entries.json> --write --csv <path-to-csv>
```

Only `new` rows are written, and the script refuses to overwrite an existing file. With `--csv`, every row whose file was actually written gets `Y` in its Completed column. The CSV keeps its encoding and line endings, so it still opens cleanly in Excel. A Completed header is added if missing. Blocked rows stay blank so they come up again next time. Check that `csv_marked` in the output matches `written`. A URL missing from `csv_marked` means the entry's `url` didn't match the CSV cell. Fix it and mark that row by hand. It handles the frontmatter quoting, which is fiddlier than it looks — notes carry apostrophes, colons and quotation marks, and a naively written note silently breaks the whole entry. Don't hand-write these files.

## Step 6 — Commit both repos

Two commits, in this order, because weewebsite records a commit of weelyrics that has to exist on the remote before the site can build against it.

```bash
# 1. the content
cd external/lyrics
git add <the new files>
git commit -m "Add <n> songs to the songbook"
git push

# 2. the pointer
cd <site repo>
git add external/lyrics
git commit -m "Songbook: point at <n> new songs"
```

Pushing weelyrics is not optional — an unpushed commit leaves the site repo pointing at something the build server cannot fetch, and CI fails on a fresh clone.

Stop after committing the pointer. **Leave the weewebsite push to Bobby** unless he tells you otherwise: that push is what deploys the live site, and it's his call when the songs go public. Tell him plainly what's staged and what's left:

> Committed <n> songs to weelyrics and pushed. Submodule pointer committed in weewebsite but not pushed — `git push` when you want it live.

Then offer `yarn start` so he can look at `/songbook` before it ships.

## When things go sideways

**`HTTP 503` from MusicBrainz** — it's busy or you went too fast. The script already backs off and retries five times; if a whole batch still fails, wait a minute and re-run. The artist cache means the re-run is much faster.

**A song genuinely isn't in MusicBrainz.** Obscure and self-released tracks sometimes aren't. Confirm the details with a web search, then hand-build that one entry and mention in the table that its metadata came from a search rather than the database.

**Genius slugs with extra words.** Genius sometimes puts extra text in the slug (e.g. `Mike-scott-sct-sensitive-children-lyrics`), and then even `--artist` finds nothing. Look the title up on MusicBrainz directly (`/ws/2/recording?query=recording:"<title>"`) and build the entry by hand. Keep the CSV URL as `url`.

**The catalogue match finds nothing** (`No recording by X normalises to '...'`) — usually the URL slug and MusicBrainz disagree on the title (a subtitle, a bracketed suffix, "Pt. 2" vs "Part 2"). Search MusicBrainz for the artist and eyeball their track list; if you spot it, resolve it by title rather than by URL.

**The submodule looks detached.** `external/lyrics` sitting on a detached HEAD is normal for a fresh submodule checkout, but you cannot commit from there. `git -C external/lyrics checkout main` first, and make sure it's up to date before adding files.
