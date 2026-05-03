const $ = (sel) => document.querySelector(sel);
const fmtPrice = (p) => "$" + p.toLocaleString();
const fmtSpecs = (l) => {
  const parts = [];
  if (l.beds != null) parts.push(`${l.beds}bd`);
  if (l.baths != null) parts.push(`${l.baths}ba`);
  if (l.sqft) parts.push(`${l.sqft.toLocaleString()} sqft`);
  return parts.join(" · ");
};

let allListings = [];
let filters = {};

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

function card(l) {
  const el = document.createElement("div");
  el.className = "card" + (l.pinned_at ? " pinned" : "");
  el.dataset.id = l.id;

  const agent = [];
  if (l.agent_name) agent.push(`<div class="name">${escapeHtml(l.agent_name)}</div>`);
  if (l.agent_phone) {
    const tel = l.agent_phone.replace(/[^0-9+]/g, "");
    agent.push(`<div>📞 <a href="tel:${tel}">${escapeHtml(l.agent_phone)}</a></div>`);
  }
  if (l.agent_email) agent.push(`<div>✉️ <a href="mailto:${escapeHtml(l.agent_email)}">${escapeHtml(l.agent_email)}</a></div>`);
  if (!agent.length) agent.push(`<div class="muted">No agent info</div>`);

  el.innerHTML = `
    <span class="source-tag">${escapeHtml(l.source.replace("_", " "))}</span>
    <div class="price">${fmtPrice(l.price)}</div>
    <div class="addr">${escapeHtml(l.address)}, ${escapeHtml(l.city)} ${escapeHtml(l.state)} ${escapeHtml(l.zip)}</div>
    <div class="specs">${fmtSpecs(l) || "—"}</div>
    <div class="agent">${agent.join("")}</div>
    <button class="pin ${l.pinned_at ? "pinned" : ""}" data-action="${l.pinned_at ? "unpin" : "pin"}">
      ${l.pinned_at ? "📌 Pinned" : "Pin"}
    </button>
    <a class="muted small" style="margin-top:8px;" href="${escapeHtml(l.listing_url)}" target="_blank" rel="noopener">View listing →</a>
  `;
  el.querySelector("button.pin").addEventListener("click", () => togglePin(l));
  return el;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function togglePin(l) {
  const action = l.pinned_at ? "unpin" : "pin";
  try {
    if (action === "pin") {
      const res = await api(`/api/listings/${l.id}/pin`, { method: "POST" });
      toast(res.telegram_sent ? "📌 Pinned & sent to Telegram" : "Pinned (Telegram not linked — /start the bot)", res.telegram_sent ? "success" : "error");
    } else {
      await api(`/api/listings/${l.id}/pin`, { method: "DELETE" });
      toast("Unpinned");
    }
    await refresh();
  } catch (e) {
    toast("Failed: " + e.message, "error");
  }
}

function buildQuery(f) {
  const q = new URLSearchParams();
  if (f.zip) q.set("zip", f.zip);
  if (f.min_price) q.set("min_price", f.min_price);
  if (f.max_price) q.set("max_price", f.max_price);
  if (f.beds) q.set("beds", f.beds);
  return q.toString();
}

async function refresh() {
  const [pinned, all] = await Promise.all([
    api("/api/listings?pinned=true"),
    api("/api/listings?" + buildQuery(filters)),
  ]);

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
  if (!all.length) {
    list.innerHTML = `<div class="empty">No listings match your filters.</div>`;
  } else {
    all.forEach((l) => list.appendChild(card(l)));
  }
  $("#all-count").textContent = `(${all.length})`;

  allListings = all;
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

$("#f-apply").addEventListener("click", applyFilters);
$("#f-clear").addEventListener("click", clearFilters);
$("#f-zip").addEventListener("keydown", (e) => e.key === "Enter" && applyFilters());

checkHealth();
refresh();
