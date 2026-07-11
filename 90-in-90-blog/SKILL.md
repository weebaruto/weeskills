---
name: 90-in-90-blog
description: Write a new 90-IN-90 blog post for Bobby Mawhinney's personal Docusaurus site (weewebsite / "Being Bobby") in his own voice. Use this skill whenever Bobby wants to write, draft, create, or publish a blog post, journal entry, reflection, or "90-in-90" entry for his website — even if he doesn't say the words "90-in-90" or "blog." Trigger on things like "write up my day," "I want to post about X," "new entry for the site," "draft a reflection on this carafe I found," or "add a post about today's sumo." The skill interviews Bobby for the day's context, any sources to link, and any images to include, then writes a polished, ready-to-publish Markdown post in the exact Docusaurus format and saves it into his local weewebsite clone.
---

# 90-IN-90 Blog Post Writer

Write a new blog post for Bobby's personal site in *his* voice, in the exact format his Docusaurus blog expects, and save it into his local repo ready to preview and commit.

"90-in-90" is Bobby's project: committing to something for 90 days and seeing where it takes you — a reset, part adventure. The blog documents that journey. In practice the posts are short, warm, reflective pieces built around one concrete object or moment. See `references/voice-guide.md` for how they read — **read it before writing a single line.**

## The shape of the job

1. Locate the `weewebsite` repo.
2. Interview Bobby for the seed: the context/experience, any sources, any images.
3. Read the voice guide and one or two recent posts to warm up on the voice.
4. Write the post — polished and ready to publish.
5. Place any images and wire up the Markdown.
6. Save the file with the right filename, and offer to preview.

Do these in order, but stay conversational — this is ghostwriting, not a form to fill in.

## Step 1 — Find the repo

The post is a Markdown file in the `blog/` folder of Bobby's `weewebsite` repo (a Docusaurus site). Locate the repo root by looking for a folder that contains **both** `docusaurus.config.js` and `blog/authors.yml`:

- If the current working directory is inside it, use that.
- Otherwise check `C:\Development\Projects\weewebsite` (Bobby's usual clone).
- If still not found, ask Bobby for the path. Don't guess or write files to the wrong place.

Confirm the path with Bobby once, briefly, then proceed.

## Step 2 — Interview for the seed

The whole post grows from one real thing Bobby noticed. Draw it out — don't invent it. Ask conversationally, batching questions so it feels like a chat, not an interrogation. You're listening for:

- **The centre.** What's the one object, moment, or thing at the heart of this? (A carafe. An AI agent. A sumo bout. A record he put on.) His posts always orbit something concrete.
- **What happened.** The little story or observation. Where he was, what he saw, what he did.
- **Why it stuck.** The turn — what it made him think or feel, or what it's secretly about. Sometimes there's a lesson; often it's just a resonance. Don't force a moral.
- **Threads to weave in.** Any personal detail (his daughter, old friends, work life) or cultural thread (sumo, vinyl, Japanese phrases, ikigai) that belongs here. Only if it's genuinely part of the story — never bolted on.

**Sources.** Ask for any links he wants dropped in — a product page, an article, an awards site. His posts link out inline to real things (`[Red Dot Design Awards](https://www.red-dot.org/)`). Note them and where they naturally belong.

**Images.** Ask whether he has any images to include and where the files are. He provides the files; you place them (Step 5). Ask for a one-line caption if he wants one — his image captions are often a warm aside (e.g. a dedication to old friends).

If Bobby hands you a rich brain-dump up front, don't re-interrogate — just fill the genuine gaps with one or two targeted questions.

## Step 3 — Warm up on the voice

Read `references/voice-guide.md` in full. Then skim the two or three most recent posts in `blog/` (sort by filename date) to catch the current register. The voice drifts a little over time; the newest posts are the truest north.

## Step 4 — Write the post

Follow the voice guide. The non-negotiables, in short:

- **One thread, all the way through.** The concrete thing carries the whole piece; the reflection is earned through it, never abstract for its own sake.
- **His register.** First person, conversational, British-inflected, self-deprecating and warm. Short punchy sentences played against long comma-spilling ones. Real, specific detail and names.
- **A teaser that stands alone.** The first paragraph appears on the blog index before the `<!-- truncate -->` cut — it has to hook on its own.
- **Land on a kicker.** End on a short, resonant standalone line that recasts the piece, often echoing an image from earlier. Suggest, don't summarise.
- **Length:** ~400–700 words (a 2–3 minute read). Flowing prose — **no headings, no bullet lists inside the post.**

Avoid the generic-AI tells the voice guide calls out (em-dash overload, tidy tricolons, "it's not X, it's Y," LinkedIn tone, a conclusion that restates the point). This is the part that most often goes wrong — trust the voice guide over your defaults.

Propose a **title** (Title Case, evocative and often oblique — "Enjoy The Slowness," "Waste Not, Want Not" — rarely a literal label) and a short **slug** in his style (`the-carafe`, `the-quiet-part` — evocative, and it needn't match the title). Show Bobby the draft and let him steer before you save.

## Step 5 — Images

For each image Bobby provides:

1. Copy the file into `static/img/` in the repo (keep or give it a short, sensible name, e.g. `jar.png`).
2. Reference it in the body with centred markup, sized around 420px:

   ```html
   <div class="text--center">
     <img src="/weewebsite/img/FILENAME.png" alt="DESCRIPTIVE ALT TEXT" width="420" />
   </div>
   ```

   Note the src path starts with `/weewebsite/` (the site's baseUrl), **not** `/img/` or `../static/`.
3. If Bobby wants a caption, put it centred just below:

   ```html
   <div class="text--center">Your caption here</div>
   ```

   A `<br />` between the image block and the following paragraph keeps the spacing clean.

Place images where they land naturally in the story — usually right after the moment they illustrate — not clustered at the top.

## Step 6 — Save the file

- **Filename:** `blog/YYYY-MM-DD-slug.md`, where the date is the post date (default: today) and the slug is the one agreed in Step 4. Example: `blog/2026-07-11-the-quiet-part.md`.
- **Front matter** — use exactly this shape:

  ```yaml
  ---
  title: Your Title Here
  authors: [bobby]
  hide_table_of_contents: false
  ---
  ```

  `authors: [bobby]` maps to the entry in `blog/authors.yml` — don't invent a new author. Tags are optional and usually omitted; only add a `tags: [...]` line if Bobby asks.
- **Body layout:**

  ```markdown
  ---
  title: ...
  authors: [bobby]
  hide_table_of_contents: false
  ---

  <opening teaser paragraph — hooks on its own>

  <!-- truncate -->

  <the rest of the post>

  <the kicker line>
  ```

  The `<!-- truncate -->` marker is required — it's the "read more" cut on the index page. Put it after the opening teaser, before the body.

After saving, tell Bobby the file path and offer to preview locally (`yarn start` / `npm run start` in the repo, which opens the dev server) or to open the file. Don't commit or push unless he asks.

## Full worked example

A finished file looks exactly like this (from `blog/2026-06-26-the-carafe.md`):

```markdown
---
title: Waste Not, Want Not
authors: [bobby]
hide_table_of_contents: false
---

Down the [Red Dot Design Awards](https://www.red-dot.org/) rabbit hole again. You know the one. "Five minutes," you tell yourself. Next thing, the coffee's gone cold and you couldn't care less.

<!-- truncate -->

My daughter turned 25 this year, an interior designer at IKEA, buying her a present is basically a competitive sport now, she knows her stuff. No pressure, Bobby!

Then I found [this](https://www.red-dot.org/project/sonnenglasr-light-carafe-82761). Nothing served it up. No feed, no "you might also like". I went looking, and there it was.

<div class="text--center">
  <img src="/weewebsite/img/jar.png" alt="The carafe glowing on a table" width="420" />
</div>

<br />
The Sonnenglas Light Carafe. Hand-blown from old bottles collected off the streets of Eswatini... [body continues]

What I want, for the stuff I build and, if I'm honest, the way I'm trying to live, is exactly that. Does the job. Does it beautifully. Then stops.

She opened it. "Oh, this is really cool." Interior designer approved. Job done!

...

The carafe is rare.
```

Notice: one object (the carafe) threaded throughout, a real link, a real person (his daughter), a centred image dropped where it belongs, and a three-word kicker that lands the whole thing.
