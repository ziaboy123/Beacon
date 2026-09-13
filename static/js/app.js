const DESTRUCTIVE_PATTERNS = [/^stop\b/, /^ban\b/, /^ban-ip\b/, /^kick\b/, /^op\b/, /^deop\b/, /^save-off\b/];

function isDestructive(cmd) {
  const c = cmd.trim().toLowerCase();
  return DESTRUCTIVE_PATTERNS.some((re) => re.test(c));
}

function el(id) {
  return document.getElementById(id);
}

// --- Nav ---

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((i) => i.classList.remove("active"));
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    item.classList.add("active");
    el(`page-${item.dataset.page}`).classList.add("active");
    if (item.dataset.page === "console") connectConsole();
    if (item.dataset.page === "whitelist") loadWhitelist();
    if (item.dataset.page === "players") loadPlayers();
    if (item.dataset.page === "world") loadWorld();
  });
});

// --- Overview / status ---

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    const dot = el("status-dot");
    const statusText = el("status-text");
    dot.className = "dot " + (data.online ? "online" : "offline");
    statusText.textContent = data.online ? "online" : "offline";

    el("ov-status").textContent = data.online ? "Online" : "Offline";
    el("ov-players").textContent = `${data.players_online} / ${data.players_max}`;
    el("ov-tps").textContent = data.tps ? data.tps.map((t) => t.toFixed(1)).join(" / ") : "—";
    el("ov-uptime").textContent = data.uptime_since || "—";
    el("ov-motd").textContent = data.motd || "—";

    const errorBox = el("overview-error");
    errorBox.innerHTML = data.error
      ? `<div class="error-banner">${escapeHtml(data.error)}</div>`
      : "";

    const list = el("ov-online-list");
    if (data.player_names && data.player_names.length) {
      list.innerHTML = data.player_names.map((n) => `<span class="badge">${escapeHtml(n)}</span>`).join(" ");
    } else {
      list.innerHTML = `<div class="empty">No one online</div>`;
    }
  } catch (err) {
    el("status-text").textContent = "unreachable";
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  // innerHTML only escapes <>& — also escape quotes so this is safe to
  // drop into a quoted HTML attribute (e.g. title="..."), not just text.
  return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

loadStatus();
setInterval(loadStatus, 5000);

async function loadOverviewExtras() {
  try {
    const whitelist = await fetch("/api/whitelist").then((r) => r.json());
    el("ov-whitelisted").textContent = whitelist.length;
  } catch (err) {
    el("ov-whitelisted").textContent = "—";
  }

  try {
    const world = await fetch("/api/world").then((r) => r.json());
    if (!world.error) {
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

function connectConsole() {
  if (consoleSocket && consoleSocket.readyState === WebSocket.OPEN) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  consoleSocket = new WebSocket(`${proto}://${location.host}/ws/console`);
  const logEl = el("console-log");
  consoleSocket.addEventListener("message", (event) => {
    const line = document.createElement("div");
    line.className = "line";
    line.textContent = event.data;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  });
}

async function sendCommand() {
  const input = el("console-input");
  const cmd = input.value.trim();
  if (!cmd) return;

  if (isDestructive(cmd) && !confirm(`Run potentially destructive command: /${cmd}?`)) {
    return;
  }

  const logEl = el("console-log");
  const line = document.createElement("div");
  line.className = "line attn";
  line.textContent = `> /${cmd}`;
  logEl.appendChild(line);

  input.value = "";
  try {
    const res = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd }),
    });
    const data = await res.json();
    const respLine = document.createElement("div");
    respLine.className = "line";
    respLine.textContent = res.ok ? data.response : `Error: ${data.detail || "unknown error"}`;
    logEl.appendChild(respLine);
    logEl.scrollTop = logEl.scrollHeight;
  } catch (err) {
    const respLine = document.createElement("div");
    respLine.className = "line";
    respLine.textContent = `Error: ${err}`;
    logEl.appendChild(respLine);
  }
}

el("console-send").addEventListener("click", sendCommand);
el("console-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendCommand();
});

// --- Whitelist ---

async function loadWhitelist() {
  const body = el("whitelist-body");
  body.innerHTML = `<tr><td colspan="3" class="empty">Loading...</td></tr>`;
  try {
    const res = await fetch("/api/whitelist");
    const entries = await res.json();
    if (!entries.length) {
      body.innerHTML = `<tr><td colspan="3" class="empty">No one whitelisted</td></tr>`;
      return;
    }
    body.innerHTML = entries
      .map(
        (e) => `
      <tr>
        <td>${escapeHtml(e.name)}${e.is_op ? `<span class="badge op">OP ${e.op_level ?? ""}</span>` : ""}</td>
        <td>${escapeHtml(e.uuid)}</td>
        <td><button class="danger" data-remove="${escapeHtml(e.name)}">Remove</button></td>
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
  await fetch(`/api/whitelist/${encodeURIComponent(name)}`, { method: "DELETE" });
  loadWhitelist();
}

el("whitelist-add").addEventListener("click", async () => {
  const input = el("whitelist-username");
  const username = input.value.trim();
  if (!username) return;
  const errorBox = el("whitelist-error");
  errorBox.innerHTML = "";
  try {
    const res = await fetch("/api/whitelist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await res.json();
    if (!res.ok) {
      errorBox.innerHTML = `<div class="error-banner">${escapeHtml(data.detail || "Failed to add")}</div>`;
      return;
    }
    input.value = "";
    loadWhitelist();
  } catch (err) {
    errorBox.innerHTML = `<div class="error-banner">${err}</div>`;
  }
});

// --- Players ---

let allPlayers = [];

async function loadPlayers() {
  const body = el("players-body");
  body.innerHTML = `<tr><td colspan="2" class="empty">Loading...</td></tr>`;
  try {
    const res = await fetch("/api/players");
    allPlayers = await res.json();
    renderPlayers(allPlayers);
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
      <td>${escapeHtml(p.name)}</td>
      <td>${p.online ? '<span class="dot online" style="display:inline-block"></span> online' : "offline"}</td>
    </tr>`
    )
    .join("");
  body.querySelectorAll("tr[data-uuid]").forEach((row) => {
    row.addEventListener("click", () => openPlayerModal(row.dataset.uuid, row.dataset.name));
  });
}

el("players-search").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  renderPlayers(allPlayers.filter((p) => p.name.toLowerCase().includes(q)));
});

let playerModalRefreshTimer = null;

function openPlayerModal(uuid, name) {
  el("player-modal-name").textContent = name;
  el("player-modal-body").innerHTML = `<div class="empty">Loading...</div>`;
  el("player-modal-backdrop").classList.add("active");

  loadPlayerModalContent(uuid);
  if (playerModalRefreshTimer) clearInterval(playerModalRefreshTimer);
  playerModalRefreshTimer = setInterval(() => loadPlayerModalContent(uuid), 4000);
}

function closePlayerModal() {
  el("player-modal-backdrop").classList.remove("active");
  if (playerModalRefreshTimer) {
    clearInterval(playerModalRefreshTimer);
    playerModalRefreshTimer = null;
  }
}

async function loadPlayerModalContent(uuid) {
  const bodyEl = el("player-modal-body");

  const [statsRes, invRes] = await Promise.allSettled([
    fetch(`/api/players/${uuid}/stats`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    fetch(`/api/players/${uuid}/inventory`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
  ]);

  let html = "";

  html += `<div class="section-title">Stats</div>`;
  if (statsRes.status === "fulfilled") {
    const s = statsRes.value;
    html += `<div class="grid">`;
    for (const [label, value] of Object.entries(s.summary)) {
      html += `<div class="card"><div class="label">${escapeHtml(label)}</div><div class="value small">${value}</div></div>`;
    }
    html += `</div>`;
    if (s.top_mined.length) {
      html += `<div class="section-title">Top Mined</div>`;
      html += s.top_mined.map((m) => `<span class="badge">${shortName(m.item)} × ${m.count}</span>`).join(" ");
    }
    if (s.top_killed.length) {
      html += `<div class="section-title">Top Kills</div>`;
      html += s.top_killed.map((k) => `<span class="badge">${shortName(k.entity)} × ${k.count}</span>`).join(" ");
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
    html += `<div style="margin-bottom:8px;color:var(--text-dim)">Health ${inv.health} · Food ${inv.food_level} · XP Level ${inv.xp_level} · ${gamemode} · ${escapeHtml(inv.dimension)} · (${coords})</div>`;
    html += renderSlotGroup("Hotbar", inv.inventory.hotbar);
    html += renderSlotGroup("Main Inventory", inv.inventory.main);
    html += renderSlotGroup("Armor", armorOrder, true);
    html += renderSlotGroup("Offhand", [inv.inventory.offhand], true);
    if (inv.inventory.other.length) html += renderSlotGroup("Other", inv.inventory.other, true);
    html += renderSlotGroup("Ender Chest", inv.ender_chest);
  } else {
    html += `<div class="empty">No playerdata available</div>`;
  }

  bodyEl.innerHTML = html;
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

// items: array of item-or-null, one per real inventory slot — nulls render
// as empty slot boxes so gaps line up with the player's actual layout.
function renderSlotGroup(title, items, narrow) {
  if (!items || !items.length) return "";
  const slots = items
    .map((it) => {
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
      return `<div class="slot${enchantedClass}">
        <img src="${iconSrc}" alt="${escapeHtml(displayName)}" loading="lazy" />
        ${countBadge}
        ${tooltipHtml}
      </div>`;
    })
    .join("");
  const gridClass = narrow ? "slot-grid slot-grid-narrow" : "slot-grid";
  return `<div class="section-title">${title}</div><div class="${gridClass}">${slots}</div>`;
}

el("player-modal-close").addEventListener("click", closePlayerModal);
el("player-modal-backdrop").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closePlayerModal();
});

// --- World ---

async function loadWorld() {
  try {
    const res = await fetch("/api/world");
    const w = await res.json();

    if (w.error) {
      el("w-seed").textContent = "—";
      el("w-difficulty").textContent = "—";
      el("w-weather").textContent = "—";
      el("w-spawn").textContent = "—";
    } else {
      el("w-seed").textContent = w.seed ?? "—";
      el("w-difficulty").textContent = w.difficulty + (w.difficulty_locked ? " (locked)" : "");
      el("w-weather").textContent = w.thundering ? "Thunderstorm" : w.raining ? "Rain" : "Clear";
      el("w-spawn").textContent = `${w.spawn.x}, ${w.spawn.y}, ${w.spawn.z}`;

      const rulesBody = el("w-gamerules");
      rulesBody.innerHTML = Object.entries(w.game_rules)
        .map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`)
        .join("");
    }

    const diskBody = el("w-disk");
    diskBody.innerHTML = (w.disk_usage || [])
      .map((d) => `<tr><td>${escapeHtml(d.path)}</td><td>${escapeHtml(d.size)}</td></tr>`)
      .join("");
  } catch (err) {
    // leave placeholders
  }
}
