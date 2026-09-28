// Social Media Data Gathering frontend: one tab per platform, one export schema.

const $ = (s) => document.querySelector(s);
const statusEl = $("#status");

const COMMON_LANGS = ["en", "en-US", "es", "fr", "de", "pt", "it", "ja", "ko", "zh-Hans", "ar", "hi"];

// What each platform tab offers. Everything here mirrors what the backend supports.
const PLATFORMS = {
  youtube: {
    label: "YouTube",
    note: "By default this works like YT Timed Text: transcripts come from YouTube's own caption track (timedtext) and the raw timedtext JSON is included. Switch the transcript source to use the model instead, or both side by side.",
    linksLabel: "Video or Shorts links, one per line",
    placeholder: "https://www.youtube.com/watch?v=...\nhttps://youtu.be/...\nhttps://www.youtube.com/shorts/...",
    account: { label: "Channel", placeholder: "https://www.youtube.com/@channel", prefix: "youtube:", note: "Lists the channel's most recent uploads." },
    search: { note: "YouTube keyword search. No key needed." },
    comments: true, captions: true, model: false, pseudonymize: "commenters",
  },
  tiktok: {
    label: "TikTok",
    note: "Captions and hashtags come from the post. The model transcribes speech and describes the video. TikTok comments are not available.",
    linksLabel: "Video links, one per line",
    placeholder: "https://www.tiktok.com/@name/video/123...\nhttps://vm.tiktok.com/...",
    account: { label: "Profile", placeholder: "https://www.tiktok.com/@name", prefix: "tiktok:", note: "Best effort: TikTok profile listing breaks from time to time. If it fails, retry later or paste video links." },
    search: null,
    comments: false, captions: true, model: true,
  },
  instagram: {
    label: "Instagram",
    note: "Single public posts and reels only. Profiles and stories need a login, which this app never uses. The model transcribes speech and describes the video or images.",
    linksLabel: "Post or reel links, one per line",
    placeholder: "https://www.instagram.com/reel/...\nhttps://www.instagram.com/p/...",
    account: null, search: null,
    comments: true, captions: false, model: true,
  },
  facebook: {
    label: "Facebook",
    note: "Single public posts and videos only. Pages and profiles need a login, which this app never uses.",
    linksLabel: "Public post or video links, one per line",
    placeholder: "https://www.facebook.com/watch/?v=...\nhttps://www.facebook.com/reel/...",
    account: null, search: null,
    comments: false, captions: false, model: true,
  },
  reddit: {
    label: "Reddit",
    note: "Uses Reddit's official API. Requires your own free Reddit API key in Settings. The model is used only for posts with images or video.",
    linksLabel: "Post links, one per line",
    placeholder: "https://www.reddit.com/r/sub/comments/abc123/...",
    account: { label: "Subreddit or user", placeholder: "r/LanguageTechnology or u/username", prefix: "reddit:", sort: true, note: "" },
    search: { subreddit: true, note: "Searches all of Reddit, or one subreddit." },
    comments: true, captions: false, model: true, requires: "reddit",
  },
  bluesky: {
    label: "Bluesky",
    note: "Uses Bluesky's open API. Posts, replies, and profiles need no account. The model is used only for posts with images or video.",
    linksLabel: "Post links, one per line",
    placeholder: "https://bsky.app/profile/name.bsky.social/post/...",
    account: { label: "Profile", placeholder: "name.bsky.social or https://bsky.app/profile/name.bsky.social", prefix: "bsky:", note: "Lists original posts (reposts are skipped)." },
    search: { note: "Keyword search needs your Bluesky handle and an app password in Settings." },
    comments: true, captions: false, model: true,
  },
};

// Per-tab state, so switching tabs keeps what you typed and listed
const state = {};
// Default pseudonymization: keep the channel you study on YouTube; elsewhere post authors are often private people
for (const [p, cfg] of Object.entries(PLATFORMS)) {
  state[p] = { links: "", listRows: [], acct: "", query: "", lang: "en", valid: [], pseudo: cfg.pseudonymize || "everyone" };
}
let active = "youtube";
let settings = {};

function setStatus(msg, isError = false) {
  statusEl.textContent = msg || "";
  statusEl.classList.toggle("error", !!isError);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

const show = (el, on) => el.classList.toggle("hidden", !on);

async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
  return data;
}

// Read an NDJSON stream, calling onObj for each line
async function streamNDJSON(url, body, onObj) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${r.status})`);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      let obj;
      try { obj = JSON.parse(line); } catch { continue; }
      onObj(obj);
    }
  }
}

// -------- Quit --------
$("#quitBtn").addEventListener("click", async () => {
  if (!confirm("Stop the server and close the app?")) return;
  try { await fetch("/api/shutdown", { method: "POST" }); } catch (_) { /* server already gone */ }
  document.body.innerHTML = "<div style='padding:40px;font-family:sans-serif;color:#8a93a3'>Server stopped. You can close this tab.</div>";
});

// -------- Tabs --------
function buildTabs() {
  const nav = $("#tabs");
  for (const [key, p] of Object.entries(PLATFORMS)) {
    const b = document.createElement("button");
    b.className = "tab";
    b.dataset.tab = key;
    b.textContent = p.label;
    nav.appendChild(b);
  }
  const log = document.createElement("button");
  log.className = "tab tab-log";
  log.dataset.tab = "log";
  log.textContent = "Log";
  nav.appendChild(log);
  nav.addEventListener("click", (e) => {
    const t = e.target.closest(".tab");
    if (t) switchTab(t.dataset.tab);
  });
}

function saveTabState() {
  if (active === "log") return;
  const s = state[active];
  s.links = $("#links").value;
  s.acct = $("#acctInput").value;
  s.query = $("#searchQuery").value;
  s.lang = $("#optLang").value || s.lang;
  s.pseudo = $("#optPseudo").value;
}

function switchTab(tab) {
  saveTabState();
  active = tab;
  for (const x of document.querySelectorAll(".tab")) x.classList.toggle("active", x.dataset.tab === tab);
  show($("#platformPane"), tab !== "log");
  show($("#logPane"), tab === "log");
  show($("#progressView"), false);
  setStatus("");
  if (tab === "log") { loadLog(); updateBanner(); return; }

  const p = PLATFORMS[tab];
  const s = state[tab];
  $("#pNote").textContent = p.note;
  $("#linksLabel").textContent = p.linksLabel;
  $("#links").placeholder = p.placeholder;
  $("#links").value = s.links;
  $("#optPseudo").value = s.pseudo;

  show($("#accountBlock"), !!p.account);
  if (p.account) {
    $("#acctLabel").textContent = p.account.label;
    $("#acctInput").placeholder = p.account.placeholder;
    $("#acctInput").value = s.acct;
    $("#acctNote").textContent = p.account.note || "";
    show($("#acctSort"), !!p.account.sort);
  }
  show($("#searchBlock"), !!p.search);
  if (p.search) {
    $("#searchQuery").value = s.query;
    $("#searchNote").textContent = p.search.note || "";
    show($("#searchSub"), !!p.search.subreddit);
  }

  show($("#optYtSourceWrap"), tab === "youtube");
  show($("#optLlmWrap"), p.model);
  updateModelOptions();
  show($("#optLangWrap"), p.captions);
  show($("#optCommentsWrap"), p.comments);
  fillLangs(COMMON_LANGS.map(c => ({ code: c, label: c })), s.lang);

  renderList();
  updateBanner();
  classifyLinks();
}

// Model-related options show when the model can run on this tab
function usesModel() {
  const p = PLATFORMS[active];
  if (!p) return false;
  if (active === "youtube") return $("#optYtSource").value !== "captions";
  return p.model && $("#optLlm").checked;
}

function updateModelOptions() {
  const on = usesModel();
  const translating = !!$("#optTranslate").value.trim();
  show($("#optMaxWrap"), on);
  show($("#optKeepWrap"), on);
  show($("#modelLine"), on || translating);
  show($("#optLangWrap"), PLATFORMS[active]?.captions && !(active === "youtube" && $("#optYtSource").value === "model"));
  updateBanner();
}

$("#optYtSource").addEventListener("change", updateModelOptions);
$("#optLlm").addEventListener("change", updateModelOptions);
$("#optTranslate").addEventListener("input", updateModelOptions);

// -------- Links: validate against the active platform --------
let classifyTimer;
$("#links").addEventListener("input", () => {
  clearTimeout(classifyTimer);
  classifyTimer = setTimeout(classifyLinks, 350);
});

function linkLines() {
  return $("#links").value.split("\n").map(s => s.trim()).filter(Boolean);
}

async function classifyLinks() {
  const tab = active;
  const lines = linkLines();
  state[tab].valid = [];
  if (!lines.length) { $("#classifyInfo").textContent = ""; updateRunLabel(); return; }
  const res = await postJSON("/api/classify", { inputs: lines }).catch(() => []);
  if (tab !== active) return;
  const problems = [];
  for (const r of res) {
    if (!r.ok) problems.push(`${r.input}: ${r.error}`);
    else if (r.platform !== tab) problems.push(`${r.input}: this is a ${PLATFORMS[r.platform].label} link; paste it on the ${PLATFORMS[r.platform].label} tab.`);
    else if (r.kind === "account") problems.push(`${r.input}: this is an account; use the ${PLATFORMS[tab].account ? PLATFORMS[tab].account.label.toLowerCase() : "account"} box below.`);
    else state[tab].valid.push(r.input);
  }
  const n = state[tab].valid.length;
  $("#classifyInfo").innerHTML = (n ? `${n} ${PLATFORMS[tab].label} link${n === 1 ? "" : "s"} ready.` : "")
    + problems.map(p => `<div class="warn">${escapeHtml(p)}</div>`).join("");
  updateRunLabel();
  if (tab === "youtube") maybeLoadYoutubeLanguages();
}

// YouTube: with a single video, offer that video's actual caption languages (as in YT Timed Text)
let langFor = null;
async function maybeLoadYoutubeLanguages() {
  const valid = state.youtube.valid;
  if (valid.length !== 1 || state.youtube.listRows.length) {
    if (langFor) { langFor = null; fillLangs(COMMON_LANGS.map(c => ({ code: c, label: c })), state.youtube.lang); }
    return;
  }
  if (langFor === valid[0]) return;
  langFor = valid[0];
  const sel = $("#optLang");
  sel.innerHTML = `<option>Loading languages...</option>`;
  try {
    const r = await fetch(`/api/youtube/languages?url=${encodeURIComponent(valid[0])}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail);
    const opts = [
      ...(data.manual || []).map(m => ({ code: m.code, label: `${m.code}: ${m.name}` })),
      ...(data.auto || []).map(a => ({ code: a.code, label: `${a.code}: ${a.name} (auto)` })),
    ];
    if (!opts.length) {
      sel.innerHTML = `<option value="en">No captions available</option>`;
      return;
    }
    const pref = opts.find(o => o.code === "en") || opts.find(o => o.code.startsWith("en")) || opts[0];
    fillLangs(opts, pref.code);
  } catch {
    fillLangs(COMMON_LANGS.map(c => ({ code: c, label: c })), state.youtube.lang);
  }
}

function fillLangs(opts, selected) {
  const sel = $("#optLang");
  sel.innerHTML = "";
  const seen = new Set();
  for (const o of opts) {
    if (seen.has(o.code)) continue;
    seen.add(o.code);
    const el = document.createElement("option");
    el.value = o.code;
    el.textContent = o.label;
    sel.appendChild(el);
  }
  sel.value = seen.has(selected) ? selected : (opts[0] || {}).code;
}

// -------- Account + search listing --------
function renderList() {
  const rows = state[active].listRows;
  $("#lBody").innerHTML = "";
  $("#lFilter").value = "";
  for (const it of rows) appendListRow(it);
  show($("#listView"), rows.length > 0);
  updateListCount();
}

function appendListRow(it) {
  const tr = document.createElement("tr");
  tr.dataset.text = `${it.title} ${it.author}`.toLowerCase();
  const thumb = it.thumbnail ? `<img class="thumb" loading="lazy" src="${escapeHtml(it.thumbnail)}" alt="">` : "";
  tr.innerHTML = `
    <td><input type="checkbox" class="rowChk" data-url="${escapeHtml(it.url)}" ${it.checked === false ? "" : "checked"}></td>
    <td>${thumb}</td>
    <td><a href="${escapeHtml(it.url)}" target="_blank" rel="noopener">${escapeHtml((it.title || it.id || "").slice(0, 160))}</a></td>
    <td>${escapeHtml(it.author)}</td>
    <td>${escapeHtml((it.created_at || "").slice(0, 10))}</td>`;
  const chk = tr.querySelector(".rowChk");
  chk.addEventListener("change", () => { it.checked = chk.checked; updateListCount(); });
  $("#lBody").appendChild(tr);
}

function selectedUrls() {
  return state[active].listRows.filter(it => it.checked !== false && it.url).map(it => it.url);
}

function updateListCount() {
  $("#lCount").textContent = `${state[active].listRows.length} posts, ${selectedUrls().length} selected`;
  updateRunLabel();
}

async function runListing(url, body, btn) {
  const tab = active;
  const rows = state[tab].listRows;
  rows.length = 0;
  renderList();
  show($("#listView"), true);
  btn.disabled = true;
  setStatus("Listing posts...");
  let err = null;
  try {
    await streamNDJSON(url, body, (obj) => {
      if (obj.event === "error") { err = obj.error; return; }
      rows.push(obj);
      if (tab === active) {
        appendListRow(obj);
        if (rows.length % 10 === 0) updateListCount();
      }
    });
    setStatus(err ? err : `Found ${rows.length} posts. Uncheck any you don't want, then Collect.`, !!err);
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    btn.disabled = false;
    if (tab === active) { updateListCount(); show($("#listView"), rows.length > 0); }
  }
}

function accountInput(raw) {
  // Bare handles like "@name" or "r/sub" get the platform prefix the backend expects
  raw = raw.trim();
  const p = PLATFORMS[active].account;
  return /^https?:\/\/|\.(com|app)\//i.test(raw) ? raw : p.prefix + raw;
}

$("#acctGo").addEventListener("click", () => {
  const raw = $("#acctInput").value.trim();
  if (!raw) return;
  runListing("/api/list", { input: accountInput(raw), limit: +$("#acctLimit").value || 25, sort: $("#acctSort").value }, $("#acctGo"));
});

$("#searchGo").addEventListener("click", () => {
  const query = $("#searchQuery").value.trim();
  if (!query) return;
  runListing("/api/search", {
    platform: active, query,
    limit: +$("#searchLimit").value || 50, sort: $("#searchSort").value,
    subreddit: $("#searchSub").value.trim().replace(/^r\//, ""),
  }, $("#searchGo"));
});

$("#lAll").addEventListener("change", (e) => {
  const trs = document.querySelectorAll("#lBody tr");
  state[active].listRows.forEach((it, i) => {
    if (trs[i] && trs[i].style.display !== "none") {
      it.checked = e.target.checked;
      trs[i].querySelector(".rowChk").checked = e.target.checked;
    }
  });
  updateListCount();
});

$("#lFilter").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase().trim();
  for (const tr of document.querySelectorAll("#lBody tr")) {
    tr.style.display = !q || tr.dataset.text.includes(q) ? "" : "none";
  }
});

$("#lClear").addEventListener("click", () => {
  state[active].listRows.length = 0;
  renderList();
});

// -------- Collect --------
function currentInputs() {
  if (active === "log") return [];
  return [...new Set([...state[active].valid, ...selectedUrls()])];
}

function updateRunLabel() {
  const n = currentInputs().length;
  $("#runBtn").textContent = n ? `Collect ${n} ${PLATFORMS[active]?.label || ""} post${n === 1 ? "" : "s"}` : "Collect";
  $("#runBtn").disabled = !n;
}

function options() {
  const p = PLATFORMS[active];
  return {
    llm: usesModel(),
    youtube_source: $("#optYtSource").value,
    translate_to: $("#optTranslate").value.trim(),
    comments: p.comments ? (+$("#optComments").value || 0) : 0,
    max_media_seconds: +$("#optMaxSecs").value || 300,
    caption_lang: $("#optLang").value || "en",
    pseudonymize: $("#optPseudo").value,
    include_identifiable: $("#optIdent").checked,
    keep_media: usesModel() && $("#optKeep").checked,
    model: settings.model,
  };
}

$("#runBtn").addEventListener("click", async () => {
  const inputs = currentInputs();
  if (!inputs.length) return;
  const p = PLATFORMS[active];
  $("#runBtn").disabled = true;
  show($("#progressView"), true);
  show($("#zipLink"), false);
  show($("#aiLabel"), usesModel() || !!$("#optTranslate").value.trim());
  $("#progBody").innerHTML = "";
  $("#progTitle").textContent = `Collecting 0 of ${inputs.length}...`;
  setStatus("");
  let done = 0;
  try {
    await streamNDJSON("/api/collect", { inputs, options: options() }, (ev) => {
      if (ev.event === "item") {
        done++;
        $("#progTitle").textContent = `Collecting ${done} of ${inputs.length}...`;
        const tr = document.createElement("tr");
        let result;
        if (!ev.ok) result = `<span class="err">${escapeHtml(ev.error)}</span>`;
        else {
          result = `${ev.n_docs} doc${ev.n_docs === 1 ? "" : "s"}`
            + (ev.cost ? ` <span class="muted">($${ev.cost.toFixed(4)})</span>` : "")
            + (ev.preview ? `<div class="preview">${escapeHtml(ev.preview)}</div>` : "")
            + (ev.llm_error ? `<div class="warn">Model: ${escapeHtml(ev.llm_error)}</div>` : "");
        }
        tr.innerHTML = `<td>${ev.i + 1}</td><td class="input-cell">${escapeHtml(ev.input)}</td><td>${result}</td>`;
        $("#progBody").appendChild(tr);
      } else if (ev.event === "done") {
        $("#progTitle").textContent = `Done: ${ev.ok} collected, ${ev.failed} failed, ${ev.n_docs} documents`
          + (ev.cost ? `, model cost $${ev.cost.toFixed(4)}` : "");
        const a = $("#zipLink");
        a.href = `/api/exports/${encodeURIComponent(ev.zip)}`;
        show(a, true);
      } else if (ev.event === "error") {
        setStatus(ev.error, true);
      }
    });
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    updateRunLabel();
  }
});

// -------- Log --------
async function loadLog() {
  $("#logPath").textContent = (settings.data_dir || "") + "/collection_log.jsonl";
  const rows = await fetch("/api/log").then(r => r.json()).catch(() => []);
  $("#logBody").innerHTML = rows.map(r => `<tr>
    <td>${escapeHtml((r.requested_at || "").replace("T", " ").replace("Z", ""))}</td>
    <td>${escapeHtml(r.platform || "")}</td>
    <td class="input-cell">${escapeHtml(r.input)}</td>
    <td>${r.ok ? `${r.n_docs} docs` : `<span class="err">${escapeHtml(r.error)}</span>`}</td></tr>`).join("")
    || `<tr><td colspan="4" class="muted">Nothing collected yet.</td></tr>`;
}

// -------- Settings --------
function updateBanner() {
  const p = PLATFORMS[active];
  let msg = "";
  if (p && p.requires === "reddit" && !settings.reddit_client_id) {
    msg = "Reddit needs your own API client ID and secret before anything can be collected.";
  } else if (p && (usesModel() || $("#optTranslate").value.trim()) && !settings.openrouter_api_key) {
    msg = "No OpenRouter key yet. Posts will still be collected, but model extraction and translation are skipped.";
  }
  const b = $("#keyWarning");
  b.innerHTML = msg ? `${escapeHtml(msg)} <a href="#" id="keyWarningLink">Open Settings</a>.` : "";
  show(b, !!msg);
  if (msg) $("#keyWarningLink").addEventListener("click", (e) => { e.preventDefault(); openSettings(); });
}

async function loadSettings() {
  settings = await fetch("/api/settings").then(r => r.json());
  $("#modelName").textContent = settings.model;
  $("#dataDir").textContent = settings.data_dir;
  updateBanner();
}

async function loadModels() {
  const sel = $("#sModel");
  sel.innerHTML = `<option>Loading models...</option>`;
  try {
    const data = await fetch("/api/models").then(r => r.json());
    sel.innerHTML = "";
    if (!data.models.some(m => m.id === settings.model)) data.models.unshift({ id: settings.model });
    for (const m of data.models) {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.id + (m.prompt_per_million != null ? `  ($${m.prompt_per_million.toFixed(2)}/M)` : "");
      sel.appendChild(o);
    }
    sel.value = settings.model;
  } catch {
    sel.innerHTML = `<option value="${escapeHtml(settings.model)}">${escapeHtml(settings.model)}</option>`;
  }
}

function openSettings() {
  $("#sOpenrouter").value = "";
  $("#sOpenrouter").placeholder = settings.openrouter_api_key ? "saved (leave blank to keep)" : "sk-or-...";
  $("#sRedditId").value = settings.reddit_client_id || "";
  $("#sRedditSecret").value = "";
  $("#sRedditSecret").placeholder = settings.reddit_client_secret ? "saved (leave blank to keep)" : "";
  $("#sBskyHandle").value = settings.bluesky_handle || "";
  $("#sBskyPw").value = "";
  $("#sBskyPw").placeholder = settings.bluesky_app_password ? "saved (leave blank to keep)" : "xxxx-xxxx-xxxx-xxxx";
  $("#settingsStatus").textContent = "";
  $("#settingsDlg").showModal();
  loadModels();
}

$("#settingsBtn").addEventListener("click", openSettings);

$("#settingsSave").addEventListener("click", async (e) => {
  e.preventDefault();
  const body = {
    model: $("#sModel").value,
    reddit_client_id: $("#sRedditId").value.trim(),
    bluesky_handle: $("#sBskyHandle").value.trim(),
  };
  // Blank secret fields mean "keep what's saved"
  if ($("#sOpenrouter").value.trim()) body.openrouter_api_key = $("#sOpenrouter").value.trim();
  if ($("#sRedditSecret").value.trim()) body.reddit_client_secret = $("#sRedditSecret").value.trim();
  if ($("#sBskyPw").value.trim()) body.bluesky_app_password = $("#sBskyPw").value.trim();
  try {
    await postJSON("/api/settings", body);
    await loadSettings();
    $("#settingsDlg").close();
  } catch (err) {
    $("#settingsStatus").textContent = err.message;
  }
});

buildTabs();
loadSettings().then(() => switchTab("youtube"));
