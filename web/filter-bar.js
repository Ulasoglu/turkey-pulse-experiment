(() => {
  const baseRender = render;
  const stage = document.querySelector(".map-stage");
  if (!stage) return;

  const timeLabels = {now:"Şimdi", today:"Bugün", "7d":"7 Gün"};
  const categoryOrder = ["ALL", "EARTHQUAKE", "WEATHER", "TRAFFIC", "INFRASTRUCTURE", "EVENT", "OTHER"];

  const bar = document.createElement("div");
  bar.className = "map-filter-bar";
  bar.innerHTML = `
    <button class="map-filter-pill province-pill" type="button" hidden><span>⌖</span><b></b><i>×</i></button>
    <button class="map-filter-pill" type="button" data-open-filter><span>◷</span><b data-time-label>Bugün</b><i>⌄</i></button>
    <button class="map-filter-pill" type="button" data-open-filter><span>•••</span><b data-category-label>Tümü</b><i>⌄</i></button>
  `;
  stage.appendChild(bar);

  const overlay = document.createElement("div");
  overlay.className = "map-filter-overlay";
  overlay.innerHTML = `
    <section class="map-filter-panel" role="dialog" aria-modal="true" aria-label="Harita filtreleri">
      <button class="map-filter-handle" type="button" aria-label="Kapat"><span></span></button>
      <div class="map-filter-panel-head"><strong>Filtreler</strong><button type="button" data-filter-close>×</button></div>
      <div class="map-filter-group">
        <small>ZAMAN ARALIĞI</small>
        <div class="map-filter-time"></div>
      </div>
      <div class="map-filter-group">
        <small>KATEGORİ</small>
        <div class="map-filter-categories"></div>
      </div>
      <button class="map-filter-apply" type="button">Uygula</button>
      <button class="map-filter-reset" type="button">Filtreleri Sıfırla</button>
    </section>
  `;
  document.body.appendChild(overlay);

  const provincePill = bar.querySelector(".province-pill");
  const provinceLabel = provincePill.querySelector("b");
  const timeLabelEl = bar.querySelector("[data-time-label]");
  const categoryLabelEl = bar.querySelector("[data-category-label]");
  const timeWrap = overlay.querySelector(".map-filter-time");
  const categoryWrap = overlay.querySelector(".map-filter-categories");

  let draftTime = selectedTime;
  let draftCategory = selectedCategory;

  function availableCategories() {
    return categoryOrder.filter(key => key === "ALL" || signals.some(signal => signal.category === key));
  }

  function categoryLabel(key) {
    const meta = CATEGORY_META[key] || CATEGORY_META.OTHER;
    return meta.short || meta.label;
  }

  function drawPanel() {
    timeWrap.innerHTML = ["now", "today", "7d"].map(key => `
      <button type="button" data-filter-time="${key}" class="${draftTime === key ? "active" : ""}">${timeLabels[key]}</button>
    `).join("");

    categoryWrap.innerHTML = availableCategories().map(key => {
      const meta = CATEGORY_META[key] || CATEGORY_META.OTHER;
      return `
        <button type="button" data-filter-category="${key}" class="${draftCategory === key ? "active" : ""}">
          <span class="filter-category-icon ${meta.css}">${meta.icon}</span>
          <b>${categoryLabel(key)}</b>
        </button>
      `;
    }).join("");

    timeWrap.querySelectorAll("[data-filter-time]").forEach(button => {
      button.onclick = () => {
        draftTime = button.dataset.filterTime;
        drawPanel();
      };
    });

    categoryWrap.querySelectorAll("[data-filter-category]").forEach(button => {
      button.onclick = () => {
        draftCategory = button.dataset.filterCategory;
        drawPanel();
      };
    });
  }

  function openPanel() {
    draftTime = selectedTime;
    draftCategory = selectedCategory;
    drawPanel();
    overlay.classList.add("show");
  }

  function closePanel() {
    overlay.classList.remove("show");
  }

  function updateBar() {
    timeLabelEl.textContent = timeLabels[selectedTime] || "Bugün";
    categoryLabelEl.textContent = categoryLabel(selectedCategory);
    provincePill.hidden = !selectedProvince;
    provinceLabel.textContent = selectedProvince || "";
    bar.classList.toggle("with-province", Boolean(selectedProvince));
  }

  bar.querySelectorAll("[data-open-filter]").forEach(button => button.onclick = openPanel);
  provincePill.onclick = () => {
    selectedProvince = null;
    render();
    fitTurkey();
  };

  overlay.querySelector("[data-filter-close]").onclick = closePanel;
  overlay.querySelector(".map-filter-handle").onclick = closePanel;
  overlay.onclick = event => { if (event.target === overlay) closePanel(); };
  overlay.querySelector(".map-filter-apply").onclick = () => {
    selectedTime = draftTime;
    selectedCategory = draftCategory;
    closePanel();
    render();
  };
  overlay.querySelector(".map-filter-reset").onclick = () => {
    selectedTime = "today";
    selectedCategory = "ALL";
    draftTime = selectedTime;
    draftCategory = selectedCategory;
    closePanel();
    render();
  };

  render = function renderWithFilterBar() {
    baseRender();
    updateBar();
  };

  updateBar();
})();
