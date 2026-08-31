let state = null;
let selectedAirport = null;

let leafletMap = null;
let markersLayer = null;
let travelLine = null;
let mapFitted = false;

const $ = (id) => document.getElementById(id);

function initMap() {
  leafletMap = L.map("world-map", { minZoom: 1, maxZoom: 7 }).setView([15, 10], 2);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(leafletMap);

  markersLayer = L.layerGroup().addTo(leafletMap);

  // The map panel is sized by CSS flexbox/grid, which can settle after
  // Leaflet's first measurement — recheck once layout is definitely done,
  // and again on any window resize.
  setTimeout(() => leafletMap.invalidateSize(), 0);
  window.addEventListener("resize", () => leafletMap.invalidateSize());
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (res.status === 401) {
    window.location.href = "/";
    return new Promise(() => {}); // navigation is in flight; don't resolve
  }
  return res.json();
}

async function refresh() {
  const res = await fetch("/api/state");
  if (res.status === 401) {
    window.location.href = "/";
    return;
  }
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

function airportTooltipHtml(airport) {
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
  return `<div class="airport-tooltip"><span class="tooltip-title">${airport.name}</span>${heat}${rows}</div>`;
}

function renderMap() {
  markersLayer.clearLayers();
  if (travelLine) {
    leafletMap.removeLayer(travelLine);
    travelLine = null;
  }

  if (!mapFitted) {
    const bounds = L.latLngBounds(state.airports.map((a) => [a.lat, a.lon]));
    leafletMap.fitBounds(bounds, { padding: [24, 24] });
    mapFitted = true;
  }

  if (selectedAirport && selectedAirport !== state.location) {
    const origin = state.airports.find((a) => a.code === state.location);
    const dest = state.airports.find((a) => a.code === selectedAirport);
    travelLine = L.polyline(
      [
        [origin.lat, origin.lon],
        [dest.lat, dest.lon],
      ],
      { color: "#4a2f2f", weight: 2, dashArray: "6,5" }
    ).addTo(leafletMap);
  }

  state.airports.forEach((a) => {
    const isCurrent = a.code === state.location;
    const isSelected = a.code === selectedAirport;
    const marker = L.circleMarker([a.lat, a.lon], {
      radius: isCurrent ? 9 : 6,
      color: "#4a2f2f",
      weight: 1.5,
      fillColor: isCurrent ? "#fbf35b" : isSelected ? "#ff8a4c" : "#4a90d9",
      fillOpacity: 1,
    });
    marker.bindTooltip(airportTooltipHtml(a), { direction: "top", offset: [0, -6] });
    marker.on("click", () => {
      selectedAirport = a.code;
      render();
    });
    marker.addTo(markersLayer);
  });
}

function animatePlane(originCode, destCode) {
  const origin = state.airports.find((a) => a.code === originCode);
  const dest = state.airports.find((a) => a.code === destCode);
  if (!origin || !dest) return;
  const plane = L.circleMarker([origin.lat, origin.lon], {
    radius: 6,
    color: "#4a2f2f",
    weight: 1,
    fillColor: "#ff5a3c",
    fillOpacity: 1,
  }).addTo(leafletMap);
  const start = performance.now();
  const duration = 900;
  function step(now) {
    const t = Math.min(1, (now - start) / duration);
    plane.setLatLng([
      origin.lat + (dest.lat - origin.lat) * t,
      origin.lon + (dest.lon - origin.lon) * t,
    ]);
    if (t < 1) requestAnimationFrame(step);
    else leafletMap.removeLayer(plane);
  }
  requestAnimationFrame(step);
}

function renderOverlay() {
  const overlay = $("game-over-overlay");
  if (state.game_over) {
    overlay.classList.remove("hidden");
    $("overlay-title").textContent = state.win ? "✈️🔥 YOU WIN! 🔥✈️" : "Game Over";
    $("overlay-message").textContent = state.game_over_reason;
    $("overlay-leaderboard-link").classList.toggle("hidden", !state.win);
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
  renderMap();
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
  $("logout-link").addEventListener("click", async (evt) => {
    evt.preventDefault();
    await api("/api/logout");
    window.location.href = "/";
  });

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
