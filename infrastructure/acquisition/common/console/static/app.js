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

// ----------------------------- tree -----------------------------
async function loadTree() {
  const districts = await (await fetch("/api/tree")).json();
  const byBatch = {};
  districts.forEach((d) => { (byBatch[d.batch_id || "—"] ||= []).push(d); });
  const tree = $("#tree");
  tree.innerHTML = "";
  for (const [batch, ds] of Object.entries(byBatch)) {
    const g = document.createElement("div"); g.className = "batch-group";
    g.innerHTML = `<div class="batch-label">${batch}</div>`;
    ds.forEach((d) => g.appendChild(renderDistrict(d)));
    tree.appendChild(g);
  }
  refreshProgress();
}

function topoBadge(kind, val) {
  const v = val || "unknown";
  const title = kind === "guessed"
    ? "guessed topology — from signals (noisy; measures the heuristic)"
    : "labeled topology — derived from your labels + NCES (the truth)";
  return `<span class="topo ${kind} ${v}" title="${title}">${kind === "guessed" ? "guess" : "labeled"}: ${v}</span>`;
}

function byLevelStr(bl) { return bl ? Object.entries(bl).map(([k, v]) => `${k}: ${v}`).join(", ") : ""; }

function renderDistrict(d) {
  const wrap = document.createElement("div"); wrap.className = "district";
  const head = document.createElement("div"); head.className = "district-head";
  const nces = d.nces_school_count != null ? ` · ${d.nces_school_count} NCES school${d.nces_school_count === 1 ? "" : "s"}` : "";
  const blTitle = d.nces_by_level ? ` (${byLevelStr(d.nces_by_level)})` : "";
  head.innerHTML = `<div><div class="district-name">${d.name}</div>
      <div class="district-meta" title="NCES schools by level${blTitle}">${d.state} · ${d.records.length} records${nces}</div></div>
    <div class="topos">${topoBadge("labeled", d.labeled_topology)}${topoBadge("guessed", d.guessed_topology)}</div>`;
  const ul = document.createElement("ul"); ul.className = "rec-list";

  // Group records into near-duplicate clusters. A cluster renders as its representative row
  // (with a "+N" badge that expands the members); standalone records render directly.
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
  li.className = "rec-row" + (r.duplicate_of ? " dup" : "") + (clusterSize > 1 ? " cluster-rep" : "");
  li.dataset.recKey = r.rec_key;
  const tail = (r.url || "").replace(/^https?:\/\//, "").slice(0, 34);
  const badge = clusterSize > 1
    ? `<span class="cluster-badge" title="${clusterSize - 1} near-duplicate(s) — click to expand">+${clusterSize - 1}</span>` : "";
  const emergent = r.is_emergent ? `<span class="emergent-dot" title="emergent — captured but not a planned candidate">⚡</span>` : "";
  li.innerHTML = `<span class="tier ${r.tier}">${r.tier}</span>
    <span class="rec-label" title="${r.url}">${tail}${r.duplicate_of ? " · dup" : ""}</span>
    ${emergent}${badge}<span class="status-dot ${r.status || "unlabeled"}"></span>`;
  li.onclick = (e) => { e.stopPropagation(); selectRecord(r.rec_key, li); };
  return li;
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
loadTree();
