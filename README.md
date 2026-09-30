# Social Media Data Gathering

A local app for collecting social media text for NLP research methods. It builds on
[yt-timed-text](https://github.com/kwartler/yt-timed-text) and adds TikTok, Instagram,
Facebook, Reddit, Bluesky, Truth Social, and roughly 1,700 other video sites (Rumble, BitChute,
Odysee, Dailymotion, Twitch clips, Bilibili, and more), plus an OpenRouter model step that turns video and images
into text you can analyze.

Each platform has its own tab. Paste post links (or list an account, or run a keyword
search), click **Collect**, and download a zip. **Every platform exports the same JSON
schema** (`corpus.jsonl`, defined in [`smdg/document.schema.json`](smdg/document.schema.json)),
so one ingestion step works for all of them in bag of words, syntactic parsing, or
LLM-as-a-judge work.

How text is extracted:

- **YouTube** works like yt-timed-text by default: the transcript comes from YouTube's own
  caption track through the timedtext API, and the raw timedtext JSON is included in the
  export. The YouTube tab's **Transcript source** menu can instead send the video to the
  model, or do **both** so you can compare the two transcripts on the same video.
- **TikTok, Instagram, Facebook** (and image or video posts on Reddit and Bluesky): the app
  downloads the video with its audio and sends it to an OpenRouter model, which returns the
  dialog transcript, on-screen text, and a description of the visuals.

For every post you get:

- **What the author wrote**: caption, description, post body, title.
- **What was said**: a dialog transcript, from YouTube captions or from the model. The two
  sources are kept in separate fields (`caption_transcript`, `llm_transcript`).
- **Who said it**: model transcripts label each speaker turn `A`, `B`, `C`... and describe
  each speaker ("person in red jacket facing camera", "off-screen narrator").
- **Translations** (optional): pick a language under **Translate to** and every text field
  gets a translated copy next to the original.
- **What was shown**: on-screen text and a description of the visuals, from the model.
- **Replies**: comments, with reply structure (`parent_id`), where the platform allows.
- **Provenance**: a manifest with every input, error, option, the exact model prompt, and
  the model cost.

Runs on your computer. Media is sent only to the OpenRouter model you choose, and is deleted
after extraction unless you ask to keep it.

---

## What works on each platform

| Platform | Single post | Account / community | Search | Comments | Needs |
|---|---|---|---|---|---|
| YouTube | Yes (videos, Shorts) | Channels | Yes | Yes | Nothing |
| TikTok | Yes | Profiles (best effort) | No | No | Nothing |
| Instagram | Yes (posts, reels) | No | No | Yes (a sample) | Nothing |
| Facebook | Yes (public videos) | No | No | No | Nothing |
| Bluesky | Yes | Profiles | Yes | Yes | App password for search only |
| Reddit | Yes | Subreddits, users | Yes | Yes | Free Reddit API key |
| Truth Social (see warning below) | Yes | Accounts | No | No | Nothing |
| Other video sites (Other tab) | Yes | No | No | No | Nothing |
| X/Twitter, Snapchat, Threads, LinkedIn, Vimeo, Kick | Not supported | | | | |

The **OpenRouter key** is needed only for model steps: video and image to text, and
translation. YouTube with its default caption source never needs it.

Notes:

- **Instagram and Facebook profiles** are not supported. Pulling a whole profile requires
  logging in, and this app never logs in to any platform. Paste individual post links instead.
- **TikTok profile listing** uses an extractor that breaks from time to time. If it fails,
  retry later or paste video links.
- **Instagram stories** require a login and are not supported.
- **Truth Social: terms of service warning.** Truth Social offers no research API, and its
  terms likely prohibit automated collection. Its servers reject ordinary requests, so the
  app gets through only by presenting itself as a Chrome browser. Using this tab may violate
  the platform's terms, and it can stop working at any time. Get IRB guidance before
  collecting data you plan to publish or share. The tab shows this warning at the top.
  Replies and search need a login and are not supported. Truth Social rate-limits hard, so
  the app paces requests; if you see a 429 error, wait 15 to 30 minutes.
- **Other tab.** Pick a popular site (Rumble, BitChute, Odysee, Dailymotion, Twitch clips,
  Bilibili) for example links, or choose "Any other supported site" and paste links from
  any site on yt-dlp's [full list of supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).
  The popular sites are tested; others are best effort. Paste links to individual videos
  (channel listing is not offered here). Every document records its website in the `site`
  field (for example `rumble.com`). Live streams can be collected only after they end.
  Vimeo (copy-protected) and Kick (live streams) are not supported.
- **Large videos are shrunk automatically.** Anything over 40 MB is re-encoded to 360p
  before it goes to the model, which can take a minute for long videos.
- **Instagram rate-limits logged-out access.** Large batches may start failing with a login
  message; wait 15 minutes and re-run the failed links.

---

## Install

### Easiest (recommended)

1. Go to the [Releases](../../releases) page.
2. Download the file for your platform:
   - **Mac (Apple Silicon, M1 or later):** `social-media-data-gathering-mac-arm64.zip`
   - **Windows:** `social-media-data-gathering-windows.exe`
3. **Mac:** unzip it and double-click `social-media-data-gathering.app`. A Terminal window
   opens and your browser goes to `http://127.0.0.1:8010`.
   **Windows:** double-click the `.exe`. Your browser opens to `http://127.0.0.1:8010`.

#### First-launch security warnings

The app isn't signed with a paid Apple or Microsoft certificate, so your computer warns you
the first time you open it. **Step-by-step instructions for Mac and Windows, with
troubleshooting, are in [docs/INSTALL.md](docs/INSTALL.md).** In short:

- **Mac:** click **Done** on the warning, then **System Settings > Privacy & Security >
  Open Anyway**.
- **Windows:** on the blue SmartScreen window, click **More info**, then **Run anyway**.

You only do this once per download.

### Run from source

```bash
git clone https://github.com/kwartler/social-media-data-gathering.git
cd social-media-data-gathering
pip install -r requirements.txt
python app.py
```

Running from source updates yt-dlp at every launch, which fixes most "the platform changed"
errors. The packaged app can't self-update, so download the newest release if extraction
starts failing.

---

## Set up your keys (Settings button)

Keys are saved only on your computer, in `~/.social_media_data_gathering/config.json`.
Environment variables with the same names (`OPENROUTER_API_KEY`, `REDDIT_CLIENT_ID`,
`REDDIT_CLIENT_SECRET`, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`) override the saved values.

**OpenRouter** (for video and image extraction, and translation)
1. Create an account at [openrouter.ai](https://openrouter.ai) and add a few dollars of credit.
2. Create a key under **Keys** and paste it into Settings.
3. Pick a model. Only models that accept video are listed. The default, `google/gemini-3.8-flash`,
   costs well under a cent for a short clip.

**Reddit** (required for any Reddit collection)
Reddit blocks anonymous access, so you need your own free API credentials.
1. Sign in to Reddit and go to <https://www.reddit.com/prefs/apps>.
2. Click **create another app**, choose **script**, give it a name, and set the redirect URI to
   `http://localhost:8080`.
3. Copy the client ID (under the app name) and the secret into Settings.
Reddit reviews API access under its Responsible Builder Policy; register early, and describe
your use as non-commercial academic research.

**Bluesky** (only for keyword search)
In Bluesky go to **Settings > Privacy and security > App passwords**, create one, and paste
it with your handle into Settings. Posts and profiles don't need this.

---

## Using it

Pick the tab for your platform: **YouTube, TikTok, Instagram, Facebook, Reddit, Bluesky,
Truth Social, Other**, or
**Log**. Each tab shows only what that platform supports:

- **Links:** paste post links, one per line. The app confirms what it recognized and flags
  links that belong on another tab or aren't supported.
- **Account** (YouTube, TikTok, Reddit, Bluesky, Truth Social): paste a channel, profile, subreddit
  (`r/name`), or user (`u/name`), choose how many recent posts, and uncheck any you don't want.
- **Search** (YouTube, Reddit, Bluesky): keyword or hashtag search.
- **YouTube caption language:** with one video pasted, the menu lists that video's actual
  caption languages, as in yt-timed-text.
- **Log:** every collection attempt on this computer, including failures. Re-running a link
  adds a new entry; nothing is overwritten.

Links and selected posts from the list are collected together.

Collection options:

| Option | Default | What it does |
|---|---|---|
| Extract text with the model | on | Sends each video or image set to OpenRouter for a speaker-labeled transcript, on-screen text, and visual description. On the YouTube tab this is set by Transcript source instead. |
| Comments per post | 0 | How many comments to collect per post. |
| Max video length for the model | 300 s | Longer videos are collected but not sent to the model (cost control). |
| Transcript source (YouTube) | captions | `captions` (timedtext, as in yt-timed-text), `model`, or `both`. |
| Caption language | en | Which caption track to take (YouTube and TikTok). |
| Translate to | off | Adds `translated_*` fields in this language for the title, text, transcripts, and on-screen text of every post and comment. Originals are never replaced. |
| Pseudonymize | YouTube: commenters only. Other tabs: everyone | Replaces names and @mentions with stable codes such as `u_3f9a1c02de`. **Commenters and @mentions only** keeps the accounts you chose to study (for example a news channel) and codes everyone else. **Everyone** codes post authors too. **No one** turns it off. |
| Include identifiable folder | on (off with "No one") | Adds the keys that map codes back to real names and links, plus raw platform data, in a separate `identifiable/` folder. With Pseudonymize set to "No one" there is no key, so this unchecks itself and becomes "Include raw platform data"; tick it to keep the raw data. |
| Keep downloaded media | off | Leaves the downloaded videos and images on disk instead of deleting them. |

## What's in the zip

| File | Contents |
|---|---|
| `corpus.jsonl` | One JSON document per post or comment, in the common schema, with time-stamped transcript `segments` nested inside. **Start here.** |
| `document.schema.json` | The JSON Schema every `corpus.jsonl` line follows, on every platform. |
| `corpus.csv`, `segments.csv` | The same data flattened for spreadsheets. |
| `timedtext/` | YouTube only: raw timedtext caption JSON, as yt-timed-text produced. |
| `manifest.json` | Inputs, errors, options, model prompt and version, cost. |
| `codebook.md` | Every column explained, plus measurement notes. **Read this before analysis.** |
| `identifiable/` | Linking key and raw data. Store separately from the analysis data. |

Loading any export in R is the same one line, whatever the platform:

```r
corpus <- jsonlite::stream_in(file("corpus.jsonl", encoding = "UTF-8"))
```

In Python: `pandas.read_json("corpus.jsonl", lines=True)`.

### R scripts for students

All three run from RStudio with the **Source** button and a file-picker window; no
programming needed.

| Script | What it does |
|---|---|
| `examples/restore_identities.R` | Puts real names, @mentions, and links back into a pseudonymized export, using the key in `identifiable/`. Saves `corpus_identified.csv`. Keep the output private. |
| `examples/review_sheet.R` | Picks a random sample of posts with model output and builds `review_sheet.csv` with blank columns for marking whether the transcript, speakers, on-screen text, description, and translation are right. `summarize_review()` then tallies the results for your methods section. |
| `examples/starter_analysis.R` | Runs the three course methods on an export (below). |

A typical cleanup: collect with pseudonymization on, run `restore_identities.R`, run
`review_sheet.R` on its output, check the sample by hand, and analyze the pseudonymized
`corpus.jsonl`.

`examples/starter_analysis.R` loads an export and runs all three course methods: a
document-term matrix with **tm**, dependency parsing with **udpipe**, and an **LLM-as-a-judge**
classifier through OpenRouter.

```bash
Rscript examples/starter_analysis.R ~/Downloads/social_media_corpus_XXXX.zip
```

---

## Speaker labels: how they work and their limits

The model labels speakers in the same pass that transcribes the video, using both the
voices and the picture (whose lips move, who is on camera, cuts between people). This was
chosen after comparing the options:

- **One multimodal pass (used here).** In a 2026 benchmark of speaker-attributed
  transcription, Gemini 3 Pro's word-level speaker attribution error (WDER, 33.0%) was as
  good as or better than dedicated commercial services (33 to 44%). Its time-based
  diarization error (DER, 74.0%) was much worse, mostly from missed short utterances and
  unreliable timestamps
  ([Indic DiarBench](https://arxiv.org/abs/2607.23808)). For text analysis, "which words
  did each speaker say" (WDER) is what matters, so one pass fits well. **Treat
  `start_seconds` on model segments as approximate.**
- **A second model pass to fix speakers.** LLM post-correction such as
  [DiarizationLM](https://arxiv.org/abs/2401.03506) cuts word-level speaker errors by 45 to 55%,
  but it corrects the output of a *separate* acoustic diarization system, with fine-tuned
  models. Re-running a general model on its own transcript adds no independent evidence
  and doubles the video cost, so it is not included.
- **Dedicated diarization (pyannote, AssemblyAI, and others).** Best timing accuracy
  ([pyannote benchmark](https://www.pyannote.ai/benchmark)), but not available through
  OpenRouter, and it needs a separate account or a heavy local install. Use one when
  turn timing matters, such as studies of interruptions or overlap.

Labels are per video: speaker `A` in one video is unrelated to `A` in another. The model
describes speakers but never names them unless a name is shown or spoken. Short, fast,
overlapping, or similar-sounding voices are the most common errors, so hand-check a
sample, especially with three or more speakers.

## Research ethics

This tool makes collection easy; that does not make every collection appropriate.
[`docs/ethics_speaker_notes.txt`](docs/ethics_speaker_notes.txt) has lecture notes with
discussion prompts covering the points below.

- Get IRB approval, or confirm an exemption, before collecting data for research you plan to
  publish or share.
- Collect only public content, and only what your question needs.
- Keep pseudonymization on, store the `identifiable/` folder separately, and delete data on the
  schedule your protocol sets.
- Model outputs are AI-generated and unverified. Validate a sample by hand and report the model
  and prompt version (from `manifest.json`) in your methods.
- Each platform's terms of service govern automated collection. Reddit and Bluesky provide
  official APIs for it; YouTube, TikTok, Instagram, and Facebook collection uses yt-dlp to
  read public pages. Truth Social collection works only by imitating a browser to get past
  its bot protection, which its terms likely prohibit; treat it as the highest-risk tab.
- Posts can contain disturbing or illegal material. If you encounter content that sexualizes
  minors, stop, do not save or share it, and report it to your instructor and to NCMEC
  (<https://report.cybertip.org>).

## Where data is stored

**Your corpus zips go to your Downloads folder**, the same way YT Timed Text saves its JSON.
When a collection finishes, the browser downloads `social_media_corpus_<date>_<id>.zip`
automatically; **Download again** fetches it a second time if needed. Move the zips wherever
your project keeps its data. The R scripts save their output next to whichever zip you pick.

The app doesn't keep its own copy of your zips. It has one hidden folder,
`~/.social_media_data_gathering/`, for its own files, which you never need to open:

- `config.json`: your keys and the pseudonymization salt. Keep the salt if you want pseudonyms
  to stay the same across collections.
- `collection_log.jsonl`: the collection log shown on the Log tab.
- `cache/`: model results, so re-running the same media with the same model is free.
- `media/`: temporary video and image downloads (emptied after extraction unless you keep media).
- `exports/`: holds each zip only until your browser has downloaded it; emptied every time
  the app starts.

To uninstall, including deleting that folder and revoking your keys, see
[Removing the app when you're done](docs/INSTALL.md#removing-the-app-when-youre-done).

## Troubleshooting

**"This post needs a login"**: the post is private, age-restricted, or the platform is
rate-limiting logged-out access. Wait 15 minutes and retry, or choose another public post.

**"The platform's page changed"**: TikTok, Instagram, and Facebook change their sites often.
Restart from source (it updates yt-dlp), or download the latest release.

**"The model did not return usable JSON (it may have refused)"**: some models decline graphic
content. Try a different model in Settings; the error is recorded in `llm_error`.

**Reddit 403**: the subreddit is private or quarantined, or your API app isn't approved yet.

## Tests

**Offline tests** (fast, no internet):

```bash
pip install -r requirements-dev.txt
pytest
```

They cover link recognition, caption parsing, pseudonymization, translation, and that every
platform's documents validate against the JSON schema.

**Live smoke test** (real posts, about 3 minutes): feeds the example links in
[`tests/smoke_urls.json`](tests/smoke_urls.json) to the app the same way the input boxes do,
for every tab, and checks the results.

```bash
python scripts/smoke_test.py
```

- `--app path/to/social-media-data-gathering.app` (or the `.exe`) tests a downloaded build
  instead of the source code. **Run this on a new release before sharing it.**
- `--model` also sends three videos through the model (needs `OPENROUTER_API_KEY`; a few cents).
- `--only tiktok` tests one tab.
- Reddit and Bluesky search run only when their credentials are set as environment variables.

Each run uses a throwaway settings folder, so it never touches your real settings. The example
links are also handy for trying each tab by hand. Posts get deleted over time; replace any
link that starts failing with a similar public post.

## Build your own binary

```bash
pip install -r requirements.txt pyinstaller
pyinstaller social_media_data_gathering.spec
# Output: dist/social-media-data-gathering (or .exe on Windows)
```

Pushing a version tag (for example `v0.3.0`) builds Mac and Windows binaries on GitHub Actions and attaches
them to a release.
