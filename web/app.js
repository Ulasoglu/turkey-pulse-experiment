const CATEGORY_META = {
  ALL: { label: "Tümü", icon: "••", css: "all" },
  EARTHQUAKE: { label: "Deprem", icon: "✦", css: "earthquake" },
  WEATHER: { label: "Hava Durumu", short: "Hava", icon: "⌁", css: "weather" },
  TRAFFIC: { label: "Trafik", icon: "▰", css: "traffic" },
  INFRASTRUCTURE: { label: "Altyapı", icon: "⌂", css: "infrastructure" },
  EVENT: { label: "Etkinlik", icon: "▣", css: "event" },
  OTHER: { label: "Yerel Gelişmeler", short: "Yerel", icon: "●", css: "other" },
};

const GEOJSON_URL = "https://raw.githubusercontent.com/cihadturhan/tr-geojson/master/geo/tr-cities-utf8.json";
const FALLBACK_BOUNDS = L.latLngBounds([35.7, 25.5], [42.2, 44.9]);
const FALLBACK_CENTERS = {
  İstanbul:[41.0082,28.9784], Ankara:[39.9334,32.8597], İzmir:[38.4237,27.1428], Bursa:[40.1885,29.061], Konya:[37.8746,32.4932], Samsun:[41.2867,36.33], Antalya:[36.8969,30.7133], Çorum:[40.5506,34.9556], Bayburt:[40.2552,40.2249], Balıkesir:[39.6484,27.8826], Malatya:[38.3552,38.3095], Manisa:[38.6191,27.4289], Denizli:[37.7765,29.0864], Elazığ:[38.681,39.2264], Adana:[36.9914,35.3308], Gaziantep:[37.0662,37.3833], Diyarbakır:[37.9144,40.2306], Trabzon:[41.0015,39.7178], Erzurum:[39.9043,41.2679], Van:[38.4891,43.4089]
};

let signals = [];
let selectedProvince = null;
let selectedTime = "today";
let selectedCategory = "ALL";
let map;
let provinceLayer;
let markersLayer;
let labelsLayer;
let turkeyBounds = FALLBACK_BOUNDS;
let provinceCenters = { ...FALLBACK_CENTERS };
let provinceLayers = new Map();
let favorites = new Set(JSON.parse(localStorage.getItem("tp:favorites") || "[]"));

const el = (id) => document.getElementById(id);
const searchInput = el("searchInput");
const statusText = el("statusText");
const desktopFeedList = el("desktopFeedList");
const mobileFeedList = el("mobileFeedList");
const feedTitle = el("feedTitle");
const feedSubtitle = el("feedSubtitle");
const mobileFeedTitle = el("mobileFeedTitle");
const mobileFeedSubtitle = el("mobileFeedSubtitle");
const favoriteButton = el("favoriteButton");
const mobileFavoriteButton = el("mobileFavoriteButton");
const mobileSheet = el("mobileSheet");
const template = el("feedCardTemplate");

function normalizeProvinceName(name) {
  if (!name) return null;
  const aliases = { Istanbul: "İstanbul", Izmir: "İzmir", Mugla: "Muğla", Sanliurfa: "Şanlıurfa", Kirikkale: "Kırıkkale", Kirklareli: "Kırklareli", Kirsehir: "Kırşehir", Diyarbakir: "Diyarbakır", Eskisehir: "Eskişehir", Gumushane: "Gümüşhane", Canakkale: "Çanakkale", Cankiri: "Çankırı", Corum: "Çorum", Agri: "Ağrı", Igdir: "Iğdır", Sirnak: "Şırnak", Usak: "Uşak" };
  return aliases[name] || name;
}

function initMap() {
  map = L.map("map", {
    zoomControl: false,
    attributionControl: false,
    minZoom: 5,
    maxZoom: 10,
    zoomSnap: 0.25,
    preferCanvas: true,
  });
  map.fitBounds(FALLBACK_BOUNDS, { padding: [18, 18] });
  markersLayer = L.layerGroup().addTo(map);
  labelsLayer = L.layerGroup().addTo(map);
}

function baseProvinceStyle(feature) {
  const name = normalizeProvinceName(feature?.properties?.name);
  const selected = selectedProvince && name === selectedProvince;
  return {
    color: selected ? "#9caaa5" : "#d8ddd6",
    weight: selected ? 1.8 : 0.8,
    fillColor: selected ? "#fffdf4" : "#f6f4e9",
    fillOpacity: 1,
  };
}

async function loadTurkeyMap() {
  try {
    const response = await fetch(GEOJSON_URL, { cache: "force-cache" });
    if (!response.ok) throw new Error(`GeoJSON HTTP ${response.status}`);
    const geojson = await response.json();
    provinceLayer = L.geoJSON(geojson, {
      style: baseProvinceStyle,
      onEachFeature(feature, layer) {
        const name = normalizeProvinceName(feature?.properties?.name);
        if (!name) return;
        provinceLayers.set(name, layer);
        provinceCenters[name] = [layer.getBounds().getCenter().lat, layer.getBounds().getCenter().lng];
        layer.on({
          mouseover: () => layer.setStyle({ fillColor: "#fffdf5", weight: 1.3 }),
          mouseout: () => refreshProvinceStyles(),
          click: () => selectProvince(name, true),
        });
      },
    }).addTo(map);
    turkeyBounds = provinceLayer.getBounds();
    map.setMaxBounds(turkeyBounds.pad(0.08));
    map.options.maxBoundsViscosity = 1;
    fitTurkey();
  } catch (error) {
    console.error("Province map could not be loaded", error);
    map.setMaxBounds(FALLBACK_BOUNDS.pad(0.08));
    fitTurkey();
  }
}

function fitTurkey() {
  const mobilePadding = window.innerWidth <= 820 ? [8, 18] : [26, 42];
  map.fitBounds(turkeyBounds, { padding: mobilePadding, animate: true, duration: 0.35 });
}

function refreshProvinceStyles() {
  if (provinceLayer) provinceLayer.setStyle(baseProvinceStyle);
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function passesTime(signal) {
  const date = parseDate(signal.published_at);
  const now = new Date();
  if (selectedTime === "now") return signal.freshness === "NOW";
  if (!date) return selectedTime === "7d";
  if (selectedTime === "today") {
    return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
  }
  const from = new Date(now.getTime() - 7 * 86400000);
  const to = new Date(now.getTime() + 7 * 86400000);
  return date >= from && date <= to;
}

function visibleSignals({ ignoreProvince = false } = {}) {
  const query = searchInput.value.trim().toLocaleLowerCase("tr-TR");
  return signals.filter((signal) => {
    if (!passesTime(signal)) return false;
    if (selectedCategory !== "ALL" && signal.category !== selectedCategory) return false;
    if (!ignoreProvince && selectedProvince && signal.province !== selectedProvince) return false;
    if (!query) return true;
    return `${signal.province || ""} ${signal.title || ""}`.toLocaleLowerCase("tr-TR").includes(query);
  });
}

function signalPosition(signal) {
  if (Number.isFinite(signal.latitude) && Number.isFinite(signal.longitude)) return [signal.latitude, signal.longitude];
  return provinceCenters[signal.province] || null;
}

function categoryMeta(category) {
  return CATEGORY_META[category] || CATEGORY_META.OTHER;
}

function signalPriority(signal) {
  if (signal.relevance === "HIGH") return "high";
  if (signal.relevance === "LOW") return "low";
  return "normal";
}

function renderMapLayers() {
  markersLayer.clearLayers();
  labelsLayer.clearLayers();
  const filtered = visibleSignals();
  const groups = new Map();

  for (const signal of filtered) {
    const position = signalPosition(signal);
    if (!position) continue;
    const precise = Number.isFinite(signal.latitude) && Number.isFinite(signal.longitude);
    const key = precise ? `signal:${signal.id}` : `province:${signal.province}:${signal.category}`;
    if (!groups.has(key)) groups.set(key, { signals: [], position });
    groups.get(key).signals.push(signal);
  }

  for (const group of groups.values()) {
    const first = group.signals[0];
    const meta = categoryMeta(first.category);
    const count = group.signals.reduce((sum, item) => sum + (item.signal_count || 1), 0);
    const priority = group.signals.some((item) => signalPriority(item) === "high") ? "high" : signalPriority(first);
    const icon = L.divIcon({
      className: "pulse-marker-wrap",
      html: `<div class="pulse-marker ${meta.css} ${priority}">${count}</div>`,
      iconSize: [42, 42],
      iconAnchor: [21, 21],
    });
    L.marker(group.position, { icon, keyboard: true })
      .addTo(markersLayer)
      .on("click", () => selectProvince(first.province, true));
  }

  const provincesToLabel = new Set(filtered.map((s) => s.province).filter(Boolean));
  for (const province of provincesToLabel) {
    const position = provinceCenters[province];
    if (!position) continue;
    const label = L.divIcon({
      className: "province-label-wrap",
      html: `<span class="province-label">${province}</span>`,
      iconSize: [90, 20],
      iconAnchor: [45, -13],
    });
    L.marker(position, { icon: label, interactive: false }).addTo(labelsLayer);
  }

  statusText.textContent = `${filtered.length} gelişme`;
}

function formatTime(value) {
  const date = parseDate(value);
  if (!date) return "--:--";
  return new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" }).format(date);
}

function timeLabel() {
  if (selectedTime === "now") return "Şimdi";
  if (selectedTime === "7d") return "7 Gün";
  return "Bugün";
}

function categoryLabel() {
  return selectedCategory === "ALL" ? "Tümü" : (categoryMeta(selectedCategory).short || categoryMeta(selectedCategory).label);
}

function createFeedCard(signal) {
  const fragment = template.content.cloneNode(true);
  const article = fragment.querySelector(".feed-card");
  const meta = categoryMeta(signal.category);
  const priority = signalPriority(signal);
  const icon = fragment.querySelector(".feed-row-icon");
  icon.className = `feed-row-icon ${meta.css}`;
  icon.textContent = meta.icon;
  fragment.querySelector(".category-name").textContent = meta.label.toUpperCase();
  fragment.querySelector("time").textContent = formatTime(signal.published_at);
  fragment.querySelector("h3").textContent = signal.title;
  fragment.querySelector(".feed-place").textContent = signal.province || "Türkiye";
  fragment.querySelector(".feed-source").textContent = `Kaynak: ${signal.source_id || "Resmî kaynak"}`;
  const pill = fragment.querySelector(".priority-pill");
  pill.className = `priority-pill ${priority}`;
  pill.textContent = priority === "high" ? "Yüksek" : priority === "low" ? "Düşük" : "Normal";
  const sourceLink = fragment.querySelector(".source-link");
  if (signal.source_url && /^https?:\/\//.test(signal.source_url)) sourceLink.href = signal.source_url;
  else sourceLink.remove();
  fragment.querySelector(".show-on-map").addEventListener("click", () => {
    const position = signalPosition(signal);
    if (position) map.flyTo(position, Number.isFinite(signal.latitude) ? 9 : 7, { duration: 0.4 });
  });
  article.addEventListener("click", (event) => {
    if (event.target.closest("button,a")) return;
    selectProvince(signal.province, true);
  });
  return fragment;
}

function renderFeeds() {
  const filtered = visibleSignals();
  const title = selectedProvince ? `${selectedProvince} · ${categoryLabel()}` : `${timeLabel()} · ${categoryLabel()}`;
  const subtitle = `${filtered.length} gelişme bulundu`;
  feedTitle.textContent = title;
  mobileFeedTitle.textContent = title;
  feedSubtitle.textContent = subtitle;
  mobileFeedSubtitle.textContent = subtitle;
  desktopFeedList.innerHTML = "";
  mobileFeedList.innerHTML = "";

  if (!filtered.length) {
    const empty = `<div class="empty-state"><strong>Şu anda yeni bir gelişme yok.</strong><span>Başka bir filtre veya şehir deneyebilirsin.</span></div>`;
    desktopFeedList.innerHTML = empty;
    mobileFeedList.innerHTML = empty;
  } else {
    for (const signal of filtered.slice(0, 30)) {
      desktopFeedList.appendChild(createFeedCard(signal));
      mobileFeedList.appendChild(createFeedCard(signal));
    }
  }
  updateFavoriteButtons();
}

function renderCategories() {
  const available = ["ALL", ...Object.keys(CATEGORY_META).filter((key) => key !== "ALL" && signals.some((s) => s.category === key))];
  const desktop = el("desktopCategories");
  const mobile = el("mobileCategories");
  desktop.innerHTML = "";
  mobile.innerHTML = "";

  for (const category of available) {
    const meta = CATEGORY_META[category];
    const desktopButton = document.createElement("button");
    desktopButton.className = `category-button ${meta.css}${selectedCategory === category ? " active" : ""}`;
    desktopButton.innerHTML = `<span class="category-icon">${meta.icon}</span><span>${meta.label}</span>`;
    desktopButton.addEventListener("click", () => setCategory(category));
    desktop.appendChild(desktopButton);

    const mobileButton = document.createElement("button");
    mobileButton.className = `mobile-category ${meta.css}${selectedCategory === category ? " active" : ""}`;
    mobileButton.innerHTML = `<span class="category-icon">${meta.icon}</span><small>${meta.short || meta.label}</small>`;
    mobileButton.addEventListener("click", () => setCategory(category));
    mobile.appendChild(mobileButton);
  }
}

function renderTimeButtons() {
  document.querySelectorAll("[data-time]").forEach((button) => {
    button.classList.toggle("active", button.dataset.time === selectedTime);
  });
}

function render() {
  renderTimeButtons();
  renderCategories();
  renderMapLayers();
  renderFeeds();
  refreshProvinceStyles();
}

function setCategory(category) {
  selectedCategory = category;
  render();
}

function selectProvince(province, openSheet = false) {
  if (!province) return;
  selectedProvince = selectedProvince === province ? null : province;
  render();
  if (selectedProvince) {
    const layer = provinceLayers.get(selectedProvince);
    if (layer) map.flyToBounds(layer.getBounds(), { padding: [55, 55], maxZoom: 7.3, duration: 0.4 });
    else if (provinceCenters[selectedProvince]) map.flyTo(provinceCenters[selectedProvince], 7, { duration: 0.4 });
  } else {
    fitTurkey();
  }
  if (openSheet && window.innerWidth <= 820) mobileSheet.classList.add("open");
}

function saveFavorites() {
  localStorage.setItem("tp:favorites", JSON.stringify([...favorites]));
}

function toggleFavorite() {
  if (!selectedProvince) return;
  favorites.has(selectedProvince) ? favorites.delete(selectedProvince) : favorites.add(selectedProvince);
  saveFavorites();
  updateFavoriteButtons();
}

function updateFavoriteButtons() {
  const active = selectedProvince && favorites.has(selectedProvince);
  [favoriteButton, mobileFavoriteButton].forEach((button) => {
    button.style.visibility = selectedProvince ? "visible" : "hidden";
    button.classList.toggle("active", Boolean(active));
    button.textContent = active ? "★" : "☆";
  });
}

function openFavorites() {
  if (!favorites.size) {
    alert("Henüz favori şehrin yok. Haritadan bir şehir seçip yıldızla kaydedebilirsin.");
    return;
  }
  selectProvince([...favorites][0], true);
}

function focusSearch() {
  searchInput.focus();
  if (window.innerWidth <= 820) mobileSheet.classList.remove("open");
}

for (const button of document.querySelectorAll("[data-time]")) {
  button.addEventListener("click", () => {
    selectedTime = button.dataset.time;
    render();
  });
}

searchInput.addEventListener("input", () => {
  const query = searchInput.value.trim().toLocaleLowerCase("tr-TR");
  if (!query) selectedProvince = null;
  else {
    const province = [...new Set(signals.map((s) => s.province).filter(Boolean))]
      .find((name) => name.toLocaleLowerCase("tr-TR").startsWith(query));
    if (province) selectedProvince = province;
  }
  render();
});

favoriteButton.addEventListener("click", toggleFavorite);
mobileFavoriteButton.addEventListener("click", toggleFavorite);
el("desktopFavorites").addEventListener("click", openFavorites);
el("mobileFavorites").addEventListener("click", openFavorites);
el("desktopSearchNav").addEventListener("click", focusSearch);
el("mobileSearch").addEventListener("click", focusSearch);
el("mobileDevelopments").addEventListener("click", () => mobileSheet.classList.add("open"));
el("showAllDesktop").addEventListener("click", () => { selectedProvince = null; render(); fitTurkey(); });
el("resetMapButton").addEventListener("click", () => { selectedProvince = null; searchInput.value = ""; render(); fitTurkey(); });
el("sheetHandle").addEventListener("click", () => mobileSheet.classList.toggle("open"));
el("mobileMenuButton").addEventListener("click", () => mobileSheet.classList.toggle("open"));

window.addEventListener("resize", () => {
  if (!map) return;
  map.invalidateSize();
});

async function boot() {
  initMap();
  const [mapResult, signalsResult] = await Promise.allSettled([
    loadTurkeyMap(),
    fetch("data/signals.json", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`Signals HTTP ${response.status}`);
      return response.json();
    }),
  ]);

  if (signalsResult.status === "fulfilled") signals = signalsResult.value;
  else {
    console.error(signalsResult.reason);
    statusText.textContent = "Veriler şu anda yüklenemedi";
  }
  render();
  if (mapResult.status === "rejected") console.error(mapResult.reason);

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(console.error);
  }
}

boot();
