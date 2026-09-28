"""Offline tests: URL classification, caption parsing, pseudonymization, and the JSON schema."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from smdg import captions, classify
from smdg.pipeline import to_document
from smdg.records import COLUMNS, new_row, pseudonymize

SCHEMA = json.loads((Path(__file__).parent.parent / "smdg" / "document.schema.json").read_text())


@pytest.mark.parametrize("url,platform,kind", [
    ("https://www.youtube.com/watch?v=jNQXAC9IVRw", "youtube", "post"),
    ("https://youtu.be/jNQXAC9IVRw", "youtube", "post"),
    ("https://www.youtube.com/shorts/tPEE9ZwTmy0", "youtube", "post"),
    ("https://www.youtube.com/@jawed", "youtube", "account"),
    ("https://www.tiktok.com/@scout2015/video/6718335390845095173", "tiktok", "post"),
    ("https://vm.tiktok.com/ZMabc123/", "tiktok", "post"),
    ("https://www.tiktok.com/@scout2015", "tiktok", "account"),
    ("tiktok:@scout2015", "tiktok", "account"),
    ("https://www.instagram.com/reel/Chunk8-jurw/", "instagram", "post"),
    ("https://www.instagram.com/p/BQ0eAlwhDrw/?igsh=abc", "instagram", "post"),
    ("https://www.facebook.com/watch/?v=10153231379946729", "facebook", "post"),
    ("https://fb.watch/abc123/", "facebook", "post"),
    ("https://www.reddit.com/r/LanguageTechnology/comments/abc123/some_title/", "reddit", "post"),
    ("https://www.reddit.com/r/LanguageTechnology/", "reddit", "account"),
    ("reddit:u/spez", "reddit", "account"),
    ("https://bsky.app/profile/bsky.app/post/3mw2cdr44fc2a", "bluesky", "post"),
    ("bsky:bsky.app", "bluesky", "account"),
    ("https://truthsocial.com/@realDonaldTrump/posts/117346090177597599", "truthsocial", "post"),
    ("https://truthsocial.com/@realDonaldTrump/117346090177597599", "truthsocial", "post"),
    ("https://truthsocial.com/@realDonaldTrump", "truthsocial", "account"),
    ("truth:@realDonaldTrump", "truthsocial", "account"),
    ("https://rumble.com/v7g1oa0-q-after-hours-ep.-37.html", "other", "post"),
    ("https://www.bitchute.com/video/UGlrF9o9b-Q/", "other", "post"),
    ("https://www.dailymotion.com/video/x5kesuj", "other", "post"),
    ("https://odysee.com/@Odysee:8/first-day-in-lbry:e", "other", "post"),
    ("other:https://rumble.com/c/Rumble", "other", "account"),
])
def test_classify(url, platform, kind):
    t = classify.classify(url)
    assert (t["platform"], t["kind"]) == (platform, kind)


@pytest.mark.parametrize("url", [
    "https://www.instagram.com/natgeo/",
    "https://www.instagram.com/stories/natgeo/123/",
    "https://x.com/someone/status/1",
    "https://www.snapchat.com/add/someone",
    "https://example.com/page",
])
def test_classify_rejects(url):
    with pytest.raises(ValueError):
        classify.classify(url)


def test_vimeo_pages_use_the_player_url():
    assert classify.classify("https://vimeo.com/76979871")["url"] == "https://player.vimeo.com/video/76979871"


def test_truthsocial_html_to_text():
    from smdg.truthsocial import html_to_text
    raw = '<p>Big news!<br>Line two &amp; more</p><p>See <span class="h-card"><a href="x">@<span>someone</span></a></span></p>'
    assert html_to_text(raw) == "Big news!\nLine two & more\n\nSee @someone"
    assert html_to_text("<p></p>") == ""


def test_parse_vtt_drops_markup_and_rolling_duplicates():
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:01.500\n<c>hello</c> there\n\n00:00:01.500 --> 00:00:02.000\nhello there\n\n00:00:02.000 --> 00:00:03.250\nsecond line\n"
    segs = captions.parse_vtt(vtt)
    assert [s["text"] for s in segs] == ["hello there", "second line"]
    assert segs[1]["start_seconds"] == 2.0 and segs[1]["end_seconds"] == 3.25


def test_parse_json3():
    data = {"events": [{"tStartMs": 1200, "dDurationMs": 2160, "segs": [{"utf8": "All right"}]}, {"tStartMs": 4000}]}
    assert captions.parse_json3(data) == [{"start_seconds": 1.2, "end_seconds": 3.36, "text": "All right"}]


def test_pseudonymize_is_stable_and_masks_mentions():
    a = new_row("bluesky", "post", "1", author="alice.bsky.social", author_id="did:plc:a", url="https://x", text="hi @bob.bsky.social")
    b = new_row("bluesky", "comment", "1", comment_id="2", author="alice.bsky.social", author_id="did:plc:a", text="again")
    rows, key, names = pseudonymize([a, b])
    assert rows[0]["author"] == rows[1]["author"] != "alice.bsky.social"
    assert rows[0]["url"] == "" and "bob" not in rows[0]["text"]
    assert key[0]["url"] == "https://x"
    assert {n["original"] for n in names} == {"alice.bsky.social", "@bob.bsky.social"}


def test_mention_and_author_share_a_pseudonym():
    post = new_row("bluesky", "post", "1", author="bob.bsky.social", author_id="did:plc:b", text="hi")
    com = new_row("bluesky", "comment", "1", comment_id="2", author="carol.bsky.social", author_id="did:plc:c", text="@bob.bsky.social agreed")
    rows, _, _ = pseudonymize([post, com])
    assert rows[1]["text"] == f"@{rows[0]['author']} agreed"


def test_commenters_mode_keeps_the_studied_channel():
    post = new_row("youtube", "post", "v1", author="Channel 5 News", author_id="@Channel5News", url="https://yt/v1", text="Report")
    com = new_row("youtube", "comment", "v1", comment_id="c1", author="@viewer1", author_id="UCviewer", url="https://yt/v1",
                  text="@Channel5News thanks, and @viewer2 look")
    rows, key, names = pseudonymize([post, com], "commenters")
    assert rows[0]["author"] == "Channel 5 News" and rows[0]["url"] == "https://yt/v1"
    assert rows[1]["author"].startswith("u_") and rows[1]["url"] == ""
    assert "@Channel5News" in rows[1]["text"] and "viewer2" not in rows[1]["text"]
    assert key[0]["pseudonym"] == "" and key[1]["author"] == "@viewer1"


def test_none_mode_changes_nothing():
    r = new_row("reddit", "post", "1", author="someone", text="hi @other")
    rows, key, names = pseudonymize([r], "none")
    assert rows[0]["author"] == "someone" and rows[0]["text"] == "hi @other" and key == names == []


def test_documents_match_schema_for_every_platform():
    v = Draft202012Validator(SCHEMA)
    for plat in ("youtube", "tiktok", "instagram", "facebook", "reddit", "bluesky", "truthsocial", "other"):
        row = new_row(plat, "post", "abc", text="#nlp is fun", like_count="12", view_count=None, created_at="2024-05-01T10:00:00.123Z")
        row["speakers"] = [{"id": "A", "description": "person facing camera", "on_screen": True}]
        doc = to_document(row, [{"doc_id": row["doc_id"], "source": "llm", "speaker": "A", "start_seconds": 0.5, "end_seconds": "", "text": "hi"}])
        assert list(v.iter_errors(doc)) == []
        assert doc["site"] == ("" if plat == "other" else doc["site"]) and (plat == "other" or "." in doc["site"])
        assert doc["like_count"] == 12 and doc["view_count"] is None
        assert doc["created_at"] == "2024-05-01T10:00:00Z" and doc["hashtags"] == "nlp"
    assert set(SCHEMA["properties"]) == set(COLUMNS) | {"segments"}


def test_schema_file_is_current():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_schema", Path(__file__).parent.parent / "scripts" / "build_schema.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.build() == SCHEMA, "Run python scripts/build_schema.py"


def test_translation_fills_fields_and_keeps_originals(monkeypatch):
    from smdg import config, llm, pipeline
    monkeypatch.setattr(config, "get", lambda name, default="": "key" if name == "openrouter_api_key" else default)
    monkeypatch.setattr(llm, "translate", lambda values, lang, model: ({k: "EN:" + v for k, v in values.items()}, {"cost": 0.001}))
    post = new_row("tiktok", "post", "1", text="hola", llm_transcript="A: buenos dias")
    com = new_row("tiktok", "comment", "1", comment_id="2", text="que bueno")
    result = {"rows": [post, com]}
    usage = pipeline._apply_translation(result, {"translate_to": "English", "model": "m"})
    assert post["text"] == "hola" and post["translated_text"] == "EN:hola"
    assert post["translated_llm_transcript"] == "EN:A: buenos dias"
    assert com["translated_text"] == "EN:que bueno" and com["translation_language"] == "English"
    assert post["ai_generated"] is True and usage["cost"] == 0.001
