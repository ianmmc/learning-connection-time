"use strict";

// ---- v2.1 taxonomy (single source for the UI; mirrors STAGE5_FILTER_DESIGN §4) ----
// AXIS 1 (radio, pick one): the target's SHAPE — each derives minutes + routes to Stage 6/7 differently.
const TARGET = [
  ["school_start_end_list", "Single school — start/end (list/footer, e.g. “Hours: 8:30–3:30”)"],
  ["school_bell_table", "Single school — bell schedule table (Period 1…N)"],
  ["school_start_end_prose", "Single school — start/end in prose"],
  ["district_hub_by_school", "District hub — start/end by school"],
  ["district_hub_by_band", "District hub — start/end by grade band"],
  ["explicit_instructional_time", "Explicit instructional minutes (e.g. “147 days × 7.5 hrs”)"],
  ["target_other_shape", "Target info — un-enumerated shape"],
];
// AXIS 1 terminals: no target here, or unreadable.
const TERMINAL = [
  ["target_absent", "Target information NOT present"],
  ["unusable", "Unusable — can’t interpret (garbled / empty)"],
];
// AXIS 2 (checkboxes, multi): confounding signals PRESENT — usable whether or not a target is present,
// and the ground truth for the negative detectors. `det` = the detector whose firing hints "check this."
const CONFOUNDERS = [
  ["board", "School Board / Trustees", "lf_board"],
  ["sports", "Athletics / sports", "lf_sports"],
  ["academic_calendar", "Academic calendar", "lf_calendar_widget"],
  ["community_calendar", "Community / events calendar", "lf_calendar_widget"],
  ["transportation", "Bus / transportation", "lf_transport"],
  ["news_feed", "News / social feed", "lf_news_feed"],
  ["office_building_hours", "Building / office hours (not the student day)", "lf_office_hours"],
];
// AXIS 3 (checkboxes): where the target hides / how to read it. `sig` = the signal that hints it.
const LOCATION = [
  ["buried_handbook", "Buried in a long doc (handbook)", "is_handbook"],
  ["needs_vision", "Visible in image/PDF but missing from ALL text — needs vision", "visual_text_gap"],
];
const FACET_WHERE = ["", "main body", "footer", "header", "table", "image/PDF", "feed post", "multiple"];
const DEFS = {
  school_start_end_list: "A single school's start/end shown as a labeled item/range (e.g. a footer “Hours: 8:30–3:30”), not a sentence and not a period table.",
  school_bell_table: "A single school's period table (Period 1…N). School start = start of the first instructional period; end = end of the last.",
  school_start_end_prose: "A single school's start/end declared in a sentence (“The school day starts at 8:30 and ends at 3:30…”).",
  district_hub_by_school: "A table/list giving start & end times for each named school in the district (may appear on a district page or repeated across school feeds).",
  district_hub_by_band: "Start & end times by grade band (“Elementary 8:30–3:30; Middle 8:15–3:45; High 8:00–4:00”).",
  explicit_instructional_time: "A declaration like “Students receive XXX minutes of instruction every day” (or hours/day).",
  target_other_shape: "Bell-schedule / instructional-time info in a shape we haven't enumerated.",
  target_absent: "No student start/end, bell schedule, or instructional-time declaration is present.",
  unusable: "Garbled, effectively empty, or impossible for a human to interpret.",
  // confounders (Axis 2) — things that generate confusing signals; check any that are present.
  board: "School Board / Trustees agenda or meeting content.",
  sports: "Athletics / sports scheduling.",
  academic_calendar: "A school/district calendar (year, holidays, early-release) — time-bearing but not a schedule.",
  community_calendar: "A community / events calendar — not the academic calendar, not a schedule.",
  transportation: "Bus / transport times.",
  news_feed: "A news / social-media feed whose post timestamps are spurious time signal.",
  office_building_hours: "Building/office hours (often a footer “Building Hours 7:15–3:15”) that mimic a start/end pair but are NOT the student day.",
  // location (Axis 3)
  buried_handbook: "The target is present but inside a long multi-topic document (e.g. a handbook) — record the page(s).",
  needs_vision: "You can see the target in the image/PDF, but NO text extractor captured it — needs vision at Stage 6/7.",
};
const TIER_DEF = {
  A: "Send — a real target shape (or a confident prose/table pair).",
  B: "Review — ambiguous target evidence; your call at gate@5.",
  C: "Review — negative-leaning but not confident.",
  D: "Suppress — no in-window times / a confident negative.",
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
  tiers: [], reasons: [], hide_resolved: false, lane: "", q: "" };
let VIEW = loadView();
let FACETS = null;

function loadView() {
  let v;
  try { v = { ...DEFAULT_VIEW, ...JSON.parse(localStorage.getItem("s5_view") || "{}") }; }
  catch (_) { v = { ...DEFAULT_VIEW }; }
  // Deep-linkable: ?group_by=…&sort=…&dir=… overrides (bookmarkable/shareable views).
  const q = new URLSearchParams(location.search);
  ["group_by", "sort", "dir", "label", "lane", "q"].forEach((k) => { if (q.has(k)) v[k] = q.get(k); });
  return v;
}
function persistView() { localStorage.setItem("s5_view", JSON.stringify(VIEW)); }

function viewQuery() {
  const p = new URLSearchParams();
  p.set("group_by", VIEW.group_by); p.set("sort", VIEW.sort); p.set("dir", VIEW.dir);
  if (VIEW.label) p.set("label", VIEW.label);
  (VIEW.tiers || []).forEach((t) => p.append("tier", t));
  (VIEW.reasons || []).forEach((r) => p.append("reason", r));
  if (VIEW.hide_resolved) p.set("hide_resolved", "true");
  if (VIEW.lane) p.set("lane", VIEW.lane);
  if (VIEW.q) p.set("q", VIEW.q);
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
  const selectFor = (id, map, cur) => `<select id="${id}" class="s5-select">` +
    Object.keys(map).map((k) => `<option value="${k}" ${k === cur ? "selected" : ""}>${map[k]}</option>`).join("") + `</select>`;
  const labelSeg = [["", "All"], ["unlabeled", "Unlabeled"], ["labeled", "Labeled"]].map(([v, t]) =>
    `<button class="seg-btn ${VIEW.label === v ? "on" : ""}" data-label="${v}">${t}</button>`).join("");
  const tierBtns = ["A", "B", "C", "D"].map((t) =>
    `<button class="tier-btn t-${t} ${VIEW.tiers.includes(t) ? "on" : ""}" data-tier="${t}">${t}</button>`).join("");
  const reasonChips = ((FACETS && FACETS.reason) || []).filter((r) => r.value).map((r) => {
    const [lab, tone] = ATTN_REASON[r.value] || [r.value, "r-low"];
    return `<button class="rsn-chip ${tone} ${VIEW.reasons.includes(r.value) ? "on" : ""}" data-reason="${r.value}" title="${r.count} records">${lab}</button>`;
  }).join("");
  // #516 error-review lanes: disagreement between the machine tier and the human label is the tuning
  // loop's fuel. FP = tier-A the human labeled absent (the money-leak queue); FN = the #211 reject-audit.
  const laneSeg = [["", "Off"], ["fp", "FP · money-leak"], ["fn", "FN · reject audit"]].map(([v, t]) =>
    `<button class="seg-btn lane-btn ${VIEW.lane === v ? "on" : ""}" data-lane="${v}">${t}</button>`).join("");
  const grouped = VIEW.group_by !== "none";

  bar.innerHTML = `
    <div class="s5-field"><span class="s5-lbl">Group</span>${selectFor("s5-group", GROUP_LABEL, VIEW.group_by)}</div>
    <div class="s5-field"><span class="s5-lbl">Sort</span>${selectFor("s5-sort", SORT_LABEL, VIEW.sort)}
      <button id="s5-dir" class="s5-iconbtn" title="ascending / descending">${VIEW.dir === "asc" ? "↑" : "↓"}</button></div>
    <div class="s5-filtrow">
      <div class="seg" role="group" aria-label="label status">${labelSeg}</div>
      <div class="tiers" role="group" aria-label="tier">${tierBtns}</div>
    </div>
    <div class="s5-filtrow s5-lanes">
      <span class="s5-lbl">Lane</span>
      <div class="seg" role="group" aria-label="error-review lane">${laneSeg}</div>
      <input id="s5-search" class="s5-search" type="search" placeholder="Find rec_key…" aria-label="search rec_key"/>
    </div>
    <div class="s5-filtrow s5-secondary">
      <label class="s5-toggle"><input type="checkbox" id="s5-hideres" ${VIEW.hide_resolved ? "checked" : ""}/> Hide resolved</label>
      ${grouped ? `<span class="s5-spacer"></span>
        <button id="s5-collapse" class="s5-link">Collapse all</button>
        <button id="s5-expand" class="s5-link">Expand all</button>` : ""}
    </div>
    ${reasonChips ? `<div class="s5-reasons">${reasonChips}</div>` : ""}
    <div class="s5-actions">
      <select id="s5-viewsel" class="s5-select s5-viewsel"><option value="">Saved views…</option></select>
      <button id="s5-viewsave" class="s5-btn">Save view</button>
      <span class="s5-count">${data.total_districts} district${data.total_districts === 1 ? "" : "s"}</span>
    </div>`;

  bar.querySelector("#s5-group").onchange = (e) => { VIEW.group_by = e.target.value; commitView(); };
  bar.querySelector("#s5-sort").onchange = (e) => { VIEW.sort = e.target.value; commitView(); };
  bar.querySelector("#s5-dir").onclick = () => { VIEW.dir = VIEW.dir === "asc" ? "desc" : "asc"; commitView(); };
  bar.querySelector("#s5-hideres").onchange = (e) => { VIEW.hide_resolved = e.target.checked; commitView(); };
  bar.querySelectorAll("[data-label]").forEach((b) => b.onclick = () => { VIEW.label = b.dataset.label; commitView(); });
  bar.querySelectorAll("[data-tier]").forEach((b) => b.onclick = () => { toggle(VIEW.tiers, b.dataset.tier); commitView(); });
  bar.querySelectorAll("[data-reason]").forEach((b) => b.onclick = () => { toggle(VIEW.reasons, b.dataset.reason); commitView(); });
  bar.querySelectorAll("[data-lane]").forEach((b) => b.onclick = () => { VIEW.lane = b.dataset.lane; commitView(); });
  const search = bar.querySelector("#s5-search");
  search.value = VIEW.q || "";                            // set as a property (never interpolated into HTML)
  search.onchange = () => { VIEW.q = search.value.trim(); commitView(); };   // commits on Enter/blur
  bar.querySelector("#s5-viewsave").onclick = saveCurrentView;
  if (grouped) {
    bar.querySelector("#s5-collapse").onclick = () => setAllGroups(true);
    bar.querySelector("#s5-expand").onclick = () => setAllGroups(false);
  }
  populateViewSelect(bar.querySelector("#s5-viewsel"));
  return bar;
}
function toggle(arr, v) { const i = arr.indexOf(v); if (i < 0) arr.push(v); else arr.splice(i, 1); }
function commitView() { persistView(); loadTree(); }
function setAllGroups(collapsed) {
  document.querySelectorAll("#s5-list .s5-group-body").forEach((b) => b.classList.toggle("hidden", collapsed));
  document.querySelectorAll("#s5-list .s5-caret").forEach((c) => c.textContent = collapsed ? "▸" : "▾");
}

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
    <button class="dist-resetbtn btn btn-ghost" title="reset ALL labels in this district back to unlabeled (#228)">⟲</button>
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
  head.querySelector(".dist-resetbtn").onclick = (e) => { e.stopPropagation(); resetLabels("district", d.district_id, d.name); };
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
  // Favor the DISTINGUISHING tail (path/page) over the shared domain prefix — records within a
  // district otherwise all read identically. Full URL stays on hover (title).
  const u = (r.url || "").replace(/^https?:\/\//, "").replace(/^www\./, "");
  const tail = u.length > 34 ? "…" + u.slice(-33) : u;
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

// #228 "Reset labels": return a record (or a whole district) to a truthful unlabeled state. Destructive
// to precious label state, so it CONFIRMS first. The motivating case is a valid schedule for the WRONG
// district (Millard's unscoped contamination, #227) — neither target_absent nor unusable is honest, so
// unlabeled is the only truthful label. A record-scope reset of a cluster rep reverses the cascade (its
// members reset too); a district-scope reset clears every record in the district.
async function resetLabels(scope, target_id, label) {
  const msg = scope === "district"
    ? `Reset ALL labels in this district back to unlabeled?\n(${label})\n\nClears primary + facets + note on every record — the truthful neutral state. Real DB change (the tracked labels.json backup updates too).`
    : `Reset this record's label back to unlabeled?\n(${label})\n\nClears primary + facets + note. If it's a cluster representative, its members reset too.`;
  if (!confirm(msg)) return;
  let resp;
  try {
    resp = await fetch("/api/reset-labels", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope, target_id, actor: "ian" }) });
  } catch (e) { alert("Couldn't reset labels: " + e.message); return; }
  if (!resp.ok) { alert(`Couldn't reset labels: HTTP ${resp.status}`); return; }   // destructive — don't fake success
  await loadTree();                                   // labels/topology/attention changed -> rebuild the tree
  // Re-render the open panel in its cleared state. For a record reset, re-select it (with its
  // rebuilt tree row, so the .active highlight survives loadTree — PR #242 review); for a district
  // reset, the open record may BELONG to that district (rec_key = "<district_id>:<hash>") and would
  // otherwise keep showing stale pre-reset label state.
  const reselect = scope === "record" ? target_id
    : (CURRENT && CURRENT.startsWith(target_id + ":") ? CURRENT : null);
  if (reselect) {
    await selectRecord(reselect, document.querySelector(`.rec-row[data-rec-key="${reselect}"]`));
  }
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

  // TEXT FIRST (REQ-114 v2.1): the council reads TEXT, so confirm the target appears in a text rep BEFORE
  // the image can anchor you into "checking it off". Footer/header/nav segments first (the common hours
  // spot); then the densest full text; then the rest — each annotated with what it uniquely adds (below).
  const segRank = { "segment:footer": 0, "segment:header": 1, "segment:nav": 2, "segment:main": 3 };
  const segs = texts.filter((r) => r.source.startsWith("segment:")).sort((a, b) => (segRank[a.source] ?? 9) - (segRank[b.source] ?? 9));
  const fulls = texts.filter((r) => !r.source.startsWith("segment:")).sort((a, b) => (b.n_times || 0) - (a.n_times || 0));
  const ordered = [...segs, ...fulls];
  html += `<p class="text-first-note">Text first — the council reads text, so confirm the target is in at least one
    <b>text</b> rep. Footer/header shown first (the common “Hours:” spot). If the target is <b>only</b> in the image/PDF below,
    tick <b>needs vision</b>.</p>`;
  ordered.forEach((r, i) => {
    const openSeg = r.source.startsWith("segment:footer") || r.source.startsWith("segment:header");
    const open = (openSeg || (segs.length === 0 && i === 0)) ? "open" : "";
    html += `<details ${open} data-file="${r.filename}" data-src="${r.source}">
      <summary><span class="rep-src">${r.source}</span><span class="rep-uniq" data-uniq="${r.filename}">·</span></summary>
      <pre class="text" data-target="${r.filename}">loading…</pre></details>`;
  });
  if (emptyTexts.length) html += `<div class="chip">${emptyTexts.length} below-bar/empty text rep(s) not shown</div>`;

  // Per-page n_times (handbook-harvest signal) if a multi-page PDF.
  if (s.pages && s.pages.length > 1) {
    const harvest = new Set(s.harvest_pages || []);
    const rows = s.pages.map((p) => `<tr><td>${harvest.has(p.page) ? "★ " : ""}p${p.page}</td><td class="${harvest.has(p.page) ? "hot" : (p.n_times >= 8 ? "hot" : "")}">${p.n_times} times</td></tr>`).join("");
    const meta = s.harvest_pages && s.harvest_pages.length
      ? `${s.is_handbook ? "handbook · " : ""}harvest p${s.harvest_pages.join(", p")} → council (not the whole doc)`
      : (s.is_handbook ? "handbook — no schedule page stood out" : "high-count pages are likely the schedule page");
    html += card("Per-page time counts (handbook harvest)", meta, `<table class="pages-table">${rows}</table>`);
  }

  // VISUAL LAST — for confirming structure / catching an image-only target (→ needs vision).
  visual.forEach((r) => {
    const url = fileUrl(d, r.filename);
    const body = r.file_kind === "pdf"
      ? `<iframe src="${url}" title="${r.filename}"></iframe>`
      : `<img src="${url}" alt="${r.filename}" loading="lazy" />`;
    html += card(`${r.source} · ${r.filename}`, "image/PDF — confirm the target also appears in a text rep above", body);
  });

  c.innerHTML = html;
  c.querySelectorAll("[data-go]").forEach((a) => a.onclick = (e) => { e.preventDefault(); selectRecord(a.dataset.go); });
  // Lazy-load text bodies, then compute the per-rep SIGNAL-LEVEL "unique contribution" (times in this rep
  // that the densest rep lacks) — so you never re-read a rep that adds nothing, but never miss one that does.
  const bodies = {};
  const W = await detectorWeights();   // #521: the relevance-density weight SSOT (fetched once, cached)
  await Promise.all([...c.querySelectorAll("pre.text")].map(async (pre) => {
    const r = await fetch(fileUrl(d, pre.dataset.target));
    const t = await r.text();
    bodies[pre.dataset.target] = t;
    // #521: a LONG rep gets relevance-density navigation (full text + heat-strip + ranked bookmarks) so a
    // schedule buried past the old ~20k display cap is reachable in relevance order; short reps already fit.
    if (t.length > DENSITY_MIN_CHARS) renderDensityNav(pre, t, s, W);
    else pre.textContent = t || "(empty)";
  }));
  annotateUniqueTimes(c, bodies, ordered);
}

// In-window (07:00–16:00) clock times in a text, as a set of canonical "h:mm(a/p)" strings.
function inWindowTimes(text) {
  const out = new Set();
  const re = /\b(\d{1,2}):(\d{2})\s*([ap])?\.?m?\.?/gi;
  let m;
  while ((m = re.exec(text))) {
    let h = +m[1]; const mm = +m[2]; const ap = (m[3] || "").toLowerCase();
    if (ap === "p" && h !== 12) h += 12; else if (ap === "a" && h === 12) h = 0;
    else if (!ap && h >= 1 && h <= 6) h += 12;
    if (h > 23 || mm > 59) continue;
    const mins = h * 60 + mm;
    if (mins >= 420 && mins <= 960) out.add(`${+m[1]}:${m[2]}${ap ? ap + "m" : ""}`);
  }
  return out;
}

// Annotate each text rep with the in-window times it has that the DENSEST rep lacks (or "⊆ densest").
function annotateUniqueTimes(c, bodies, ordered) {
  const timeSets = {};
  ordered.forEach((r) => { timeSets[r.filename] = inWindowTimes(bodies[r.filename] || ""); });
  let best = null, bestN = -1;
  ordered.forEach((r) => { const n = timeSets[r.filename].size; if (n > bestN) { bestN = n; best = r.filename; } });
  ordered.forEach((r) => {
    const el = c.querySelector(`.rep-uniq[data-uniq="${r.filename}"]`);
    if (!el) return;
    const mine = timeSets[r.filename], bestSet = timeSets[best] || new Set();
    const uniq = [...mine].filter((t) => !bestSet.has(t));
    if (r.filename === best) el.innerHTML = `<b>densest</b> · ${mine.size} in-window time(s)`;
    else if (uniq.length) el.innerHTML = `<span class="uniq-hot">+${uniq.length} time(s) not in densest: ${uniq.slice(0, 6).join(", ")}</span>`;
    else el.innerHTML = `<span class="uniq-sub">⊆ densest (nothing unique)</span>`;
  });
}

// ----------------------------- #521 relevance-density navigation -----------------------------
// A long rep is read in RELEVANCE order, not document order: project the SAME signed detector signals that
// scored the record onto the character axis, smooth into a density curve, and surface the peaks as ranked
// bookmarks + a heat-strip. Weights come from the server (/api/detector-weights — the ONE source, so the
// strip can never contradict the score); the keyword vocabulary is THIS record's own matched
// positive_kw/negative_kw (no drift); only stable code-constant regexes/lists are ported here.
let DWEIGHTS = null;
async function detectorWeights() {
  if (!DWEIGHTS) { try { DWEIGHTS = await (await fetch("/api/detector-weights")).json(); } catch (_) { DWEIGHTS = {}; } }
  return DWEIGHTS;
}

const DENSITY_MIN_CHARS = 20000;   // reps shorter than the old display cap already fit — no nav needed
const DN_RENDER_CAP = 1000000;     // hard ceiling on chars rendered into one <pre> (perf; realistic docs are far under)
const DN_PROXIMITY = 220, DN_WIN_LO = 420, DN_WIN_HI = 960;   // mirror build_signals PROXIMITY_CHARS / WINDOW
const DN_OFFICE_KW = ["office hours", "office is open", "main office", "front office", "staff hours",
  "staff day", "workday", "work day", "teacher hours", "building hours", "administrative"];
const DN_INSTRUCTIONAL = /(\d{2,4})\s*(?:minutes|mins)\s+(?:of|per)\s+(?:instruction|instructional|class|learning)|instructional\s+minutes|minutes\s+per\s+day|minutes\s+of\s+instruction/gi;
const DN_PERIOD = /\bperiod\s*\d|\b\d(?:st|nd|rd|th)\s+period/gi;
const DN_TYPE_LABEL = { proximity_pair: "start/end pair", table_times: "schedule table",
  instructional: "instructional minutes", in_window_time: "in-window times", positive_kw: "hours keyword" };
const dnEsc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// In-window (07:00–16:00) time offsets — the inWindowTimes regex/window, keeping m.index this time.
function dnTimeOffsets(text) {
  const re = /\b(\d{1,2}):(\d{2})\s*([ap])?\.?m?\.?/gi, out = []; let m;
  while ((m = re.exec(text))) {
    let h = +m[1]; const mm = +m[2], ap = (m[3] || "").toLowerCase();
    if (ap === "p" && h !== 12) h += 12; else if (ap === "a" && h === 12) h = 0;
    else if (!ap && h >= 1 && h <= 6) h += 12;
    if (h > 23 || mm > 59) continue;
    const mins = h * 60 + mm;
    if (mins >= DN_WIN_LO && mins <= DN_WIN_HI) out.push({ off: m.index, mins });
  }
  return out;
}
function dnAllIndexOf(hayLc, needle) {
  const n = (needle || "").toLowerCase(), out = [];
  if (!n) return out;
  let i = hayLc.indexOf(n);
  while (i !== -1) { out.push(i); i = hayLc.indexOf(n, i + n.length); }
  return out;
}

// Signed relevance events over one rep's full text. Keyword vocab = this record's own matched terms.
function dnEvents(text, sig, W) {
  const ev = [], lc = text.toLowerCase();
  const push = (off, type) => { const w = W[type]; if (w) ev.push({ off, type, weight: w.polarity * w.weight }); };
  const tps = dnTimeOffsets(text);
  tps.forEach((t) => push(t.off, "in_window_time"));
  for (let i = 0; i < tps.length; i++)
    for (let j = i + 1; j < tps.length && tps[j].off - tps[i].off <= DN_PROXIMITY; j++)
      if (tps[i].mins !== tps[j].mins) { push(tps[i].off, "proximity_pair"); break; }   // anchor on the first time (a real clock time for the bookmark)
  let m; DN_INSTRUCTIONAL.lastIndex = 0;
  while ((m = DN_INSTRUCTIONAL.exec(text))) push(m.index, "instructional");
  DN_PERIOD.lastIndex = 0;
  while ((m = DN_PERIOD.exec(text))) push(m.index, "table_times");
  (sig.positive_kw || []).forEach((k) => dnAllIndexOf(lc, k).forEach((o) => push(o, "positive_kw")));
  const neg = sig.negative_kw || {};
  ["board", "sports", "calendar", "transport"].forEach((cls) =>
    (neg[cls] || []).forEach((k) => dnAllIndexOf(lc, k).forEach((o) => push(o, cls))));
  DN_OFFICE_KW.forEach((k) => dnAllIndexOf(lc, k).forEach((o) => push(o, "office_hours")));
  return ev;
}

// Gaussian-smoothed signed density over the char axis (nbins), plus ranked positive peaks.
function dnCurve(events, length, nbins = 140) {
  const raw = new Float64Array(nbins);
  events.forEach((e) => { raw[Math.min(nbins - 1, Math.floor(e.off / length * nbins))] += e.weight; });
  const sigma = 1.6, radius = 5, ker = []; let ksum = 0;
  for (let k = -radius; k <= radius; k++) { const v = Math.exp(-(k * k) / (2 * sigma * sigma)); ker.push(v); ksum += v; }
  const sm = new Float64Array(nbins);
  for (let i = 0; i < nbins; i++) {
    let acc = 0;
    for (let k = -radius; k <= radius; k++) { const j = i + k; if (j >= 0 && j < nbins) acc += raw[j] * ker[k + radius]; }
    sm[i] = acc / ksum;
  }
  let maxPos = 0, maxAbs = 1e-9;
  for (let i = 0; i < nbins; i++) { if (sm[i] > maxPos) maxPos = sm[i]; if (Math.abs(sm[i]) > maxAbs) maxAbs = Math.abs(sm[i]); }
  const peaks = [], floor = maxPos * 0.25;
  for (let i = 0; i < nbins; i++) {
    const l = i === 0 ? -Infinity : sm[i - 1], r = i === nbins - 1 ? -Infinity : sm[i + 1];
    if (sm[i] > 0 && sm[i] >= floor && sm[i] > l && sm[i] >= r)
      peaks.push({ bin: i, height: sm[i], off: Math.round((i + 0.5) / nbins * length) });
  }
  peaks.sort((a, b) => b.height - a.height);
  return { sm, peaks, maxAbs };
}

// The strongest POSITIVE event near a peak's bin centre — the bookmark focuses on IT (a proximity pair /
// time), so the chip snippet + anchor + scroll land on the schedule signal itself, not the smoothed centre.
function dnPeakFocus(events, binOff, win) {
  let best = null;
  events.forEach((e) => { if (e.weight > 0 && Math.abs(e.off - binOff) <= win && (!best || e.weight > best.weight)) best = e; });
  return best || { off: binOff, type: null };
}
function dnSnippet(text, off, span = 52) {
  const s = Math.max(0, off - Math.floor(span / 2));
  return text.slice(s, s + span).replace(/\s+/g, " ").trim();
}
// Full-text HTML with a thin anchor marker (▎) at each bookmark offset; text escaped in slices between them.
function dnAnchoredHtml(text, marks) {
  const parts = []; let prev = 0;
  marks.forEach((mk) => {
    const o = Math.max(prev, Math.min(mk.off, text.length));
    parts.push(dnEsc(text.slice(prev, o)));
    parts.push(`<span class="bm-anchor" id="${mk.id}" title="relevance peak">▎</span>`);
    prev = o;
  });
  parts.push(dnEsc(text.slice(prev)));
  return parts.join("");
}

// Render the relevance-density nav (heat-strip + ranked bookmarks) above a long rep's <pre>, fill the <pre>
// with FULL text + peak anchors. The <pre> is itself the scroll container (.text max-height), so bookmarks
// set pre.scrollTop to the anchor and the strip scrolls proportionally — no ancestor-scroll math.
function renderDensityNav(pre, text, sig, W) {
  const truncated = text.length > DN_RENDER_CAP;
  if (truncated) text = text.slice(0, DN_RENDER_CAP);
  const events = dnEvents(text, sig, W);
  const { sm, peaks, maxAbs } = dnCurve(events, text.length);
  const win = text.length / sm.length * 1.5;
  const top = peaks.slice(0, 8).map((p, rank) => {
    const f = dnPeakFocus(events, p.off, win);
    return { rank, off: f.off, id: `bm-${pre.dataset.target}-${rank}`,
      label: DN_TYPE_LABEL[f.type] || "times", snippet: dnSnippet(text, f.off) };
  });
  pre.innerHTML = dnAnchoredHtml(text, [...top].sort((a, b) => a.off - b.off));   // anchors in ascending order for slicing
  const cell = (v) => {
    const a = Math.min(1, Math.abs(v) / maxAbs);
    if (a < 0.02) return `<div class="dn-cell"></div>`;
    const rgb = v >= 0 ? "26,127,55" : "200,40,40";
    return `<div class="dn-cell" style="background:rgba(${rgb},${(0.12 + 0.78 * a).toFixed(3)})"></div>`;
  };
  const chips = top.length
    ? top.map((b) => `<button class="dn-chip" data-bm="${b.id}" title="${dnEsc(b.snippet)}">` +
        `<span class="dn-rank">${b.rank + 1}</span>${dnEsc(b.snippet) || "(peak)"} <span class="dn-lbl">· ${b.label}</span></button>`).join("")
    : `<span class="dn-note">no relevance peak stood out — read top-to-bottom</span>`;
  const nav = document.createElement("div");
  nav.className = "dn";
  nav.innerHTML = `<div class="dn-strip" title="relevance density — click to jump">${Array.from(sm, cell).join("")}</div>
    <div class="dn-bmk">${chips}</div>
    <div class="dn-note">Relevance order, not page order — ${Math.round(text.length / 1000)}k chars${truncated ? " (truncated at 1M)" : ""}; green = schedule-like, red = confounder.</div>`;
  pre.parentNode.insertBefore(nav, pre);
  const flashTo = (id) => {
    const a = pre.querySelector(`#${CSS.escape(id)}`);
    if (!a) return;
    pre.scrollTop = Math.max(0, a.offsetTop - pre.clientHeight / 2);
    a.classList.remove("bm-flash"); void a.offsetWidth; a.classList.add("bm-flash");
  };
  nav.querySelectorAll("[data-bm]").forEach((c) => c.onclick = () => flashTo(c.dataset.bm));
  nav.querySelector(".dn-strip").onclick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    pre.scrollTop = frac * (pre.scrollHeight - pre.clientHeight);
  };
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

  // v2.1 label state: the stored facets (Axis 2 confounders + Axis 3 location + where/pages) and the set
  // of detectors that fired here (used only as a "flagged" HINT next to a facet — never auto-persisted).
  const savedFacets = JSON.parse(lab.facets_json || "{}");
  const fired = new Set(((d.signals && d.signals.detectors) || []).map((v) => v.name));
  // AXIS 1 — the target shape (radio), plus the terminals.
  const radios = (list) => list.map(([v, t]) =>
    `<label class="radio-row"><input type="radio" name="primary" value="${v}" ${lab.primary_label === v ? "checked" : ""}/>
     <span>${t}</span></label>`).join("");
  // AXIS 3 — location facets (checkbox + a detector/signal HINT that does NOT auto-persist — the human decides).
  const check = (id, t, flagged) => `<label class="conf-row ${savedFacets[id] === "yes" ? "on" : ""}">
      <input type="checkbox" name="facet" value="${id}" ${savedFacets[id] === "yes" ? "checked" : ""}/>
      <span>${t}</span>${flagged ? `<em class="det-hint" title="a signal/detector flagged this — confirm or ignore">flagged</em>` : ""}</label>`;
  const locChecks = LOCATION.map(([id, t, sigKey]) => check(id, t, !!(d.signals || {})[sigKey])).join("");
  const whereSel = `<select id="facetWhere" class="facet-where">${
    FACET_WHERE.map((w) => `<option value="${w}" ${savedFacets._where === w ? "selected" : ""}>${w || "where? (optional)"}</option>`).join("")}</select>`;
  const pageInput = `<input id="facetPage" class="facet-page" type="text" placeholder="pages, e.g. 4, 7-9" value="${savedFacets._pages || ""}"/>`;
  // AXIS 2 — confounders (checkbox multi-select; a fired negative detector HINTS but doesn't check it).
  const confChecks = CONFOUNDERS.map(([id, t, det]) => check(id, t, fired.has(det))).join("");

  // #516 order (Ian 2026-07-15): the LABEL controls (the decision) come first; the cluster banner stays
  // above them (a cascade warning to see BEFORE labeling); provenance + the objective Signals block (the
  // in-window-times "windows" readout) drop BELOW — reference, not decision inputs.
  $("#panel").innerHTML = `
    ${clusterBanner(d)}
    <div class="panel-section"><h3>Label <span id="savedFlash" class="saved-flash"></span></h3>
      <div class="axis-label">Target shape — pick one</div>${radios(TARGET)}
      <div class="loc-cluster">
        <div class="axis-label sub">Where / how (if a target is present)</div>
        ${locChecks}
        <div class="facet-extra">${whereSel}${pageInput}</div>
      </div>
      ${radios(TERMINAL)}
      <div class="axis-label">Confounding signals present — check all that apply</div>${confChecks}
      <div class="axis-label">Note (optional)</div>
      <textarea class="note" placeholder="anything worth recording…">${lab.note || ""}</textarea>
      <div class="btn-row"><button id="unsureBtn" class="btn btn-secondary">Mark reviewed — unsure</button>
        <button id="resetLabelBtn" class="btn btn-ghost" title="clear this label back to unlabeled (reverses any cluster cascade) — #228">Reset label</button></div>
      <div id="guess" class="guess"></div>
    </div>
    ${provenanceBlock(d)}
    <div class="panel-section"><h3>Signals <span style="font-weight:400;font-size:var(--fs-xs);color:var(--text-secondary)">(objective)</span></h3>${sig}</div>`;

  $("#panel").querySelectorAll('input[name="primary"]').forEach((el) => el.onchange = () => save("labeled"));
  $("#panel").querySelectorAll('input[name="facet"]').forEach((el) => el.onchange = () => save(currentStatus()));
  $("#panel .note").onblur = () => save(currentStatus());
  const fw = $("#facetWhere"); if (fw) fw.onchange = () => save(currentStatus());
  const fp = $("#facetPage"); if (fp) fp.onblur = () => save(currentStatus());
  $("#unsureBtn").onclick = () => save("unsure");
  // the confirm() shows `label` to the human — pass the URL, not the opaque rec_key (PR #242 review)
  $("#resetLabelBtn").onclick = () => resetLabels("record", CURRENT, (DATA && DATA.url) || CURRENT);
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

// Parse print-dialog page syntax ("4, 7-9, 12") -> a sorted unique page list [4,7,8,9,12]. Tolerant of junk.
function parsePages(s) {
  const out = new Set();
  for (const part of (s || "").split(",")) {
    const m = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
    if (!m) continue;
    const a = +m[1], b = m[2] ? +m[2] : a;
    for (let i = Math.min(a, b); i <= Math.max(a, b); i++) out.add(i);
  }
  return [...out].sort((x, y) => x - y);
}

function collectFacets() {
  // Axis 2 + Axis 3 are checkboxes → each CHECKED one is stored "yes" (present); unchecked = absent (omitted).
  // Only human checks persist (a "flagged" hint never auto-persists). Plus the structured where + page range
  // (raw string kept for what you typed; parsed list for the harvester — the guessed-vs-labeled pattern).
  const facets = {};
  document.querySelectorAll('#panel input[name="facet"]:checked').forEach((e) => { facets[e.value] = "yes"; });
  const w = $("#facetWhere"); if (w && w.value) facets._where = w.value;
  const p = $("#facetPage"); if (p && p.value.trim()) { facets._pages = p.value.trim(); facets._pages_list = parsePages(p.value); }
  return facets;
}

async function save(status) {
  if (!CURRENT) return;
  const primary = $('input[name="primary"]:checked')?.value || null;
  const note = $("#panel .note").value;
  const facets = collectFacets();
  const finalStatus = status === "unsure" ? "unsure" : (primary ? "labeled" : "unlabeled");
  await fetch(`/api/label/${CURRENT}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ primary_label: primary, facets, note, status: finalStatus }),
  });
  DATA.label = { primary_label: primary, facets_json: JSON.stringify(facets), note, status: finalStatus };
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
    <ul><li>Left: districts → records. Center: every representation (text first, then image/PDF).
      Right: the objective signals and your label controls.</li>
      <li><b>Axis 1</b> — pick the target's <b>shape</b> (or “target not present” / “unusable”).
        <b>Axis 2</b> — check any <b>confounding signals present</b> (multi-select). <b>Axis 3</b> — mark where it hides
        (footer / handbook page / needs-vision). A “flagged” hint means a detector suspected it — you confirm or ignore. Autosaves.</li>
      <li>Not sure? “Mark reviewed — unsure” records that you looked but couldn't decide (distinct from un-reviewed).</li>
      <li>Duplicates link to the canonical — label the canonical once.</li></ul>
    <h4>Likelihood tiers (script-assigned, sortable)</h4>
    <dl>${Object.entries(TIER_DEF).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    <h4>Target shapes (Axis 1)</h4>${dl(TARGET)}
    <h4>Terminals</h4>${dl(TERMINAL)}
    <h4>Confounding signals (Axis 2)</h4>${dl(CONFOUNDERS)}
    <h4>Where / how (Axis 3)</h4>${dl(LOCATION)}`;
}

$("#glossaryBtn").onclick = () => $("#glossary").classList.remove("hidden");
$("#glossaryClose").onclick = () => $("#glossary").classList.add("hidden");
$("#glossary").onclick = (e) => { if (e.target.id === "glossary") $("#glossary").classList.add("hidden"); };

buildGlossary();
// Initial Stage-5 load is driven by gate1.js's applyView() (it calls window.loadStage5 on show),
// so the tree re-fetches every time you switch back to Stage 5 — no stale list (the batch_00007
// gap). If Stage 5 isn't the initially-selected view, applyView loads it on first show.
