const $ = (sel) => document.querySelector(sel);
const fmtPrice = (p) => "$" + p.toLocaleString();
const fmtSqft = (n) => n ? n.toLocaleString() + " sq ft" : null;

let activeTab = "approved";
let filters = {};
let searchPollHandle = null;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "content-type": "application/json" }, ...opts });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.status === 204 ? null : r.json();
}

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  setTimeout(() => t.classList.remove("show"), 3500);
}

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function parseYield(l) {
  // Try to parse rent_to_price_pct from notes JSON block
  try {
    const m = (l.notes || "").match(/\{.*\}/);
    if (m) {
      const meta = JSON.parse(m[0]);
      return { pct: meta.rent_to_price_pct, passes: meta.passes_1pct_rule, rent: meta.market_rent_est };
    }
  } catch (_) {}
  return null;
}

function yieldTag(y) {
  if (!y || !y.pct) return "";
  const pct = (y.pct * 100).toFixed(2);
  const rent = y.rent ? ` · $${y.rent.toLocaleString()}/mo est.` : "";
  if (y.passes) return `<div class="yield-tag good">✓ ${pct}% yield${rent}</div>`;
  if (y.pct >= 0.007) return `<div class="yield-tag ok">${pct}% yield${rent}</div>`;
  return `<div class="yield-tag low">${pct}% yield${rent}</div>`;
}

function card(l) {
  const el = document.createElement("div");
  el.className = "card" + (l.pinned_at ? " pinned" : "") + (l.status === "pending" ? " pending" : "");
  el.dataset.id = l.id;

  const src = (l.source || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const y = parseYield(l);

  // Specs row
  const specs = [];
  if (l.beds != null) specs.push(`<span>${l.beds} bd</span>`);
  if (l.baths != null) specs.push(`<span class="spec-sep">·</span><span>${l.baths} ba</span>`);
  if (l.sqft) specs.push(`<span class="spec-sep">·</span><span>${fmtSqft(l.sqft)}</span>`);

  // Agent
  let agentHtml = "";
  if (l.agent_name || l.agent_phone || l.agent_email) {
    agentHtml = `<div class="card-agent">`;
    if (l.agent_name) agentHtml += `<div class="agent-name">${esc(l.agent_name)}</div>`;
    if (l.agent_phone) {
      const tel = l.agent_phone.replace(/[^0-9+]/g, "");
      agentHtml += `<div><a href="tel:${tel}">${esc(l.agent_phone)}</a></div>`;
    }
    if (l.agent_email) agentHtml += `<div><a href="mailto:${esc(l.agent_email)}">${esc(l.agent_email)}</a></div>`;
    agentHtml += `</div>`;
  }

  // Footer actions
  let footerHtml = `<div class="card-footer">`;
  if (l.listing_url) {
    footerHtml += `<button class="btn-view" onclick="window.open('${esc(l.listing_url)}','_blank')">View ↗</button>`;
  }
  if (l.status === "pending") {
    footerHtml += `<button class="btn-approve">✓ Approve</button><button class="btn-reject">✕</button>`;
  }
  footerHtml += `</div>`;

  // Badges in photo
  let badgesHtml = `<div class="photo-badges"><span class="badge badge-source">${esc(l.source || "unknown")}</span>`;
  if (l.pinned_at) badgesHtml += `<span class="badge badge-pinned">📌 Pinned</span>`;
  if (l.status === "pending") badgesHtml += `<span class="badge badge-pending">Review</span>`;
  if (y && y.passes) badgesHtml += `<span class="badge badge-1pct">1% Rule</span>`;
  badgesHtml += `</div>`;

  el.innerHTML = `
    <div class="card-photo" data-source="${src}">
      <div class="placeholder">🏠</div>
      ${badgesHtml}
      ${l.status === "approved" ? `<button class="pin-btn ${l.pinned_at ? "pinned" : ""}" title="${l.pinned_at ? "Unpin" : "Pin this listing"}">${l.pinned_at ? "📌" : "🤍"}</button>` : ""}
    </div>
    <div class="card-body">
      <div class="card-price">${fmtPrice(l.price)}</div>
      <div class="card-specs">${specs.join("")}</div>
      <div class="card-address">${esc(l.address)}</div>
      <div class="card-city">${esc(l.city || "Irvine")}, ${esc(l.state || "CA")} ${esc(l.zip || "")}</div>
      ${yieldTag(y)}
      ${agentHtml}
      ${footerHtml}
    </div>
  `;

  el.querySelector(".pin-btn")?.addEventListener("click", () => togglePin(l));
  el.querySelector(".btn-approve")?.addEventListener("click", () => approve(l));
  el.querySelector(".btn-reject")?.addEventListener("click", () => reject(l));
  return el;
}

async function togglePin(l) {
  try {
    if (l.pinned_at) {
      await api(`/api/listings/${l.id}/pin`, { method: "DELETE" });
      toast("Unpinned");
    } else {
      const res = await api(`/api/listings/${l.id}/pin`, { method: "POST" });
      toast(res.telegram_sent ? "📌 Pinned & sent to Telegram!" : "📌 Pinned (set up Telegram to get notified)", res.telegram_sent ? "success" : "");
    }
    await refresh();
  } catch (e) { toast("Failed: " + e.message, "error"); }
}

async function approve(l) {
  try {
    await api(`/api/listings/${l.id}/approve`, { method: "POST" });
    toast(`Approved — moved to For Sale`, "success");
    await refresh();
  } catch (e) { toast("Failed: " + e.message, "error"); }
}

async function reject(l) {
  if (!confirm(`Delete listing at ${l.address}?`)) return;
  try {
    await api(`/api/listings/${l.id}`, { method: "DELETE" });
    toast(`Removed ${l.address}`);
    await refresh();
  } catch (e) { toast("Failed: " + e.message, "error"); }
}

function buildQuery(f, status) {
  const q = new URLSearchParams();
  if (status) q.set("status", status);
  if (f.zip) q.set("zip", f.zip);
  if (f.min_price) q.set("min_price", f.min_price);
  if (f.max_price) q.set("max_price", f.max_price);
  if (f.beds) q.set("beds", f.beds);
  return q.toString();
}

async function refresh() {
  const [approved, pending, pinned] = await Promise.all([
    api("/api/listings?" + buildQuery(filters, "approved")),
    api("/api/listings?" + buildQuery(filters, "pending")),
    api("/api/listings?" + buildQuery({}, "approved") + "&pinned=true"),
  ]);

  $("#tab-count-approved").textContent = `(${approved.length})`;
  $("#tab-count-pending").textContent = `(${pending.length})`;

  // Tray
  const trayEl = $("#tray");
  const traySection = $("#tray-section");
  trayEl.innerHTML = "";
  if (!pinned.length) {
    traySection.style.display = "none";
  } else {
    traySection.style.display = "";
    pinned.forEach((l) => trayEl.appendChild(card(l)));
    $("#tray-count").textContent = pinned.length;
  }

  // Main list
  const listEl = $("#list");
  listEl.innerHTML = "";
  const rows = activeTab === "approved" ? approved : pending;
  if (!rows.length) {
    listEl.innerHTML = `<div class="empty"><div class="empty-icon">${activeTab === "pending" ? "🎉" : "🔍"}</div><p>${activeTab === "pending" ? "No listings awaiting review." : "No listings match your filters.<br>Try clicking <strong>Find More Listings</strong>."}</p></div>`;
  } else {
    rows.forEach((l) => listEl.appendChild(card(l)));
  }
}

function applyFilters() {
  filters = {
    zip: $("#f-zip").value.trim() || null,
    min_price: $("#f-min").value || null,
    max_price: $("#f-max").value || null,
    beds: $("#f-beds").value || null,
  };
  refresh();
}

function clearFilters() {
  ["#f-zip","#f-min","#f-max","#f-beds"].forEach((s) => ($(s).value = ""));
  filters = {};
  refresh();
}

async function checkHealth() {
  try {
    await api("/api/health");
    $("#status").textContent = "● Live";
    $("#status").style.color = "#00857d";
  } catch {
    $("#status").textContent = "● Offline";
    $("#status").style.color = "#d92228";
  }
}

// ── Search ────────────────────────────────────────────────────────────

async function startSearch() {
  $("#search-panel").classList.remove("hidden");
  $("#search-state").textContent = "Starting…";
  $("#search-log").textContent = "";
  $("#search-btn").disabled = true;
  try {
    await api("/api/search/run", { method: "POST", body: JSON.stringify({ target: 25 }) });
    pollSearch();
  } catch (e) {
    $("#search-state").textContent = "Failed to start";
    toast("Could not start search: " + e.message, "error");
    $("#search-btn").disabled = false;
  }
}

async function pollSearch() {
  if (searchPollHandle) clearTimeout(searchPollHandle);
  try {
    const s = await api("/api/search/status");
    const done = !s.running;
    $("#search-state").textContent = s.running ? "🔍 Scanning listings…" : (s.returncode === 0 ? "✓ Done" : "⚠ Stopped");
    $("#search-counts").textContent = `${s.qualified} found · ${s.inserted} new · ${s.updated} updated`;
    $("#search-log").textContent = s.log_tail.slice(-30).join("\n");
    if (!done) {
      searchPollHandle = setTimeout(pollSearch, 1500);
    } else {
      $("#search-btn").disabled = false;
      await refresh();
      if (s.returncode === 0 && s.inserted > 0) {
        toast(`Found ${s.inserted} new listings — check Pending Review`, "success");
        switchTab("pending");
      }
    }
  } catch (e) {
    $("#search-btn").disabled = false;
  }
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  refresh();
}

// ── Wire up ───────────────────────────────────────────────────────────

$("#f-apply").addEventListener("click", applyFilters);
$("#f-clear").addEventListener("click", clearFilters);
$("#f-zip").addEventListener("keydown", (e) => e.key === "Enter" && applyFilters());
$("#search-btn").addEventListener("click", startSearch);
$("#search-close").addEventListener("click", () => $("#search-panel").classList.add("hidden"));
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

checkHealth();
refresh();
api("/api/search/status").then((s) => { if (s.running) { $("#search-panel").classList.remove("hidden"); pollSearch(); } }).catch(() => {});
