const MAP_VIEWBOX = { w: 1000, h: 500 };

// Stylized, low-poly continent silhouettes (not cartographically precise —
// this is a retro dashboard, not an atlas).
const CONTINENTS = [
  "M100,70 180,50 230,60 250,90 260,130 240,160 220,150 200,180 170,200 140,190 110,160 90,120 95,90 Z",
  "M230,240 270,230 300,260 310,320 295,380 270,420 250,400 235,340 225,280 Z",
  "M370,30 410,20 430,40 420,70 390,75 365,55 Z",
  "M470,70 520,55 545,70 540,95 510,110 480,105 465,90 Z",
  "M470,140 520,130 555,150 565,200 555,260 530,310 500,320 480,280 465,220 460,180 Z",
  "M560,60 650,40 730,50 800,70 840,100 850,140 820,170 780,160 760,200 720,220 680,210 650,180 610,160 590,120 570,90 Z",
  "M660,190 690,180 700,230 670,250 650,220 Z",
  "M750,240 770,235 780,255 760,265 745,255 Z",
  "M790,300 850,290 880,310 875,350 840,370 800,360 780,330 Z",
];

let state = null;
let selectedAirport = null;

const $ = (id) => document.getElementById(id);

function lonLatToXY(lon, lat) {
  const x = ((lon + 180) / 360) * MAP_VIEWBOX.w;
  const y = ((90 - lat) / 180) * MAP_VIEWBOX.h;
  return { x, y };
}

function initMap() {
  const svg = $("world-map");
  CONTINENTS.forEach((d) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("class", "continent");
    svg.appendChild(path);
  });
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function refresh() {
  const res = await fetch("/api/state");
  state = await res.json();
  render();
}

let heartClipCounter = 0;

function heartSvg(fillFraction) {
  const pct = Math.round(fillFraction * 100);
  const clipId = `heart-clip-${heartClipCounter++}`;
  return `<svg width="22" height="20" viewBox="0 0 32 29">
    <defs><clipPath id="${clipId}"><rect x="0" y="0" width="${(pct / 100) * 32}" height="29" /></clipPath></defs>
    <path d="M16 28 C 2 18, -2 8, 6 3 C 11 0, 15 2, 16 7 C 17 2, 21 0, 26 3 C 34 8, 30 18, 16 28 Z"
      fill="#e0e0c8" stroke="#4a2f2f" stroke-width="1.5"/>
    <path d="M16 28 C 2 18, -2 8, 6 3 C 11 0, 15 2, 16 7 C 17 2, 21 0, 26 3 C 34 8, 30 18, 16 28 Z"
      fill="#d1263b" stroke="#4a2f2f" stroke-width="1.5" clip-path="url(#${clipId})"/>
  </svg>`;
}

function renderHearts(lifeUnits, maxUnits) {
  const heartsCount = maxUnits / 2;
  let html = "";
  for (let i = 0; i < heartsCount; i++) {
    const remaining = lifeUnits - i * 2;
    const frac = Math.max(0, Math.min(2, remaining)) / 2;
    html += heartSvg(frac);
  }
  return html;
}

function renderNotices() {
  $("notices-list").innerHTML = state.notices.map((n) => `<li>${n}</li>`).join("");
}

function heatClass(heat, heatMax) {
  const frac = heat / heatMax;
  if (frac >= 0.75) return "heat-extreme";
  if (frac >= 0.5) return "heat-hot";
  if (frac >= 0.25) return "heat-warm";
  return "heat-calm";
}

function renderAirports() {
  $("airports-list").innerHTML = state.airports
    .map((a) => {
      const classes = [];
      if (a.code === state.location) classes.push("current");
      if (a.code === selectedAirport) classes.push("selected");
      const fare = a.is_current ? "" : `$${a.airfare.toLocaleString()}`;
      const heat = `<span class="heat-badge ${heatClass(a.heat, a.heat_max)}">🔥${a.heat}/${a.heat_max}</span>`;
      const covered = a.win_covered ? `<span class="covered-badge" title="Sold here — counts toward the win">✓</span>` : "";
      return `<li class="${classes.join(" ")}" data-code="${a.code}">
        <span>${covered}${a.name} ${heat}</span><span>${fare}</span>
      </li>`;
    })
    .join("");
  $("airports-list").querySelectorAll("li").forEach((li) => {
    li.addEventListener("click", () => {
      selectedAirport = li.dataset.code;
      render();
    });
  });
}

function renderMarket() {
  $("market-body").innerHTML = state.products
    .map((p) => {
      if (!p.unlocked) {
        return `<tr class="locked"><td>${p.name}</td><td colspan="4">unlocks at level ${p.unlock_level}</td></tr>`;
      }
      return `<tr data-key="${p.key}">
        <td>${p.name}</td>
        <td>$${p.price.toLocaleString()}</td>
        <td>${p.owned}</td>
        <td><input type="number" min="1" value="1" class="buy-qty" /></td>
        <td><button class="buy-btn">Buy</button></td>
      </tr>`;
    })
    .join("");
  $("market-body").querySelectorAll("tr[data-key]").forEach((tr) => {
    const key = tr.dataset.key;
    tr.querySelector(".buy-btn").addEventListener("click", async () => {
      const qty = parseInt(tr.querySelector(".buy-qty").value, 10) || 0;
      const result = await api("/api/buy", { product: key, qty });
      state = result.state;
      if (!result.ok) alert(result.error);
      render();
    });
  });
}

function renderProductSelect() {
  const sel = $("product-select");
  const prev = sel.value;
  sel.innerHTML = state.products
    .filter((p) => p.unlocked)
    .map((p) => `<option value="${p.key}">${p.name} (own ${p.owned})</option>`)
    .join("");
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
}

function renderLoadSelect() {
  const sel = $("load-select");
  sel.innerHTML = state.saves.map((s) => `<option value="${s}">${s}</option>`).join("");
}

function renderMapDots() {
  const svg = $("world-map");
  svg.querySelectorAll(".airport-dot, .travel-line").forEach((el) => el.remove());

  if (selectedAirport && selectedAirport !== state.location) {
    const origin = state.airports.find((a) => a.code === state.location);
    const dest = state.airports.find((a) => a.code === selectedAirport);
    const p1 = lonLatToXY(origin.lon, origin.lat);
    const p2 = lonLatToXY(dest.lon, dest.lat);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", p1.x);
    line.setAttribute("y1", p1.y);
    line.setAttribute("x2", p2.x);
    line.setAttribute("y2", p2.y);
    line.setAttribute("class", "travel-line");
    svg.appendChild(line);
  }

  state.airports.forEach((a) => {
    const { x, y } = lonLatToXY(a.lon, a.lat);
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const classes = ["airport-dot"];
    if (a.code === state.location) classes.push("current");
    if (a.code === selectedAirport) classes.push("selected");
    g.setAttribute("class", classes.join(" "));
    g.setAttribute("data-code", a.code);

    // Oversized invisible circle so the hover target is easier to hit than
    // the small visible dot.
    const hitArea = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    hitArea.setAttribute("cx", x);
    hitArea.setAttribute("cy", y);
    hitArea.setAttribute("r", 14);
    hitArea.setAttribute("fill", "transparent");

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", a.code === state.location ? 7 : 5);
    circle.setAttribute("fill", a.code === selectedAirport ? "#ff8a4c" : "#4a90d9");

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", x + 8);
    label.setAttribute("y", y + 3);
    label.textContent = a.code;

    g.appendChild(hitArea);
    g.appendChild(circle);
    g.appendChild(label);
    g.addEventListener("click", () => {
      selectedAirport = a.code;
      render();
    });
    g.addEventListener("mouseenter", (evt) => showMapTooltip(a, evt));
    g.addEventListener("mousemove", positionMapTooltip);
    g.addEventListener("mouseleave", hideMapTooltip);
    svg.appendChild(g);
  });
}

function showMapTooltip(airport, evt) {
  const prices = state.airport_prices[airport.code] || {};
  const rows = state.products
    .map((p) => {
      if (!p.unlocked) {
        return `<div class="tooltip-row locked"><span>${p.name}</span><span>Lvl ${p.unlock_level}</span></div>`;
      }
      const price = prices[p.key];
      return `<div class="tooltip-row"><span>${p.name}</span><span>$${price.toLocaleString()}</span></div>`;
    })
    .join("");
  const heat = `<div class="tooltip-row heat-line ${heatClass(airport.heat, airport.heat_max)}">
    <span>Heat</span><span>🔥${airport.heat}/${airport.heat_max}</span></div>`;
  const tooltip = $("map-tooltip");
  tooltip.innerHTML = `<span class="tooltip-title">${airport.name}</span>${heat}${rows}`;
  tooltip.classList.remove("hidden");
  positionMapTooltip(evt);
}

function positionMapTooltip(evt) {
  const tooltip = $("map-tooltip");
  if (tooltip.classList.contains("hidden")) return;
  const panelRect = $("world-map").closest(".map-panel").getBoundingClientRect();
  let left = evt.clientX - panelRect.left + 14;
  let top = evt.clientY - panelRect.top + 14;
  const maxLeft = panelRect.width - tooltip.offsetWidth - 6;
  const maxTop = panelRect.height - tooltip.offsetHeight - 6;
  tooltip.style.left = `${Math.max(6, Math.min(left, maxLeft))}px`;
  tooltip.style.top = `${Math.max(6, Math.min(top, maxTop))}px`;
}

function hideMapTooltip() {
  $("map-tooltip").classList.add("hidden");
}

function animatePlane(originCode, destCode) {
  const svg = $("world-map");
  const origin = state.airports.find((a) => a.code === originCode);
  const dest = state.airports.find((a) => a.code === destCode);
  if (!origin || !dest) return;
  const p1 = lonLatToXY(origin.lon, origin.lat);
  const p2 = lonLatToXY(dest.lon, dest.lat);
  const plane = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  plane.setAttribute("r", 6);
  plane.setAttribute("class", "travel-plane");
  svg.appendChild(plane);
  const start = performance.now();
  const duration = 900;
  function step(now) {
    const t = Math.min(1, (now - start) / duration);
    plane.setAttribute("cx", p1.x + (p2.x - p1.x) * t);
    plane.setAttribute("cy", p1.y + (p2.y - p1.y) * t);
    if (t < 1) requestAnimationFrame(step);
    else plane.remove();
  }
  requestAnimationFrame(step);
}

function renderOverlay() {
  const overlay = $("game-over-overlay");
  if (state.game_over) {
    overlay.classList.remove("hidden");
    $("overlay-title").textContent = state.win ? "✈️🔥 YOU WIN! 🔥✈️" : "Game Over";
    $("overlay-message").textContent = state.game_over_reason;
  } else {
    overlay.classList.add("hidden");
  }
}

function render() {
  $("wallet-value").textContent = `$${state.cash.toLocaleString()}`;
  $("net-worth-value").textContent = `$${state.net_worth.toLocaleString()}`;
  $("net-worth-goal").textContent = `$${state.net_worth_goal.toLocaleString()}`;
  $("airports-covered-value").textContent = state.airports_covered;
  $("airports-total-value").textContent = state.airports_total;
  $("debt-value").textContent = `$${state.debt.toLocaleString()}`;
  $("life-hearts").innerHTML = renderHearts(state.life, state.life_max);
  $("day-value").textContent = state.day;
  $("level-value").textContent = `Lvl ${state.level} · ${state.sales_since_day}/${state.sales_per_day} sales today`;

  const statusBits = [];
  if (state.protected_airport === state.location) statusBits.push("🛡️ Mobster protection active");
  if (state.price_discount_airport === state.location) statusBits.push("🍍 Pineapple Express: prices down 25%");
  $("status-effects").textContent = statusBits.join(" · ");

  renderNotices();
  renderAirports();
  renderMarket();
  renderProductSelect();
  renderLoadSelect();
  renderMapDots();
  renderOverlay();
}

async function handleReset() {
  if (!confirm("Reset the game and lose current progress?")) return;
  const result = await api("/api/reset");
  state = result.state;
  selectedAirport = null;
  render();
}

function wireControls() {
  $("attempt-sale-btn").addEventListener("click", async () => {
    const product = $("product-select").value;
    const qty = parseInt($("sale-qty").value, 10) || 0;
    if (!product) return alert("Pick a product first.");
    const result = await api("/api/sell", { product, qty });
    state = result.state;
    if (!result.ok) alert(result.error);
    render();
  });

  $("travel-btn").addEventListener("click", async () => {
    if (!selectedAirport) return alert("Click an airport on the map or list first.");
    const origin = state.location;
    const result = await api("/api/travel", { destination: selectedAirport });
    if (!result.ok) {
      alert(result.error);
      return;
    }
    state = result.state;
    render();
    animatePlane(origin, state.location);
  });

  $("reset-btn").addEventListener("click", handleReset);
  $("overlay-reset-btn").addEventListener("click", handleReset);

  $("save-btn").addEventListener("click", async () => {
    const name = $("save-name").value.trim() || "save";
    const result = await api("/api/save", { name });
    state = result.state;
    render();
  });

  $("load-btn").addEventListener("click", async () => {
    const name = $("load-select").value;
    if (!name) return alert("No saves yet.");
    const result = await api("/api/load", { name });
    if (!result.ok) return alert(result.error);
    state = result.state;
    selectedAirport = null;
    render();
  });
}

initMap();
wireControls();
refresh();
