const CATEGORY_LABELS = {
  EVENT: "Etkinlik",
  EARTHQUAKE: "Deprem",
  WEATHER: "Hava",
  TRAFFIC: "Trafik",
  INFRASTRUCTURE: "Altyapı",
  OTHER: "Yerel",
};

const PROVINCE_CENTERS = {
  İstanbul: [41.0082, 28.9784],
  Ankara: [39.9334, 32.8597],
  İzmir: [38.4237, 27.1428],
  Bursa: [40.1885, 29.061],
  Konya: [37.8746, 32.4932],
  Samsun: [41.2867, 36.33],
  Antalya: [36.8969, 30.7133],
  Çorum: [40.5506, 34.9556],
  Bayburt: [40.2552, 40.2249],
  Balıkesir: [39.6484, 27.8826],
  Malatya: [38.3552, 38.3095],
  Manisa: [38.6191, 27.4289],
  Denizli: [37.7765, 29.0864],
  Elazığ: [38.681, 39.2264],
  Adana: [36.9914, 35.3308],
  Gaziantep: [37.0662, 37.3833],
  Diyarbakır: [37.9144, 40.2306],
  Trabzon: [41.0015, 39.7178],
  Erzurum: [39.9043, 41.2679],
  Van: [38.4891, 43.4089],
};

let signals = [];
let selectedProvince = null;
let selectedTime = "today";
let selectedCategory = "ALL";
let map;
let markersLayer;
let favorites = new Set(JSON.parse(localStorage.getItem("tp:favorites") || "[]"));

const feedPanel = document.getElementById("feedPanel");
const feedTitle = document.getElementById("feedTitle");
const feedSubtitle = document.getElementById("feedSubtitle");
const feedList = document.getElementById("feedList");
const favoriteButton = document.getElementById("favoriteButton");
const statusText = document.getElementById("statusText");
const searchInput = document.getElementById("searchInput");
const categoryFilters = document.getElementById("categoryFilters");
const template = document.getElementById("feedCardTemplate");

function initMap() {
  map = L.map("map", { zoomControl: true, minZoom: 5, maxZoom: 12 }).setView([39.0, 35.0], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);
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
    return date.getFullYear() === now.getFullYear()
      && date.getMonth() === now.getMonth()
      && date.getDate() === now.getDate();
  }

  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const sevenDaysAhead = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  return date >= sevenDaysAgo && date <= sevenDaysAhead;
}

function visibleSignals() {
  const query = searchInput.value.trim().toLocaleLowerCase("tr-TR");
  return signals.filter((signal) => {
    if (!passesTime(signal)) return false;
    if (selectedCategory !== "ALL" && signal.category !== selectedCategory) return false;
    if (selectedProvince && signal.province !== selectedProvince) return false;
    if (!query) return true;
    return `${signal.province || ""} ${signal.title || ""}`.toLocaleLowerCase("tr-TR").includes(query);
  });
}

function provincePosition(signal) {
  if (Number.isFinite(signal.latitude) && Number.isFinite(signal.longitude)) {
    return [signal.latitude, signal.longitude];
  }
  return PROVINCE_CENTERS[signal.province] || null;
}

function markerClass(category) {
  return (category || "OTHER").toLowerCase();
}

function renderMarkers() {
  markersLayer.clearLayers();
  const filtered = visibleSignals();
  const groups = new Map();

  for (const signal of filtered) {
    const pos = provincePosition(signal);
    if (!pos) continue;
    const precise = Number.isFinite(signal.latitude) && Number.isFinite(signal.longitude);
    const key = precise ? `signal:${signal.id}` : `province:${signal.province}:${signal.category}`;
    if (!groups.has(key)) groups.set(key, { signals: [], pos });
    groups.get(key).signals.push(signal);
  }

  for (const group of groups.values()) {
    const first = group.signals[0];
    const count = group.signals.reduce((sum, item) => sum + (item.signal_count || 1), 0);
    const icon = L.divIcon({
      className: "pulse-marker",
      html: `<div class="pulse-dot ${markerClass(first.category)}">${count}</div>`,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });
    const marker = L.marker(group.pos, { icon }).addTo(markersLayer);
    marker.on("click", () => {
      selectedProvince = first.province || null;
      render();
      openFeed();
    });
  }

  statusText.textContent = `${filtered.length} güncel gelişme`;
}

function formatDate(value) {
  const date = parseDate(value);
  if (!date) return "Zaman bilgisi yok";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"
  }).format(date);
}

function renderFeed() {
  const filtered = visibleSignals();
  feedTitle.textContent = selectedProvince || "Türkiye";
  feedSubtitle.textContent = `${filtered.length} gelişme`;
  favoriteButton.style.visibility = selectedProvince ? "visible" : "hidden";
  favoriteButton.classList.toggle("active", selectedProvince && favorites.has(selectedProvince));
  favoriteButton.textContent = selectedProvince && favorites.has(selectedProvince) ? "★" : "☆";
  feedList.innerHTML = "";

  if (!filtered.length) {
    feedList.innerHTML = `<div class="empty-state"><strong>Şu anda yeni bir gelişme yok.</strong><br><br>Başka bir zaman filtresi veya şehir deneyebilirsin.</div>`;
    return;
  }

  for (const signal of filtered.slice(0, 80)) {
    const card = template.content.cloneNode(true);
    card.querySelector(".category-badge").textContent = CATEGORY_LABELS[signal.category] || "Yerel";
    card.querySelector("time").textContent = formatDate(signal.published_at);
    card.querySelector("h2").textContent = signal.title;
    card.querySelector(".feed-source").textContent = `Kaynak: ${signal.source_id || "Resmî kaynak"}`;
    const link = card.querySelector(".source-link");
    if (signal.source_url && /^https?:\/\//.test(signal.source_url)) {
      link.href = signal.source_url;
    } else {
      link.remove();
    }
    card.querySelector(".show-on-map").addEventListener("click", () => {
      const pos = provincePosition(signal);
      if (pos) map.flyTo(pos, Number.isFinite(signal.latitude) ? 10 : 8, { duration: 0.5 });
      if (window.innerWidth <= 820) feedPanel.classList.remove("open");
    });
    feedList.appendChild(card);
  }
}

function renderCategoryFilters() {
  const categories = ["ALL", ...Object.keys(CATEGORY_LABELS).filter((cat) => signals.some((s) => s.category === cat))];
  categoryFilters.innerHTML = "";
  for (const category of categories) {
    const button = document.createElement("button");
    button.textContent = category === "ALL" ? "Tümü" : CATEGORY_LABELS[category];
    button.classList.toggle("active", selectedCategory === category);
    button.addEventListener("click", () => {
      selectedCategory = category;
      render();
    });
    categoryFilters.appendChild(button);
  }
}

function openFeed() {
  if (window.innerWidth <= 820) feedPanel.classList.add("open");
}

function render() {
  renderCategoryFilters();
  renderMarkers();
  renderFeed();
}

function saveFavorites() {
  localStorage.setItem("tp:favorites", JSON.stringify([...favorites]));
}

favoriteButton.addEventListener("click", (event) => {
  event.stopPropagation();
  if (!selectedProvince) return;
  favorites.has(selectedProvince) ? favorites.delete(selectedProvince) : favorites.add(selectedProvince);
  saveFavorites();
  renderFeed();
});

document.getElementById("savedButton").addEventListener("click", () => {
  if (!favorites.size) {
    alert("Henüz kayıtlı bir şehrin yok. Bir şehir seçip yıldız simgesine dokunabilirsin.");
    return;
  }
  selectedProvince = [...favorites][0];
  const pos = PROVINCE_CENTERS[selectedProvince];
  if (pos) map.flyTo(pos, 7, { duration: 0.5 });
  render();
  openFeed();
});

feedPanel.querySelector(".feed-head").addEventListener("click", () => {
  if (window.innerWidth <= 820) feedPanel.classList.toggle("open");
});

for (const button of document.querySelectorAll("[data-time]")) {
  button.addEventListener("click", () => {
    selectedTime = button.dataset.time;
    document.querySelectorAll("[data-time]").forEach((item) => item.classList.toggle("active", item === button));
    render();
  });
}

searchInput.addEventListener("input", () => {
  const query = searchInput.value.trim().toLocaleLowerCase("tr-TR");
  if (query) {
    const province = [...new Set(signals.map((s) => s.province).filter(Boolean))]
      .find((name) => name.toLocaleLowerCase("tr-TR").startsWith(query));
    if (province) selectedProvince = province;
  } else {
    selectedProvince = null;
  }
  render();
});

async function boot() {
  initMap();
  try {
    const response = await fetch("data/signals.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    signals = await response.json();
    statusText.textContent = `${signals.length} görünür sinyal yüklendi`;
  } catch (error) {
    console.error(error);
    statusText.textContent = "Veriler şu anda yüklenemedi";
  }
  render();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(console.error);
  }
}

boot();
