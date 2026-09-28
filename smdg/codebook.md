# Codebook: social media corpus export

Produced by social-media-data-gathering. Read this before analysis.

## Files

| File | Contents |
|---|---|
| `corpus.jsonl` | One JSON object per line, one line per document (a post or a comment). **Every platform uses the same fields**, defined in `document.schema.json`. Each document also carries its time-stamped transcript `segments`. |
| `document.schema.json` | The JSON Schema for a `corpus.jsonl` line: field names, types, and allowed values. |
| `corpus.csv` + `segments.csv` | The same data flattened for spreadsheets: documents in one file, transcript segments in the other (join on `doc_id`). |
| `timedtext/` | YouTube only: the raw caption files exactly as YouTube's timedtext API returned them (json3), as in yt-timed-text. |
| `manifest.json` | Provenance: every input, its status and error, the options used, the exact model prompt and version, and the model cost. |
| `identifiable/` | Included by default. `linking_key.csv` maps each document to its real author and URL; `pseudonym_key.csv` maps every code (authors and @mentions) to the original name; `raw/` holds the full platform responses. `examples/restore_identities.R` uses these to put names back. **Store this folder separately from the analysis data and delete it when your protocol says to.** |

## Fields (same for every platform)

| Column | Meaning |
|---|---|
| `doc_id` | Unique id: `platform_doctype_id`. |
| `platform` | youtube, tiktok, instagram, facebook, reddit, bluesky. |
| `doc_type` | `post` or `comment`. |
| `post_id` | The platform id of the post this document belongs to. Comments share their post's `post_id`. |
| `parent_id` | For comments, the `doc_id` of the post or comment being replied to. Use it to rebuild reply trees. |
| `url` | Link to the document. Blank when the author was pseudonymized (see the linking key). |
| `author`, `author_id` | Account name and platform id, or a pseudonym such as `u_3f9a1c02de`. With "commenters and @mentions only", the authors of the collected posts keep their real names. The same account always gets the same pseudonym on the computer that collected it, and @mentions of that account in text use the same code. |
| `community` | Subreddit for Reddit; blank elsewhere. |
| `created_at` | When the document was posted, ISO 8601 UTC. |
| `title` | Title (YouTube and Reddit posts only). |
| `text` | What the author typed: the caption, description, post body, or comment. Never AI-generated. |
| `caption_transcript` | Speech transcript from captions the **platform** supplied (YouTube timedtext; TikTok when available). |
| `caption_source` | `manual` (uploaded by the creator), `auto` (platform speech recognition), or `none`. |
| `llm_transcript` | Speech transcript produced by the **model**, one line per speaker turn, prefixed with the speaker label (`A:`, `B:`, `?:` when unclear). For YouTube, only when the transcript source is `model` or `both`. |
| `on_screen_text` | Text overlays, captions, and signs the model read from the video or images, separated by ` \| `. |
| `visual_description` | The model's description of what is shown. |
| `audio_description` | The model's note on music and other non-speech audio. |
| `speakers` | The distinct voices the model heard, labeled `A`, `B`, `C` in order of first speech, each with a neutral description and whether they were on screen. JSON: a list of `{id, description, on_screen}`; CSV: `A: description (on screen) \| B: ...`. |
| `alt_text` | Image descriptions written by the author (Bluesky). |
| `media_type` | video, image, mixed, or text. |
| `language` | Language code from the platform, or from the model when the platform gave none. |
| `hashtags` | Hashtags found in `text` and platform tags, space separated, without `#`. |
| `like_count`, `reply_count`, `share_count`, `view_count` | Engagement at the moment of collection (Reddit `like_count` is net score). Integers in JSON; `null` (blank in CSV) means the platform did not report it, not zero. |
| `ai_generated` | `true` when any model-produced field (extraction or translation) on this document has content. |
| `segments` | JSON only: list of `{source, speaker, start_seconds, end_seconds, text}`. `source` is `caption_manual`, `caption_auto`, or `llm`; `speaker` is set for model segments only. |
| `llm_model` | The OpenRouter model that produced the model columns. |
| `llm_error` | Why model extraction did not run or failed (for example, too long, refused, no media). |
| `translation_language` | Target language of the `translated_*` fields; empty when translation was off. |
| `translated_title`, `translated_text`, `translated_caption_transcript`, `translated_llm_transcript`, `translated_on_screen_text` | Model translations of the matching fields. The originals are never changed. Speaker labels are kept in the translated transcript. |
| `source_input` | Exactly what was pasted to collect this document. |
| `collected_at` | When this row was collected, ISO 8601 UTC. |

## Measurement notes

- **Model columns are unverified.** `llm_transcript`, `on_screen_text`, `visual_description`, and `audio_description` come from a language model. They can mishear speech, misread small or fast text, and describe imagery wrongly. Validate a sample by hand before relying on them, and report the model and prompt version (in `manifest.json`) in your methods.
- **Speaker labels are per video and approximate.** `A` in one video has nothing to do with `A` in another. Multimodal models attribute words to speakers reasonably well but place turn boundaries loosely, so model `start_seconds` are approximate and `end_seconds` are empty. Hand-check videos with three or more speakers.
- **Translations are model output.** Analyze originals and translations separately, and say which you used. Slang, sarcasm, and code-switching are where translations most often go wrong.
- **Two transcript sources are kept apart on purpose.** Platform captions and model transcripts have different error profiles. Pick one per analysis, or compare them; do not mix them in one variable without saying so.
- **The model does not see the author's caption.** It works only from the media, so `text` and the model columns are independent measurements.
- **YouTube comment dates are approximate.** YouTube only reports relative times ("3 years ago"), so `created_at` for YouTube comments is rounded.
- **Engagement counts change.** They are a snapshot at `collected_at`.
- **Comments are a sample.** Platforms return a limited, platform-ordered set (for example, "top" first). They are not every reply.
