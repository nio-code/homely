const $ = (sel) => document.querySelector(sel);
const fmtPrice = (p) => "$" + p.toLocaleString();
const fmtSqft  = (n) => n ? n.toLocaleString() + " sq ft" : null;

let activeTab = "approved";
let filters   = {};
let searchPollHandle = null;

// SVG icons (no emoji)
const ICONS = {
  pin: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/><circle cx="12" cy="9" r="2.5"/></svg>`,
  pinFill: `<svg width="14" height="14" viewBox="0 0 24 24" fill="#fff" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/><circle cx="12" cy="9" r="2.5" fill="rgba(255,255,255,0.4)"/></svg>`,
  house: `<svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9.5L12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z"/><polyline points="9 21 9 12 15 12 15 21"/></svg>`,
  phone: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2A19.79 19.79 0 0 1 11.61 19a19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 3.12 4.18 2 2 0 0 1 5.09 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L9.91 9.91a16 16 0 0 0 6 6l.44-.44a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>`,
  email: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`,
};

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
  const rent = y.rent ? ` &middot; $${y.rent.toLocaleString()}/mo est.` : "";
  if (y.passes)      return `<div class="yield-tag good">${pct}% yield${rent}</div>`;
  if (y.pct >= 0.007) return `<div class="yield-tag ok">${pct}% yield${rent}</div>`;
  return `<div class="yield-tag low">${pct}% yield${rent}</div>`;
}

function card(l) {
  const el = document.createElement("div");
  el.className = "card" + (l.pinned_at ? " pinned" : "") + (l.status === "pending" ? " pending" : "");
  el.dataset.id = l.id;

  const src = (l.source || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const y = parseYield(l);

  const specs = [];
  if (l.beds  != null) specs.push(`<span>${l.beds} bd</span>`);
  if (l.baths != null) specs.push(`<span class="spec-sep">|</span><span>${l.baths} ba</span>`);
  if (l.sqft)          specs.push(`<span class="spec-sep">|</span><span>${fmtSqft(l.sqft)}</span>`);

  let agentHtml = "";
  if (l.agent_name || l.agent_phone || l.agent_email) {
    agentHtml = `<div class="card-agent">`;
    if (l.agent_name)  agentHtml += `<div class="agent-name">${esc(l.agent_name)}</div>`;
    if (l.agent_phone) {
      const tel = l.agent_phone.replace(/[^0-9+]/g, "");
      agentHtml += `<div>${ICONS.phone} <a href="tel:${tel}">${esc(l.agent_phone)}</a></div>`;
    }
    if (l.agent_email) agentHtml += `<div>${ICONS.email} <a href="mailto:${esc(l.agent_email)}">${esc(l.agent_email)}</a></div>`;
    agentHtml += `</div>`;
  }

  let footerHtml = `<div class="card-footer">`;
  if (l.listing_url) footerHtml += `<button class="btn-view" onclick="window.open('${esc(l.listing_url)}','_blank')">View listing</button>`;
  if (l.status === "pending") {
    footerHtml += `<button class="btn-approve">Approve</button><button class="btn-reject">Reject</button>`;
  }
  footerHtml += `</div>`;

  let badgesHtml = `<div class="photo-badges"><span class="badge badge-source">${esc(l.source || "unknown")}</span>`;
  if (l.pinned_at)          badgesHtml += `<span class="badge badge-pinned">Saved</span>`;
  if (l.status === "pending") badgesHtml += `<span class="badge badge-pending">Review</span>`;
  if (y && y.passes)        badgesHtml += `<span class="badge badge-1pct">1% Rule</span>`;
  badgesHtml += `</div>`;

  const pinIcon  = l.pinned_at ? ICONS.pinFill : ICONS.pin;
  const pinClass = "pin-btn" + (l.pinned_at ? " pinned" : "");

  el.innerHTML = `
    <div class="card-photo" data-source="${src}">
      <div class="house-svg">${ICONS.house}</div>
      ${badgesHtml}
      ${l.status === "approved" ? `<button class="${pinClass}" title="${l.pinned_at ? "Remove saved" : "Save home"}">${pinIcon}</button>` : ""}
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
      toast("Removed from saved homes");
    } else {
      const res = await api(`/api/listings/${l.id}/pin`, { method: "POST" });
      toast(res.telegram_sent ? "Saved and sent to Telegram" : "Saved home", res.telegram_sent ? "success" : "");
    }
    await refresh();
  } catch (e) { toast("Error: " + e.message, "error"); }
}

async function approve(l) {
  try {
    await api(`/api/listings/${l.id}/approve`, { method: "POST" });
    toast("Moved to For Sale", "success");
    await refresh();
  } catch (e) { toast("Error: " + e.message, "error"); }
}

async function reject(l) {
  if (!confirm(`Remove listing at ${l.address}?`)) return;
  try {
    await api(`/api/listings/${l.id}`, { method: "DELETE" });
    toast("Listing removed");
    await refresh();
  } catch (e) { toast("Error: " + e.message, "error"); }
}

function buildQuery(f, status) {
  const q = new URLSearchParams();
  if (status) q.set("status", status);
  if (f.zip)       q.set("zip", f.zip);
  if (f.min_price) q.set("min_price", f.min_price);
  if (f.max_price) q.set("max_price", f.max_price);
  if (f.beds)      q.set("beds", f.beds);
  return q.toString();
}

async function refresh() {
  const [approved, pending, pinned] = await Promise.all([
    api("/api/listings?" + buildQuery(filters, "approved")),
    api("/api/listings?" + buildQuery(filters, "pending")),
    api("/api/listings?" + buildQuery({}, "approved") + "&pinned=true"),
  ]);

  $("#tab-count-approved").textContent = `(${approved.length})`;
  $("#tab-count-pending").textContent  = `(${pending.length})`;

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

  const listEl = $("#list");
  listEl.innerHTML = "";
  const rows = activeTab === "approved" ? approved : pending;
  if (!rows.length) {
    listEl.innerHTML = `<div class="empty"><p>${
      activeTab === "pending"
        ? "No listings awaiting review."
        : "No listings yet. Click <strong>Find Listings</strong> to run a search."
    }</p></div>`;
  } else {
    rows.forEach((l) => listEl.appendChild(card(l)));
  }
}

function applyFilters() {
  filters = {
    zip:       $("#f-zip").value.trim() || null,
    min_price: $("#f-min").value || null,
    max_price: $("#f-max").value || null,
    beds:      $("#f-beds").value || null,
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
    $("#status").textContent = "Live";
    $("#status").style.color = "#178a00";
  } catch {
    $("#status").textContent = "Offline";
    $("#status").style.color = "#cc0000";
  }
}

async function startSearch() {
  $("#search-panel").classList.remove("hidden");
  $("#search-state").textContent = "Starting...";
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
    $("#search-state").textContent = s.running ? "Scanning..." : (s.returncode === 0 ? "Done" : "Stopped");
    $("#search-counts").textContent = `${s.qualified} found  ${s.inserted} new  ${s.updated} updated`;
    $("#search-log").textContent = s.log_tail.slice(-30).join("\n");
    if (!s.running) {
      $("#search-btn").disabled = false;
      await refresh();
      if (s.returncode === 0 && s.inserted > 0) {
        toast(`${s.inserted} new listings added to Pending Review`, "success");
        switchTab("pending");
      }
    } else {
      searchPollHandle = setTimeout(pollSearch, 1500);
    }
  } catch (_) {
    $("#search-btn").disabled = false;
  }
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  refresh();
}

$("#f-apply").addEventListener("click", applyFilters);
$("#f-clear").addEventListener("click", clearFilters);
$("#f-zip").addEventListener("keydown", (e) => e.key === "Enter" && applyFilters());
$("#search-btn").addEventListener("click", startSearch);
$("#search-close").addEventListener("click", () => $("#search-panel").classList.add("hidden"));
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

checkHealth();
refresh();
api("/api/search/status").then((s) => { if (s.running) { $("#search-panel").classList.remove("hidden"); pollSearch(); } }).catch(() => {});
