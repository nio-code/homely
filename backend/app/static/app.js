const $ = (sel) => document.querySelector(sel);
const fmtPrice = (p) => "$" + p.toLocaleString();
const fmtSpecs = (l) => {
  const parts = [];
  if (l.beds != null) parts.push(`${l.beds}bd`);
  if (l.baths != null) parts.push(`${l.baths}ba`);
  if (l.sqft) parts.push(`${l.sqft.toLocaleString()} sqft`);
  return parts.join(" · ");
};

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

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function card(l) {
  const el = document.createElement("div");
  el.className = "card" + (l.pinned_at ? " pinned" : "") + (l.status === "pending" ? " pending" : "");
  el.dataset.id = l.id;

  const agent = [];
  if (l.agent_name) agent.push(`<div class="name">${escapeHtml(l.agent_name)}</div>`);
  if (l.agent_phone) {
    const tel = l.agent_phone.replace(/[^0-9+]/g, "");
    agent.push(`<div>📞 <a href="tel:${tel}">${escapeHtml(l.agent_phone)}</a></div>`);
  }
  if (l.agent_email) agent.push(`<div>✉️ <a href="mailto:${escapeHtml(l.agent_email)}">${escapeHtml(l.agent_email)}</a></div>`);
  if (!agent.length) agent.push(`<div class="muted">No agent info</div>`);

  const actions = l.status === "pending"
    ? `<div class="actions">
         <button class="approve">✓ Approve</button>
         <button class="reject ghost">✕ Reject</button>
       </div>`
    : `<button class="pin ${l.pinned_at ? "pinned" : ""}">${l.pinned_at ? "📌 Pinned" : "Pin"}</button>`;

  el.innerHTML = `
    <span class="source-tag">${escapeHtml(l.source.replace("_", " "))}</span>
    <div class="price">${fmtPrice(l.price)}</div>
    <div class="addr">${escapeHtml(l.address)}, ${escapeHtml(l.city)} ${escapeHtml(l.state)} ${escapeHtml(l.zip)}</div>
    <div class="specs">${fmtSpecs(l) || "—"}</div>
    <div class="agent">${agent.join("")}</div>
    ${actions}
    <a class="muted small" style="margin-top:8px;" href="${escapeHtml(l.listing_url || "#")}" target="_blank" rel="noopener">View listing →</a>
  `;
  const pinBtn = el.querySelector("button.pin");
  if (pinBtn) pinBtn.addEventListener("click", () => togglePin(l));
  const approveBtn = el.querySelector("button.approve");
  if (approveBtn) approveBtn.addEventListener("click", () => approve(l));
  const rejectBtn = el.querySelector("button.reject");
  if (rejectBtn) rejectBtn.addEventListener("click", () => reject(l));
  return el;
}

async function togglePin(l) {
  const action = l.pinned_at ? "unpin" : "pin";
  try {
    if (action === "pin") {
      const res = await api(`/api/listings/${l.id}/pin`, { method: "POST" });
      toast(res.telegram_sent ? "📌 Pinned & sent to Telegram" : "Pinned (Telegram not linked — /start the bot)", res.telegram_sent ? "success" : "");
    } else {
      await api(`/api/listings/${l.id}/pin`, { method: "DELETE" });
      toast("Unpinned");
    }
    await refresh();
  } catch (e) {
    toast("Failed: " + e.message, "error");
  }
}

async function approve(l) {
  try {
    await api(`/api/listings/${l.id}/approve`, { method: "POST" });
    toast(`✓ Approved ${l.address}`, "success");
    await refresh();
  } catch (e) {
    toast("Approve failed: " + e.message, "error");
  }
}

async function reject(l) {
  if (!confirm(`Reject (delete) ${l.address}?`)) return;
  try {
    await api(`/api/listings/${l.id}`, { method: "DELETE" });
    toast(`Rejected ${l.address}`);
    await refresh();
  } catch (e) {
    toast("Reject failed: " + e.message, "error");
  }
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

  const tray = $("#tray");
  tray.innerHTML = "";
  if (!pinned.length) {
    tray.innerHTML = `<div class="empty">No pinned listings yet — click Pin on any card below.</div>`;
  } else {
    pinned.forEach((l) => tray.appendChild(card(l)));
  }
  $("#tray-count").textContent = `(${pinned.length}${pinned.length > 5 ? ", top 5 in Telegram" : ""})`;

  const list = $("#list");
  list.innerHTML = "";
  const rows = activeTab === "approved" ? approved : pending;
  if (!rows.length) {
    list.innerHTML = `<div class="empty">${activeTab === "pending" ? "No listings awaiting review." : "No listings match your filters."}</div>`;
  } else {
    rows.forEach((l) => list.appendChild(card(l)));
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
  ["#f-zip", "#f-min", "#f-max", "#f-beds"].forEach((s) => ($(s).value = ""));
  filters = {};
  refresh();
}

async function checkHealth() {
  try {
    await api("/api/health");
    $("#status").textContent = "● connected";
    $("#status").style.color = "var(--good)";
  } catch {
    $("#status").textContent = "● backend down";
    $("#status").style.color = "var(--danger)";
  }
}

// ── Search agent ─────────────────────────────────────────────────────────

async function startSearch() {
  $("#search-panel").classList.remove("hidden");
  $("#search-state").textContent = "Starting…";
  $("#search-log").textContent = "";
  $("#search-btn").disabled = true;

  try {
    await api("/api/search/run", {
      method: "POST",
      body: JSON.stringify({ target: 25 }),
    });
    pollSearch();
  } catch (e) {
    $("#search-state").textContent = "Failed to start";
    toast("Search failed to start: " + e.message, "error");
    $("#search-btn").disabled = false;
  }
}

async function pollSearch() {
  if (searchPollHandle) clearTimeout(searchPollHandle);
  try {
    const s = await api("/api/search/status");
    $("#search-state").textContent = s.running ? "🔍 Running…" : (s.returncode === 0 ? "✓ Done" : "⚠ Stopped");
    $("#search-counts").textContent = `qualified=${s.qualified}  inserted=${s.inserted}  updated=${s.updated}`;
    $("#search-log").textContent = s.log_tail.slice(-30).join("\n");
    if (s.running) {
      searchPollHandle = setTimeout(pollSearch, 1500);
    } else {
      $("#search-btn").disabled = false;
      await refresh();
      if (s.returncode === 0) {
        toast(`Search complete — ${s.inserted} new in pending tab`, "success");
        // auto-switch to pending tab if anything new
        if (s.inserted > 0) switchTab("pending");
      }
    }
  } catch (e) {
    $("#search-state").textContent = "Status error";
    $("#search-btn").disabled = false;
  }
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  refresh();
}

// ── Wire events ──────────────────────────────────────────────────────────

$("#f-apply").addEventListener("click", applyFilters);
$("#f-clear").addEventListener("click", clearFilters);
$("#f-zip").addEventListener("keydown", (e) => e.key === "Enter" && applyFilters());
$("#search-btn").addEventListener("click", startSearch);
$("#search-close").addEventListener("click", () => $("#search-panel").classList.add("hidden"));
document.querySelectorAll(".tab").forEach((b) => {
  b.addEventListener("click", () => switchTab(b.dataset.tab));
});

checkHealth();
refresh();
// resume polling if a search was running before page reload
api("/api/search/status").then((s) => { if (s.running) { $("#search-panel").classList.remove("hidden"); pollSearch(); } }).catch(() => {});
