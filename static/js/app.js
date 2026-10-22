const DESTRUCTIVE_PATTERNS = [/^stop\b/, /^ban\b/, /^ban-ip\b/, /^kick\b/, /^op\b/, /^deop\b/, /^save-off\b/];

function isDestructive(cmd) {
  const c = cmd.trim().toLowerCase();
  return DESTRUCTIVE_PATTERNS.some((re) => re.test(c));
}

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  // innerHTML only escapes <>& — also escape quotes so this is safe to
  // drop into a quoted HTML attribute, not just text.
  return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function shortName(id) {
  return id.split(":").pop().replace(/_/g, " ");
}

function titleCase(str) {
  return str.replace(/\b\w/g, (c) => c.toUpperCase());
}

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
function toRoman(n) {
  return ROMAN[n] || String(n);
}

function banner(message) {
  return `<div class="error-banner" role="alert">${escapeHtml(message)}</div>`;
}

// fetch + parse JSON without throwing on a non-JSON body (e.g. a proxy's
// HTML 502 page), so callers can show a real message instead of a SyntaxError.
async function fetchJson(url, options) {
  const res = await fetch(url, options);
  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    // leave null
  }
  return { res, data };
}

function errorText(res, data) {
  if (data && typeof data.detail === "string" && data.detail) return data.detail;
  return `Server returned ${res.status}${res.statusText ? " " + res.statusText : ""}`;
}

// --- Nav ---

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((i) => {
      i.classList.remove("active");
      i.removeAttribute("aria-current");
    });
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    item.classList.add("active");
    item.setAttribute("aria-current", "page");
    el(`page-${item.dataset.page}`).classList.add("active");
    if (item.dataset.page === "console") connectConsole();
    if (item.dataset.page === "whitelist") loadWhitelist();
    if (item.dataset.page === "players") loadPlayers();
    if (item.dataset.page === "world") loadWorld();
  });
});

// --- Overview / status ---

function setStatusUnreachable() {
  // Beacon itself isn't answering: grey "unknown" dot, and blank everything
  // the last good reply filled in so stale numbers aren't mistaken for live ones.
  el("status-dot").className = "dot";
  el("status-text").textContent = "unreachable";
  el("ov-status").textContent = "Unreachable";
  el("ov-players").textContent = "—";
  el("ov-tps").textContent = "—";
  el("ov-uptime").textContent = "—";
  el("overview-error").innerHTML = "";
  el("ov-online-list").innerHTML = `<div class="empty">—</div>`;
}

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    el("status-dot").className = "dot " + (data.online ? "online" : "offline");
    el("status-text").textContent = data.online ? "online" : "offline";

    el("ov-status").textContent = data.online ? "Online" : "Offline";
    el("ov-players").textContent = `${data.players_online} / ${data.players_max}`;
    el("ov-tps").textContent = data.tps ? data.tps.map((t) => t.toFixed(1)).join(" / ") : "—";
    el("ov-uptime").textContent = data.uptime_since || "—";
    el("ov-motd").textContent = data.motd || "—";

    el("overview-error").innerHTML = data.error ? banner(data.error) : "";

    const list = el("ov-online-list");
    if (data.player_names && data.player_names.length) {
      list.innerHTML = `<div class="badge-row">${data.player_names
        .map((n) => `<span class="badge name">${escapeHtml(n)}</span>`)
        .join("")}</div>`;
    } else {
      list.innerHTML = `<div class="empty">No one online</div>`;
    }
  } catch (err) {
    setStatusUnreachable();
  }
}

loadStatus();
setInterval(loadStatus, 5000);

async function loadOverviewExtras() {
  try {
    const { res, data } = await fetchJson("/api/whitelist");
    el("ov-whitelisted").textContent = res.ok && Array.isArray(data) ? data.length : "—";
  } catch (err) {
    el("ov-whitelisted").textContent = "—";
  }

  try {
    const { res, data: world } = await fetchJson("/api/world");
    if (!res.ok || !world) throw new Error(errorText(res, world));
    if (world.error) {
      el("ov-world-error").innerHTML = banner(`World data unavailable: ${world.error}`);
      el("ov-w-difficulty").textContent = "—";
      el("ov-w-weather").textContent = "—";
      el("ov-w-seed").textContent = "—";
    } else {
      el("ov-world-error").innerHTML = "";
      el("ov-w-difficulty").textContent = world.difficulty;
      el("ov-w-weather").textContent = world.thundering ? "Thunderstorm" : world.raining ? "Rain" : "Clear";
      el("ov-w-seed").textContent = world.seed ?? "—";
    }
    const mainWorld = (world.disk_usage || []).find((d) => !d.path.endsWith("backups"));
    el("ov-worldsize").textContent = mainWorld ? mainWorld.size : "—";
  } catch (err) {
    // leave placeholders
  }
}

loadOverviewExtras();
setInterval(loadOverviewExtras, 30000);

// --- Console ---

let consoleSocket = null;
const CONSOLE_MAX_LINES = 2000;

function consoleAtBottom(logEl) {
  return logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
}

// Appends a line. Only follows the output if you were already at the bottom,
// so scrolling up to read earlier lines isn't undone by the next new line.
function appendConsoleLine(text, className, forceScroll) {
  const logEl = el("console-log");
  const follow = forceScroll || consoleAtBottom(logEl);
  const line = document.createElement("div");
  line.className = className ? `line ${className}` : "line";
  line.textContent = text;
  logEl.appendChild(line);
  while (logEl.childElementCount > CONSOLE_MAX_LINES) logEl.firstElementChild.remove();
  if (follow) logEl.scrollTop = logEl.scrollHeight;
}

function connectConsole() {
  // CONNECTING counts too: a quick double click on the tab used to open a
  // second socket, so every line (and the 200-line backlog) showed twice.
  if (
    consoleSocket &&
    (consoleSocket.readyState === WebSocket.OPEN || consoleSocket.readyState === WebSocket.CONNECTING)
  ) {
    return;
  }
  // A new socket replays the last 200 journal lines, so start from a clean log.
  el("console-log").innerHTML = "";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${location.host}/ws/console`);
  consoleSocket = socket;
  socket.addEventListener("message", (event) => appendConsoleLine(event.data));
}

async function sendCommand() {
  const input = el("console-input");
  const cmd = input.value.trim();
  if (!cmd) return;

  if (isDestructive(cmd) && !confirm(`Run potentially destructive command: /${cmd}?`)) {
    return;
  }

  appendConsoleLine(`> /${cmd}`, "attn", true);
  input.value = "";
  try {
    const { res, data } = await fetchJson("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd }),
    });
    appendConsoleLine(res.ok && data ? data.response : `Error: ${errorText(res, data)}`, "", true);
  } catch (err) {
    appendConsoleLine(`Error: ${err}`, "", true);
  }
}

el("console-send").addEventListener("click", sendCommand);
el("console-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendCommand();
});

// --- Whitelist ---

async function loadWhitelist() {
  el("whitelist-error").innerHTML = "";
  const body = el("whitelist-body");
  body.innerHTML = `<tr><td colspan="3" class="empty">Loading...</td></tr>`;
  try {
    const { res, data: entries } = await fetchJson("/api/whitelist");
    if (!res.ok || !Array.isArray(entries)) throw new Error(errorText(res, entries));
    if (!entries.length) {
      body.innerHTML = `<tr><td colspan="3" class="empty">No one whitelisted</td></tr>`;
      return;
    }
    body.innerHTML = entries
      .map(
        (e) => `
      <tr>
        <td>${escapeHtml(e.name)}${e.is_op ? `<span class="badge op">OP ${e.op_level ?? ""}</span>` : ""}</td>
        <td class="col-uuid">${escapeHtml(e.uuid)}</td>
        <td><button type="button" class="danger" data-remove="${escapeHtml(e.name)}">Remove</button></td>
      </tr>`
      )
      .join("");
    body.querySelectorAll("[data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => removeFromWhitelist(btn.dataset.remove));
    });
  } catch (err) {
    body.innerHTML = `<tr><td colspan="3" class="empty">Failed to load whitelist</td></tr>`;
  }
}

async function removeFromWhitelist(name) {
  if (!confirm(`Remove ${name} from the whitelist?`)) return;
  el("whitelist-error").innerHTML = "";
  try {
    const { res, data } = await fetchJson(`/api/whitelist/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (!res.ok) {
      el("whitelist-error").innerHTML = banner(`Couldn't remove ${name}: ${errorText(res, data)}`);
      return;
    }
  } catch (err) {
    el("whitelist-error").innerHTML = banner(`Couldn't remove ${name}: ${err.message}`);
    return;
  }
  loadWhitelist();
}

el("whitelist-add").addEventListener("click", async () => {
  const input = el("whitelist-username");
  const username = input.value.trim();
  if (!username) return;
  const errorBox = el("whitelist-error");
  errorBox.innerHTML = "";
  try {
    const { res, data } = await fetchJson("/api/whitelist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    if (!res.ok) {
      errorBox.innerHTML = banner(errorText(res, data));
      return;
    }
    input.value = "";
    loadWhitelist();
  } catch (err) {
    errorBox.innerHTML = banner(`Couldn't reach Beacon: ${err.message}`);
  }
});

// --- Players ---

let allPlayers = [];

function filteredPlayers() {
  const q = el("players-search").value.trim().toLowerCase();
  return allPlayers.filter((p) => p.name.toLowerCase().includes(q));
}

async function loadPlayers() {
  const body = el("players-body");
  body.innerHTML = `<tr><td colspan="2" class="empty">Loading...</td></tr>`;
  try {
    const { res, data } = await fetchJson("/api/players");
    if (!res.ok || !Array.isArray(data)) throw new Error(errorText(res, data));
    allPlayers = data;
    // The search box keeps its text when you switch tabs, so apply it again.
    renderPlayers(filteredPlayers());
  } catch (err) {
    body.innerHTML = `<tr><td colspan="2" class="empty">Failed to load players</td></tr>`;
  }
}

function renderPlayers(players) {
  const body = el("players-body");
  if (!players.length) {
    body.innerHTML = `<tr><td colspan="2" class="empty">No players found</td></tr>`;
    return;
  }
  body.innerHTML = players
    .map(
      (p) => `
    <tr class="clickable" data-uuid="${escapeHtml(p.uuid)}" data-name="${escapeHtml(p.name)}">
      <td><button type="button" class="row-link">${escapeHtml(p.name)}</button></td>
      <td>${p.online ? '<span class="dot online" style="display:inline-block"></span> online' : "offline"}</td>
    </tr>`
    )
    .join("");
}

// One delegated handler: the row is clickable for the mouse, and the name
// inside it is a real button, so keyboard and screen-reader users can open it.
el("players-body").addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-uuid]");
  if (row) openPlayerModal(row.dataset.uuid, row.dataset.name, row.querySelector(".row-link"));
});

el("players-search").addEventListener("input", () => renderPlayers(filteredPlayers()));

// --- Player popup ---

let playerModalRefreshTimer = null;
let modalUuid = null;
let modalLoadingUuid = null;
let modalOpener = null;

function openPlayerModal(uuid, name, opener) {
  modalUuid = uuid;
  modalLoadingUuid = null;
  modalOpener = opener || document.activeElement;
  el("player-modal-name").textContent = name;
  el("player-modal-body").innerHTML = `<div class="empty">Loading...</div>`;
  el("player-modal-backdrop").classList.add("active");
  // Keep Tab and screen readers inside the dialog, and move focus into it.
  el("app").inert = true;
  el("player-modal-close").focus();

  loadPlayerModalContent(uuid);
  if (playerModalRefreshTimer) clearInterval(playerModalRefreshTimer);
  playerModalRefreshTimer = setInterval(() => loadPlayerModalContent(uuid), 4000);
}

function closePlayerModal() {
  hideTooltip();
  modalUuid = null;
  modalLoadingUuid = null;
  el("player-modal-backdrop").classList.remove("active");
  el("app").inert = false;
  if (playerModalRefreshTimer) {
    clearInterval(playerModalRefreshTimer);
    playerModalRefreshTimer = null;
  }
  if (modalOpener && document.contains(modalOpener)) modalOpener.focus();
  modalOpener = null;
}

function dimensionName(id) {
  return titleCase(shortName(id));
}

async function loadPlayerModalContent(uuid) {
  // Skip if this player's data is already being fetched (a slow reply, since
  // both endpoints can run a world save, shouldn't pile up refreshes).
  if (modalLoadingUuid === uuid) return;
  modalLoadingUuid = uuid;

  let statsRes, invRes;
  try {
    [statsRes, invRes] = await Promise.allSettled([
      fetch(`/api/players/${uuid}/stats`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/players/${uuid}/inventory`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    ]);
  } finally {
    if (modalLoadingUuid === uuid) modalLoadingUuid = null;
  }

  // The popup may have been closed or switched to another player while the
  // request was in flight; don't paint this player's data under that name.
  if (uuid !== modalUuid) return;

  let html = "";

  html += `<div class="section-title">Stats</div>`;
  if (statsRes.status === "fulfilled") {
    const s = statsRes.value;
    html += `<div class="grid">`;
    for (const [label, value] of Object.entries(s.summary)) {
      html += `<div class="card"><div class="label">${escapeHtml(label)}</div><div class="value small">${escapeHtml(String(value))}</div></div>`;
    }
    html += `</div>`;
    if (s.top_mined.length) {
      html += `<div class="section-title">Top Mined</div><div class="badge-row">`;
      html += s.top_mined.map((m) => `<span class="badge">${escapeHtml(shortName(m.item))} × ${m.count}</span>`).join("");
      html += `</div>`;
    }
    if (s.top_killed.length) {
      html += `<div class="section-title">Top Kills</div><div class="badge-row">`;
      html += s.top_killed.map((k) => `<span class="badge">${escapeHtml(shortName(k.entity))} × ${k.count}</span>`).join("");
      html += `</div>`;
    }
  } else {
    html += `<div class="empty">No stats available</div>`;
  }

  html += `<div class="section-title">Inventory</div>`;
  if (invRes.status === "fulfilled") {
    const inv = invRes.value;
    const armorOrder = ["helmet", "chestplate", "leggings", "boots"].map((k) => inv.inventory.armor[k]);
    const coords = inv.position ? inv.position.map((n) => n.toFixed(1)).join(", ") : "unknown";
    const gamemode = inv.gamemode.charAt(0).toUpperCase() + inv.gamemode.slice(1);
    const health = Math.round(inv.health * 10) / 10;
    html += `<div class="player-info">Health ${health} · Food ${inv.food_level} · XP Level ${inv.xp_level} · ${escapeHtml(gamemode)} · ${escapeHtml(dimensionName(inv.dimension))} · (${coords})</div>`;
    html += renderSlotGroup("Hotbar", inv.inventory.hotbar);
    html += renderSlotGroup("Main Inventory", inv.inventory.main);
    html += renderSlotGroup("Armor", armorOrder, true);
    html += renderSlotGroup("Offhand", [inv.inventory.offhand], true);
    if (inv.inventory.other.length) html += renderSlotGroup("Other", inv.inventory.other, true);
    html += renderSlotGroup("Ender Chest", inv.ender_chest);
  } else {
    html += `<div class="empty">No playerdata available</div>`;
  }

  // The 4 s refresh rebuilds the slots, so remember which one had its
  // tooltip open and reopen it on the new element.
  const openKey = activeSlot ? activeSlot.dataset.key : null;
  hideTooltip();
  el("player-modal-body").innerHTML = html;
  if (openKey) {
    const again = el("player-modal-body").querySelector(`.slot[data-key="${openKey}"]`);
    if (again) showTooltip(again);
  }
}

// items: array of item-or-null, one per real inventory slot — nulls render
// as empty slot boxes so gaps line up with the player's actual layout.
function renderSlotGroup(title, items, narrow) {
  if (!items || !items.length) return "";
  const slots = items
    .map((it, index) => {
      if (!it) return `<div class="slot"></div>`;
      const shortId = it.id.split(":").pop();
      const displayName = it.potion ? `${it.name} of ${it.potion}` : it.name;
      const nameClass = it.custom_name ? "mc-tt-name mc-tt-custom" : "mc-tt-name";
      const nameLine = it.custom_name ? escapeHtml(it.custom_name) : escapeHtml(displayName);
      const ttLines = [];
      if (it.enchantments) {
        for (const [k, v] of Object.entries(it.enchantments)) {
          ttLines.push(`<div class="mc-tt-line mc-tt-enchant">${escapeHtml(titleCase(shortName(k)))} ${toRoman(v)}</div>`);
        }
      }
      if (it.trim && (it.trim.pattern || it.trim.material)) {
        const trimText = [it.trim.pattern, it.trim.material].filter(Boolean).join(" ");
        ttLines.push(`<div class="mc-tt-line mc-tt-trim">${escapeHtml(trimText)} Trim</div>`);
      }
      if (it.contents && it.contents.length) {
        const grouped = {};
        for (const c of it.contents) {
          grouped[c.name] = (grouped[c.name] || 0) + c.count;
        }
        ttLines.push(`<div class="mc-tt-line mc-tt-gray">Contains:</div>`);
        for (const [n, c] of Object.entries(grouped)) {
          ttLines.push(`<div class="mc-tt-line mc-tt-gray">&nbsp;&nbsp;${escapeHtml(n)} ×${c}</div>`);
        }
      }
      const tooltipHtml = `<div class="mc-tooltip"><div class="${nameClass}">${nameLine}</div>${ttLines.join("")}</div>`;
      const countBadge = it.count > 1 ? `<span class="count">${it.count}</span>` : "";
      const enchantedClass = it.enchantments ? " enchanted" : "";
      const iconSrc = it.trim && it.trim.material_id
        ? `/api/icon/${shortId}/trim/${it.trim.material_id}.png`
        : `/api/icon/${shortId}.png`;
      const initials = it.name.split(/\s+/).map((w) => w[0] || "").join("").slice(0, 2).toUpperCase();
      const key = `${title.toLowerCase().replace(/\W+/g, "-")}-${index}`;
      return `<div class="slot${enchantedClass}" data-key="${key}">
        <img src="${iconSrc}" alt="${escapeHtml(displayName)}" data-initials="${escapeHtml(initials)}" />
        ${countBadge}
        ${tooltipHtml}
      </div>`;
    })
    .join("");
  const gridClass = narrow ? "slot-grid slot-grid-narrow" : "slot-grid";
  return `<div class="section-title">${title}</div><div class="${gridClass}">${slots}</div>`;
}

// Icons with no usable picture come back as a 1x1 transparent PNG (or fail
// to load). Show the item's initials so an occupied slot never looks empty.
function iconFallback(event) {
  const img = event.target;
  if (!(img instanceof HTMLImageElement)) return;
  if (event.type === "load" && img.naturalWidth > 1) return;
  const span = document.createElement("span");
  span.className = "slot-fallback";
  span.textContent = img.dataset.initials || "?";
  img.replaceWith(span);
}
// load/error don't bubble, so listen in the capture phase.
el("player-modal-body").addEventListener("load", iconFallback, true);
el("player-modal-body").addEventListener("error", iconFallback, true);

// --- Item tooltips ---
// Positioned in JS (the tooltip is position:fixed) so it stays inside the
// window: clamped to the left/right edges, and flipped below the slot when
// there's no room above. Mouse: hover. Touch: tap a slot to toggle.

let activeSlot = null;

function hideTooltip() {
  if (activeSlot) {
    activeSlot.classList.remove("tt-open");
    activeSlot = null;
  }
}

function showTooltip(slot) {
  const tip = slot.querySelector(".mc-tooltip");
  if (!tip) return;
  if (activeSlot && activeSlot !== slot) hideTooltip();
  slot.classList.add("tt-open");
  tip.style.visibility = "hidden"; // measure first, reveal once positioned
  const rect = slot.getBoundingClientRect();
  const tw = tip.offsetWidth;
  const th = tip.offsetHeight;
  const margin = 8;
  let left = rect.left + rect.width / 2 - tw / 2;
  left = Math.max(margin, Math.min(left, window.innerWidth - tw - margin));
  let top = rect.top - th - margin;
  if (top < margin) top = rect.bottom + margin;
  if (top + th > window.innerHeight - margin) top = Math.max(margin, window.innerHeight - th - margin);
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
  tip.style.visibility = "visible";
  activeSlot = slot;
}

const canHover = () => window.matchMedia("(hover: hover)").matches;
const modalBody = el("player-modal-body");

modalBody.addEventListener("mouseover", (e) => {
  if (!canHover()) return;
  const slot = e.target.closest(".slot[data-key]");
  if (slot) showTooltip(slot);
});
modalBody.addEventListener("mouseout", (e) => {
  if (!canHover()) return;
  const slot = e.target.closest(".slot[data-key]");
  if (slot && !slot.contains(e.relatedTarget)) hideTooltip();
});
modalBody.addEventListener("click", (e) => {
  if (canHover()) return;
  const slot = e.target.closest(".slot[data-key]");
  if (!slot) return hideTooltip();
  if (activeSlot === slot) hideTooltip();
  else showTooltip(slot);
});
el("player-modal-backdrop").addEventListener("scroll", hideTooltip);

// --- Popup open/close ---

el("player-modal-close").addEventListener("click", closePlayerModal);
el("player-modal-backdrop").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closePlayerModal();
});
document.addEventListener("keydown", (e) => {
  if (modalUuid === null) return;
  if (e.key === "Escape") {
    closePlayerModal();
  } else if (e.key === "Tab") {
    // The close button is the only focusable thing in the dialog.
    e.preventDefault();
    el("player-modal-close").focus();
  }
});

// --- World ---

async function loadWorld() {
  const errorBox = el("world-error");
  try {
    const { res, data: w } = await fetchJson("/api/world");
    if (!res.ok || !w) throw new Error(errorText(res, w));

    if (w.error) {
      errorBox.innerHTML = banner(`World data unavailable: ${w.error}`);
      el("w-seed").textContent = "—";
      el("w-difficulty").textContent = "—";
      el("w-weather").textContent = "—";
      el("w-spawn").textContent = "—";
      el("w-gamerules").innerHTML = `<tr><td colspan="2" class="empty">Game rules unavailable</td></tr>`;
    } else {
      errorBox.innerHTML = "";
      el("w-seed").textContent = w.seed ?? "—";
      el("w-difficulty").textContent = w.difficulty + (w.difficulty_locked ? " (locked)" : "");
      el("w-weather").textContent = w.thundering ? "Thunderstorm" : w.raining ? "Rain" : "Clear";
      el("w-spawn").textContent = `${w.spawn.x}, ${w.spawn.y}, ${w.spawn.z}`;

      el("w-gamerules").innerHTML = Object.entries(w.game_rules)
        .map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`)
        .join("");
    }

    el("w-disk").innerHTML = (w.disk_usage || [])
      .map((d) => `<tr><td>${escapeHtml(d.path)}</td><td>${escapeHtml(d.size)}</td></tr>`)
      .join("");
  } catch (err) {
    errorBox.innerHTML = banner(`Couldn't load world data: ${err.message}`);
  }
}
