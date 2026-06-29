"use strict";

// ---- taxonomy (single source for the UI; mirrors the design note) ----
const TARGET = [
  ["school_bell_schedule", "Bell schedule — period table/list"],
  ["school_start_end_prose", "Start/end times in prose"],
  ["district_hub_schedule", "District hub — per-school/band table"],
  ["explicit_instructional_time", "Explicit instructional minutes"],
  ["nonstandard_format", "Target info, un-enumerated shape"],
];
const NONTARGET = [
  ["board_schedule", "School Board / Trustees"],
  ["sports_schedule", "Athletics / sports"],
  ["academic_calendar", "Academic calendar"],
  ["community_calendar", "Community / events calendar"],
  ["transportation_schedule", "Bus / transportation"],
  ["embedded_feed", "Embedded social-media / blog feed"],
  ["other_schedule", "Other activity schedule"],
  ["none", "No schedule / instructional info"],
  ["unusable", "Garbled / empty / uninterpretable"],
];
const FLAGS = [
  ["duplicate", "Duplicate of another record"],
  ["buried_in_long_doc", "Target buried in a long doc (handbook)"],
  ["building_hours_visible", "Building/office hours visible (start-end red herring)"],
];
// The one human-only signal: the target is plainly visible in the image/PDF but NO text
// extractor (pdftotext/camelot/tesseract) captured it -> this record needs vision at Stage 6/7.
// Only meaningful when a Target-present label is chosen; sits next to the target shapes.
const IMAGE_ONLY = ["target_image_only", "Target is in the image/PDF but missing from ALL text extractions — needs vision"];
const DEFS = {
  school_bell_schedule: "A table or list that breaks the school day into periods.",
  school_start_end_prose: "Sentence(s) declaring the start and end time of the school day.",
  district_hub_schedule: "A table/list of start & end times for each school in a district, or each grade band.",
  explicit_instructional_time: "A declaration like “Students receive XXX minutes of instruction every day.”",
  nonstandard_format: "Contains bell-schedule / instructional-time info in a shape we haven't enumerated.",
  board_schedule: "Scheduling/agenda info for the School Board / Board of Trustees.",
  sports_schedule: "Scheduling for athletics/sports teams.",
  academic_calendar: "A school/district calendar (year, holidays, early-release) — time-bearing but not a schedule.",
  community_calendar: "A community / events calendar (school or community events) — not the academic calendar, not a schedule.",
  transportation_schedule: "Bus/transport times. Tricky boundary vs. legitimate start/end prose.",
  embedded_feed: "An embedded social-media or blog feed is the dominant content — its date/time stamps are spurious signal, not a schedule.",
  other_schedule: "Scheduling for some other school activity — the residual non-target bucket.",
  none: "No discernible schedule or instructional-time info.",
  unusable: "Garbled, effectively empty, or impossible to interpret.",
  duplicate: "Byte-identical content to another record; label the canonical once.",
  buried_in_long_doc: "Target info present but inside a multi-topic document (e.g. a handbook).",
  building_hours_visible: "The page shows building/office hours (often a footer 'Building Hours 7:15–3:15') that mimic a start/end pair but are NOT the student day — a red herring to monitor.",
  target_image_only: "You can see the target (bell schedule / start-end / instructional time) in the image or PDF, but NO text extractor captured it. The 'needs vision' signal — only tick it on a record that IS a target.",
};
const TIER_DEF = {
  A: "Strong target candidate — a time pair in the school-day window + schedule keywords.",
  B: "Plausible — in-window times present, weaker keyword evidence.",
  C: "Unlikely / negative-leaning — board/sports/calendar or all-after-5pm.",
  D: "Drop-candidate — no times / unusable.",
};

const $ = (s, r = document) => r.querySelector(s);
let CURRENT = null;   // rec_key
let DATA = null;      // record detail

function fileUrl(d, fn) { return `/files/${d.district_dir}/${d.hash}/${encodeURIComponent(fn)}`; }
const short = (u) => (u || "").replace(/^https?:\/\//, "").slice(0, 40);

// ----------------------------- left pane: faceted, attention-first, district-driven -----------------------------
// The Stage-5 rework. Group by DISTRICT facets, filter by RECORD facets (the district stays visible),
// sort by district fields (incl. continuous) asc/desc — all server-side (/api/stage5/districts). Default:
// no grouping, attention-first. View-state persists across stage switches + reloads (localStorage), and
// can be saved as named presets (DB-backed). The batch is gone here; the district is the unit.
const ATTN_REASON = {   // dominant reason -> {label, tone} for the rationale chips
  manual_flag: ["⚑ flagged", "r-flag"], image_only: ["image-only", "r-image"],
  signal_text_disagree: ["signal≠text", "r-disagree"], buried_long_doc: ["buried in doc", "r-buried"],
  ambiguous: ["ambiguous", "r-amb"], clean_target: ["clean yes", "r-clean"],
  low_signal: ["low signal", "r-low"], resolved: ["done", "r-done"],
};
const GROUP_LABEL = { none: "No grouping", pipeline_state: "Pipeline state (label+guess)",
  state: "US state", topology: "Topology" };
const SORT_LABEL = { attention: "Need for attention", name: "Name (A–Z)", enrollment: "Enrollment",
  schools: "# schools (NCES)", recent: "Most recent change", first_seen: "First seen at gate@5" };
const DEFAULT_VIEW = { group_by: "none", sort: "attention", dir: "desc", label: "",
  tiers: [], reasons: [], hide_resolved: false };
let VIEW = loadView();
let FACETS = null;

function loadView() {
  try { return { ...DEFAULT_VIEW, ...JSON.parse(localStorage.getItem("s5_view") || "{}") }; }
  catch (_) { return { ...DEFAULT_VIEW }; }
}
function persistView() { localStorage.setItem("s5_view", JSON.stringify(VIEW)); }

function viewQuery() {
  const p = new URLSearchParams();
  p.set("group_by", VIEW.group_by); p.set("sort", VIEW.sort); p.set("dir", VIEW.dir);
  if (VIEW.label) p.set("label", VIEW.label);
  (VIEW.tiers || []).forEach((t) => p.append("tier", t));
  (VIEW.reasons || []).forEach((r) => p.append("reason", r));
  if (VIEW.hide_resolved) p.set("hide_resolved", "true");
  return p.toString();
}

async function loadTree() {   // (name kept: splitRecord + initial boot call it)
  if (!FACETS) { try { FACETS = await (await fetch("/api/stage5/facets")).json(); } catch (_) { FACETS = {}; } }
  let data;
  try { data = await (await fetch(`/api/stage5/districts?${viewQuery()}`)).json(); }
  catch (e) { $("#tree").innerHTML = `<div class="empty err">Couldn't load: ${e.message}</div>`; return; }
  const tree = $("#tree");
  tree.innerHTML = "";
  tree.appendChild(renderControls(data));
  const list = document.createElement("div"); list.id = "s5-list";
  data.groups.forEach((g) => list.appendChild(renderGroup(g, data.group_by)));
  if (!data.groups.length) list.innerHTML = `<div class="empty">No districts match.</div>`;
  tree.appendChild(list);
  refreshProgress();
}
window.loadStage5 = loadTree;   // gate1.js re-fetches on view-show

// ----------------------------- controls -----------------------------
function renderControls(data) {
  const bar = document.createElement("div"); bar.className = "s5-bar";
  const opt = (o, sel) => `<option value="${o}" ${o === sel ? "selected" : ""}>`;
  const groupOpts = Object.keys(GROUP_LABEL).map((k) => `${opt(k, VIEW.group_by)}${GROUP_LABEL[k]}</option>`).join("");
  const sortOpts = Object.keys(SORT_LABEL).map((k) => `${opt(k, VIEW.sort)}${SORT_LABEL[k]}</option>`).join("");
  const arrow = VIEW.dir === "asc" ? "↑" : "↓";
  const labelChip = (v, t) => `<button class="s5-chip ${VIEW.label === v ? "on" : ""}" data-label="${v}">${t}</button>`;
  const reasonChips = ((FACETS && FACETS.reason) || []).map((r) =>
    `<button class="s5-chip ${VIEW.reasons.includes(r.value) ? "on" : ""}" data-reason="${r.value}" title="${r.count} records">${(ATTN_REASON[r.value] || [r.value])[0]}</button>`).join("");
  const tierChips = ["A", "B", "C", "D"].map((t) =>
    `<button class="s5-chip ${VIEW.tiers.includes(t) ? "on" : ""}" data-tier="${t}">${t}</button>`).join("");

  bar.innerHTML = `
    <div class="s5-row">
      <label>Group</label><select id="s5-group">${groupOpts}</select>
      <label>Sort</label><select id="s5-sort">${sortOpts}</select>
      <button id="s5-dir" class="s5-icon" title="ascending / descending">${arrow}</button>
    </div>
    <div class="s5-row s5-filters">
      <span class="s5-flabel">labels</span>${labelChip("", "all")}${labelChip("unlabeled", "unlabeled")}${labelChip("labeled", "labeled")}
      <span class="s5-flabel">tier</span>${tierChips}
      <label class="s5-toggle"><input type="checkbox" id="s5-hideres" ${VIEW.hide_resolved ? "checked" : ""}/> hide resolved</label>
    </div>
    <div class="s5-row s5-reasons"><span class="s5-flabel">attention</span>${reasonChips || "<span class='q-smeta'>—</span>"}</div>
    <div class="s5-row s5-views">
      <select id="s5-viewsel"><option value="">Saved views…</option></select>
      <button id="s5-viewsave" class="btn btn-ghost s5-mini">Save view</button>
      <span class="s5-count">${data.shown}/${data.total_districts} districts</span>
    </div>`;

  bar.querySelector("#s5-group").onchange = (e) => { VIEW.group_by = e.target.value; commitView(); };
  bar.querySelector("#s5-sort").onchange = (e) => { VIEW.sort = e.target.value; commitView(); };
  bar.querySelector("#s5-dir").onclick = () => { VIEW.dir = VIEW.dir === "asc" ? "desc" : "asc"; commitView(); };
  bar.querySelector("#s5-hideres").onchange = (e) => { VIEW.hide_resolved = e.target.checked; commitView(); };
  bar.querySelectorAll("[data-label]").forEach((b) => b.onclick = () => { VIEW.label = b.dataset.label; commitView(); });
  bar.querySelectorAll("[data-tier]").forEach((b) => b.onclick = () => { toggle(VIEW.tiers, b.dataset.tier); commitView(); });
  bar.querySelectorAll("[data-reason]").forEach((b) => b.onclick = () => { toggle(VIEW.reasons, b.dataset.reason); commitView(); });
  bar.querySelector("#s5-viewsave").onclick = saveCurrentView;
  populateViewSelect(bar.querySelector("#s5-viewsel"));
  return bar;
}
function toggle(arr, v) { const i = arr.indexOf(v); if (i < 0) arr.push(v); else arr.splice(i, 1); }
function commitView() { persistView(); loadTree(); }

// ----------------------------- groups + districts -----------------------------
function groupTitle(key, group_by) {
  if (group_by === "none") return "All districts";
  if (group_by === "pipeline_state") return ({ untouched: "Untouched", partial: "In progress", complete: "Resolved" }[key] || key);
  return key;
}
function renderGroup(g, group_by) {
  const wrap = document.createElement("div"); wrap.className = "s5-group";
  if (group_by !== "none") {
    const head = document.createElement("div"); head.className = "s5-group-head";
    head.innerHTML = `<span class="s5-caret">▾</span><span class="s5-gtitle">${groupTitle(g.key, group_by)}</span>
      <span class="s5-gcount">${g.n_districts} · <b>${g.n_attention}</b> need attention</span>`;
    const body = document.createElement("div"); body.className = "s5-group-body";
    g.districts.forEach((d) => body.appendChild(renderDistrict(d)));
    head.onclick = () => { body.classList.toggle("hidden"); head.querySelector(".s5-caret").textContent = body.classList.contains("hidden") ? "▸" : "▾"; };
    wrap.append(head, body);
  } else {
    g.districts.forEach((d) => wrap.appendChild(renderDistrict(d)));
  }
  return wrap;
}

function attnChips(reasons, score) {
  const top = (reasons || []).slice(0, 2).map((r) => {
    const [label, tone] = ATTN_REASON[r] || [r, "r-low"];
    return `<span class="attn-chip ${tone}">${label}</span>`;
  }).join("");
  return `<span class="attn-score" title="attention: where your judgment moves us forward">${Math.round(score || 0)}</span>${top}`;
}

function renderDistrict(d) {
  const wrap = document.createElement("div"); wrap.className = "district";
  const head = document.createElement("div"); head.className = "district-head";
  const nces = d.nces_school_count != null ? ` · ${d.nces_school_count} sch` : "";
  const enr = d.enrollment_k12 ? ` · ${d.enrollment_k12.toLocaleString()} enr` : "";
  const flagged = d.n_flagged ? ` <span class="dist-flag" title="${d.n_flagged} open follow-up flag(s)">⚑${d.n_flagged}</span>` : "";
  head.innerHTML = `<div class="district-main">
      <div class="district-name">${d.name}${flagged}</div>
      <div class="district-meta">${d.state} · ${d.n_unlabeled}/${d.n_records} unlabeled${nces}${enr}</div>
      <div class="attn-row">${attnChips(d.attention_reasons, d.attention_score)}</div></div>
    <button class="dist-flagbtn btn btn-ghost" title="flag this district for follow-up">⚑</button>`;
  const ul = document.createElement("ul"); ul.className = "rec-list";

  const clusters = {};
  d.records.forEach((r) => {
    if (!r.cluster_id) return;
    (clusters[r.cluster_id] ||= { rep: null, members: [] });
    if (r.is_cluster_rep) clusters[r.cluster_id].rep = r;
    else clusters[r.cluster_id].members.push(r);
  });
  const seen = new Set();
  d.records.forEach((r) => {
    if (!r.cluster_id) { ul.appendChild(renderRecRow(r)); return; }
    if (seen.has(r.cluster_id)) return;
    seen.add(r.cluster_id);
    ul.appendChild(renderCluster(clusters[r.cluster_id]));
  });

  head.querySelector(".dist-flagbtn").onclick = (e) => { e.stopPropagation(); flagTarget("district", d.district_id, d.name); };
  head.onclick = () => ul.classList.toggle("hidden");
  wrap.append(head, ul);
  return wrap;
}

function renderCluster(c) {
  const rep = c.rep || c.members[0];
  const li = renderRecRow(rep, c.members.length + 1);   // representative row, with +N badge
  const sub = document.createElement("ul"); sub.className = "rec-list cluster-members hidden";
  c.members.forEach((m) => sub.appendChild(renderRecRow(m)));
  li.appendChild(sub);
  const badge = li.querySelector(".cluster-badge");
  if (badge) badge.onclick = (e) => { e.stopPropagation(); sub.classList.toggle("hidden"); li.classList.toggle("expanded"); };
  return li;
}

function renderRecRow(r, clusterSize) {
  const li = document.createElement("li");
  const status = r.label_status || r.status || "unlabeled";   // faceted endpoint -> label_status
  li.className = "rec-row" + (clusterSize > 1 ? " cluster-rep" : "");
  li.dataset.recKey = r.rec_key;
  const tail = (r.url || "").replace(/^https?:\/\//, "").slice(0, 32);
  const badge = clusterSize > 1
    ? `<span class="cluster-badge" title="${clusterSize - 1} near-duplicate(s) — click to expand">+${clusterSize - 1}</span>` : "";
  const emergent = r.is_emergent ? `<span class="emergent-dot" title="emergent — captured but not a planned candidate">⚡</span>` : "";
  // the record's dominant attention reason as a tiny dot-chip (the per-URL rationale)
  const reason = (r.attention_reasons || [])[0];
  const rchip = reason && reason !== "resolved" && reason !== "low_signal"
    ? `<span class="rec-attn ${(ATTN_REASON[reason] || ["", "r-low"])[1]}" title="${(ATTN_REASON[reason] || [reason])[0]}"></span>` : "";
  li.innerHTML = `<span class="tier ${r.tier}">${r.tier}</span>
    <span class="rec-label" title="${r.url}">${tail}</span>
    ${emergent}${rchip}${badge}<span class="status-dot ${status}"></span>
    <button class="rec-flagbtn" title="flag this URL for follow-up">⚑</button>`;
  li.onclick = (e) => { e.stopPropagation(); selectRecord(r.rec_key, li); };
  li.querySelector(".rec-flagbtn").onclick = (e) => { e.stopPropagation(); flagTarget("record", r.rec_key, tail); };
  return li;
}

// ----------------------------- follow-up flag + saved views -----------------------------
async function flagTarget(scope, target_id, label) {
  const directive = prompt(`Flag this ${scope} for follow-up — what should be done?\n(${label})`, "");
  if (directive === null) return;   // cancelled
  try {
    await fetch("/api/followup", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope, target_id, directive, actor: "ian" }) });
  } catch (e) { alert("Couldn't flag: " + e.message); return; }
  loadTree();   // attention changed server-side -> the flagged item jumps to the top
}

async function populateViewSelect(sel) {
  if (!sel) return;
  let views = [];
  try { views = await (await fetch("/api/views?actor=ian")).json(); } catch (_) {}
  views.forEach((v) => { const o = document.createElement("option"); o.value = v.id; o.textContent = v.name; o.dataset.config = JSON.stringify(v.config); sel.appendChild(o); });
  sel.onchange = () => {
    const opt = sel.selectedOptions[0];
    if (!opt || !opt.value) return;
    VIEW = { ...DEFAULT_VIEW, ...JSON.parse(opt.dataset.config || "{}") };
    persistView(); loadTree();
  };
}
async function saveCurrentView() {
  const name = prompt("Save this view as:", "");
  if (!name) return;
  try {
    await fetch("/api/views", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, config: VIEW, actor: "ian" }) });
  } catch (e) { alert("Couldn't save view: " + e.message); return; }
  loadTree();
}

// ----------------------------- center: representations -----------------------------
async function selectRecord(recKey, li) {
  CURRENT = recKey;
  document.querySelectorAll(".rec-row.active").forEach((x) => x.classList.remove("active"));
  if (li) li.classList.add("active");
  DATA = await (await fetch(`/api/record/${recKey}`)).json();
  await renderCenter(DATA);
  renderPanel(DATA);
}

async function renderCenter(d) {
  const c = $("#center");
  const s = d.signals;
  const chips = [`<span class="chip">tier ${d.tier}</span>`, `<span class="chip">${d.kind || "?"}</span>`];
  if (d.duplicate_of) chips.push(`<span class="chip dup">duplicate — <a href="#" data-go="${d.duplicate_of}">open canonical</a></span>`);
  if (s.visual_text_gap) chips.push(`<span class="chip warn">inspect visually — possible missed content</span>`);

  let html = `<div class="rec-header"><h2>${d.url.replace(/^https?:\/\//, "").slice(0, 70)}</h2>
    <div class="rec-url">${d.final_url || d.url}</div><div class="chips">${chips.join("")}</div></div>`;

  const reps = d.representations;
  const visual = reps.filter((r) => r.file_kind === "image" || r.file_kind === "pdf");
  const texts = reps.filter((r) => r.file_kind === "text" && r.usable);
  const emptyTexts = reps.filter((r) => r.file_kind === "text" && !r.usable);

  // Visual first (so the eye lands on ground truth before possibly-lossy text).
  visual.forEach((r) => {
    const url = fileUrl(d, r.filename);
    const body = r.file_kind === "pdf"
      ? `<iframe src="${url}" title="${r.filename}"></iframe>`
      : `<img src="${url}" alt="${r.filename}" loading="lazy" />`;
    html += card(`${r.source} · ${r.filename}`, "", body);
  });

  // Per-page n_times (handbook-harvest signal) if a multi-page PDF.
  if (s.pages && s.pages.length > 1) {
    const harvest = new Set(s.harvest_pages || []);
    const rows = s.pages.map((p) => `<tr><td>${harvest.has(p.page) ? "★ " : ""}p${p.page}</td><td class="${harvest.has(p.page) ? "hot" : (p.n_times >= 8 ? "hot" : "")}">${p.n_times} times</td></tr>`).join("");
    const meta = s.harvest_pages && s.harvest_pages.length
      ? `${s.is_handbook ? "handbook · " : ""}harvest p${s.harvest_pages.join(", p")} → council (not the whole doc)`
      : (s.is_handbook ? "handbook — no schedule page stood out" : "high-count pages are likely the schedule page");
    html += card("Per-page time counts (handbook harvest)", meta, `<table class="pages-table">${rows}</table>`);
  }

  // Text reps (best open). Content fetched lazily.
  texts.sort((a, b) => (b.n_times || 0) - (a.n_times || 0));
  for (let i = 0; i < texts.length; i++) {
    const r = texts[i];
    const open = i === 0 ? "open" : "";
    html += `<details ${open} data-file="${r.filename}"><summary>${r.source} — ${r.n_times} times, ${r.n_chars} chars</summary>
      <pre class="text" data-target="${r.filename}">loading…</pre></details>`;
  }
  if (emptyTexts.length) html += `<div class="chip">${emptyTexts.length} below-bar/empty text rep(s) not shown</div>`;

  c.innerHTML = html;
  c.querySelectorAll("[data-go]").forEach((a) => a.onclick = (e) => { e.preventDefault(); selectRecord(a.dataset.go); });
  // lazy-load text bodies
  c.querySelectorAll("pre.text").forEach(async (pre) => {
    const r = await fetch(fileUrl(d, pre.dataset.target));
    pre.textContent = (await r.text()).slice(0, 20000) || "(empty)";
  });
}

function card(head, meta, body) {
  return `<div class="card"><div class="card-head"><span>${head}</span><span class="meta">${meta}</span></div>
    <div class="card-body">${body}</div></div>`;
}

// ----------------------------- right: signals + labeling -----------------------------
function renderPanel(d) {
  const s = d.signals, lab = d.label || {};
  const kw = (arr) => arr && arr.length ? arr.join(", ") : "—";
  const neg = s.negative_kw || {};
  const sig = `<div class="sig-grid">
    <span class="k">tier</span><span class="v">${d.tier}</span>
    <span class="k">times (total / in-window)</span><span class="v">${s.n_times} / ${s.n_times_in_window}</span>
    <span class="k">proximity pairs</span><span class="v">${s.proximity_pairs}</span>
    <span class="k">times after 5pm</span><span class="v">${s.times_after_5pm}</span>
    <span class="k">instructional-time phrase</span><span class="v">${s.instructional_time ? "yes" : "no"}</span>
    <span class="k">real table present</span><span class="v">${s.has_table ? "yes" : "no"}</span>
    <span class="k">period-table hits</span><span class="v">${s.period_hits}</span>
    <span class="k">roster school names hit</span><span class="v">${s.roster_school_names_hit}</span>
    <span class="k">visual/text gap</span><span class="v">${s.visual_text_gap ? "yes" : "no"}</span>
  </div>
  <div class="sig-kw"><b>positive kw:</b> ${kw(s.positive_kw)}</div>
  <div class="sig-kw"><b>negative:</b> board ${kw(neg.board)} · sports ${kw(neg.sports)} · calendar ${kw(neg.calendar)} · transport ${kw(neg.transport)}</div>`;

  const flags = JSON.parse(lab.flags_json || "[]");
  if (d.duplicate_of && !flags.includes("duplicate")) flags.push("duplicate");

  const radios = (list) => list.map(([v, t]) =>
    `<label class="radio-row"><input type="radio" name="primary" value="${v}" ${lab.primary_label === v ? "checked" : ""}/>
     <span>${t}</span></label>`).join("");
  const checks = FLAGS.map(([v, t]) =>
    `<label class="check-row"><input type="checkbox" name="flag" value="${v}" ${flags.includes(v) ? "checked" : ""}/>
     <span>${t}</span></label>`).join("");

  $("#panel").innerHTML = `
    ${provenanceBlock(d)}
    ${clusterBanner(d)}
    <div class="panel-section"><h3>Signals <span style="font-weight:400;font-size:var(--fs-xs);color:var(--text-secondary)">(objective)</span></h3>${sig}</div>
    <div class="panel-section"><h3>Label <span id="savedFlash" class="saved-flash"></span></h3>
      <div class="axis-label">Target present — by shape</div>${radios(TARGET)}
      <label class="check-row special"><input type="checkbox" name="flag" value="${IMAGE_ONLY[0]}" ${flags.includes(IMAGE_ONLY[0]) ? "checked" : ""}/>
        <span>${IMAGE_ONLY[1]}</span></label>
      <div class="axis-label">Non-target — by reason</div>${radios(NONTARGET)}
      <div class="axis-label">Flags</div>${checks}
      <div class="axis-label">Note (optional)</div>
      <textarea class="note" placeholder="anything worth recording…">${lab.note || ""}</textarea>
      <div class="btn-row"><button id="unsureBtn" class="btn btn-secondary">Mark reviewed — unsure</button></div>
      <div id="guess" class="guess"></div>
    </div>`;

  $("#panel").querySelectorAll('input[name="primary"]').forEach((el) => el.onchange = () => save("labeled"));
  $("#panel").querySelectorAll('input[name="flag"]').forEach((el) => el.onchange = () => save(currentStatus()));
  $("#panel .note").onblur = () => save(currentStatus());
  $("#unsureBtn").onclick = () => save("unsure");
  $("#panel").querySelectorAll("[data-go]").forEach((a) => a.onclick = (e) => { e.preventDefault(); selectRecord(a.dataset.go); });
  $("#panel").querySelectorAll("[data-split]").forEach((b) => b.onclick = (e) => { e.preventDefault(); splitRecord(b.dataset.split); });
  renderGuess(d, lab.status);
}

// Provenance: where this record came from in the funnel (Stage-2 candidate → school, or emergent).
function provenanceBlock(d) {
  const tools = (d.candidate_tools || []).join(", ");
  if (d.is_emergent) {
    return `<div class="panel-section provenance emergent"><div class="axis-label">Provenance</div>
        <div><b>⚡ Emergent</b> — captured but never a planned candidate (discovered during capture, not tied to a targeted school).</div></div>`;
  }
  const sch = d.intended_schools || [];
  if (!sch.length) return "";
  return `<div class="panel-section provenance"><div class="axis-label">Provenance</div>
      <div>Intended for: <b>${sch.join(", ")}</b>${tools ? ` · found via ${tools}` : ""}</div></div>`;
}

// Near-duplicate cluster banner: shows the cascade relationship + per-member split control.
function clusterBanner(d) {
  if (!d.cluster_id) return "";
  const n = d.cluster_size, members = d.cluster_members || [];
  const rep = members.find((m) => m.is_cluster_rep);
  const head = d.is_cluster_rep
    ? `<b>Cluster representative</b> · ${n - 1} near-duplicate${n - 1 === 1 ? "" : "s"}. Labeling this <b>cascades to all members</b>.`
    : `<b>Cluster member</b> — label inherited from representative ${rep ? `<a href="#" data-go="${rep.rec_key}">★ ${short(rep.url)}</a>` : ""}.`;
  const rows = members.map((m) => {
    const cur = m.rec_key === d.rec_key ? " cur" : "";
    return `<div class="cl-member${cur}">
        <a href="#" data-go="${m.rec_key}" class="cl-link" title="${m.url}">${m.is_cluster_rep ? "★ " : ""}${short(m.url)}</a>
        <button class="btn btn-ghost cl-split" data-split="${m.rec_key}" title="this one's genuinely unique — pull it out of the cluster">split out</button>
      </div>`;
  }).join("");
  return `<div class="panel-section cluster-banner"><div class="axis-label">Near-duplicate cluster (${n})</div>
      <div class="cl-head">${head}</div><div class="cl-members">${rows}</div>
      <div class="cl-hint">Clustered by content similarity. If a member is actually different, split it out — the split is durable (survives re-ingest).</div></div>`;
}

async function splitRecord(recKey) {
  await fetch(`/api/split/${recKey}`, { method: "POST" });
  await loadTree();             // cluster membership changed — rebuild the tree
  await selectRecord(recKey);   // reselect the now-standalone record
}

function currentStatus() {
  // keep existing status if already set, else 'labeled' once a primary is chosen
  if (DATA.label && DATA.label.status && DATA.label.status !== "unlabeled") return DATA.label.status;
  return $('input[name="primary"]:checked') ? "labeled" : "unlabeled";
}

function renderGuess(d, status) {
  const g = $("#guess");
  if (!status || status === "unlabeled") {
    g.className = "guess guess-hidden";
    g.textContent = "Script's category guess is hidden until you label — keeps your judgment independent. (Itching to peek? Time for a break.)";
    return;
  }
  g.className = "guess";
  const chosen = $('input[name="primary"]:checked')?.value;
  const guess = d.category_hypothesis;
  const agree = chosen && chosen === guess;
  g.innerHTML = `Script guessed: <b>${guess}</b> ` +
    (chosen ? (agree ? `<span class="agree">✓ matches your label</span>` : `<span class="disagree">≠ your label (${chosen})</span>`)
            : `<span class="guess-hidden">(no primary label chosen)</span>`);
}

async function save(status) {
  if (!CURRENT) return;
  const primary = $('input[name="primary"]:checked')?.value || null;
  const flags = [...$("#panel").querySelectorAll('input[name="flag"]:checked')].map((e) => e.value);
  const note = $("#panel .note").value;
  const finalStatus = status === "unsure" ? "unsure" : (primary ? "labeled" : "unlabeled");
  await fetch(`/api/label/${CURRENT}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ primary_label: primary, flags, note, status: finalStatus }),
  });
  DATA.label = { primary_label: primary, flags_json: JSON.stringify(flags), note, status: finalStatus };
  flash();
  renderGuess(DATA, finalStatus);
  // update tree dot + progress
  const dot = document.querySelector(`.rec-row[data-rec-key="${CURRENT}"] .status-dot`);
  if (dot) dot.className = `status-dot ${finalStatus}`;
  refreshProgress();
}

let flashT;
function flash() { const f = $("#savedFlash"); if (!f) return; f.textContent = "saved"; clearTimeout(flashT); flashT = setTimeout(() => (f.textContent = ""), 1200); }

async function refreshProgress() {
  const p = await (await fetch("/api/progress")).json();
  $("#progress").textContent = `${p.labeled} / ${p.total} labeled`;
}

// ----------------------------- glossary -----------------------------
function buildGlossary() {
  const dl = (pairs) => "<dl>" + pairs.map(([k]) => `<dt>${k}</dt><dd>${DEFS[k]}</dd>`).join("") + "</dl>";
  $("#glossaryBody").innerHTML = `
    <p>Label what each captured artifact <b>actually contains</b>. Your labels are the ground truth we use to
       build the deterministic Stage 5 filters — so judge the artifact yourself; the script's category guess
       stays hidden until you've labeled, on purpose.</p>
    <h4>Workflow</h4>
    <ul><li>Left: districts → records, sorted by likelihood tier. Center: every representation (visual first).
      Right: the objective signals and your label controls.</li>
      <li>Pick <b>one primary label</b> (the dominant content) + any <b>flags</b>. Add a note if useful. Autosaves.</li>
      <li>Not sure? “Mark reviewed — unsure” records that you looked but couldn't decide (distinct from un-reviewed).</li>
      <li>Duplicates are pre-flagged and link to the canonical — label the canonical once.</li></ul>
    <h4>Likelihood tiers (script-assigned, sortable)</h4>
    <dl>${Object.entries(TIER_DEF).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    <h4>Primary labels — target present</h4>${dl(TARGET)}
    <h4>Primary labels — non-target</h4>${dl(NONTARGET)}
    <h4>Flags</h4>${dl([...FLAGS, IMAGE_ONLY])}`;
}

$("#glossaryBtn").onclick = () => $("#glossary").classList.remove("hidden");
$("#glossaryClose").onclick = () => $("#glossary").classList.add("hidden");
$("#glossary").onclick = (e) => { if (e.target.id === "glossary") $("#glossary").classList.add("hidden"); };

buildGlossary();
// Initial Stage-5 load is driven by gate1.js's applyView() (it calls window.loadStage5 on show),
// so the tree re-fetches every time you switch back to Stage 5 — no stale list (the batch_00007
// gap). If Stage 5 isn't the initially-selected view, applyView loads it on first show.
