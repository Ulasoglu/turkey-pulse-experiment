(() => {
  let provinceFeedSignals = [];
  const renderBeforeFeedLayer = render;

  function finiteNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function prepareFeedRow(row) {
    return {
      ...row,
      latitude: finiteNumber(row.latitude),
      longitude: finiteNumber(row.longitude),
    };
  }

  function feedPool() {
    return provinceFeedSignals.length ? provinceFeedSignals : signals;
  }

  function feedVisibleSignals({ ignoreProvince = false } = {}) {
    const q = searchInput.value.trim().toLocaleLowerCase("tr-TR");

    return feedPool()
      .filter((signal) =>
        passesTime(signal) &&
        (selectedCategory === "ALL" || signal.category === selectedCategory) &&
        (ignoreProvince || !selectedProvince || signal.province === selectedProvince) &&
        (!q || `${signal.province || ""} ${signal.title || ""}`.toLocaleLowerCase("tr-TR").includes(q))
      )
      .sort((a, b) => {
        const aDate = parseDate(a.published_at)?.getTime() || 0;
        const bDate = parseDate(b.published_at)?.getTime() || 0;
        return bDate - aDate;
      });
  }

  function provinceFeedCount(province) {
    if (!province) return 0;
    return feedVisibleSignals({ ignoreProvince: true }).filter((signal) => signal.province === province).length;
  }

  function activityFill(count) {
    if (count >= 10) return "#ea6d59";
    if (count >= 5) return "#f49b62";
    if (count >= 2) return "#ffd18a";
    if (count === 1) return "#fff0bf";
    return "#f6f4e9";
  }

  baseProvinceStyle = function feedAwareProvinceStyle(feature) {
    const province = normalizeProvinceName(feature?.properties?.name);
    const selected = Boolean(selectedProvince && province === selectedProvince);
    const count = provinceFeedCount(province);
    return {
      color: selected ? "#ef2f35" : "#d8ddd6",
      weight: selected ? 2.2 : .8,
      fillColor: activityFill(count),
      fillOpacity: selected ? 1 : count ? .96 : 1,
    };
  };

  refreshProvinceStyles = function refreshFeedAwareProvinceStyles() {
    if (!provinceLayer) return;
    provinceLayer.setStyle(baseProvinceStyle);

    for (const [province, layer] of provinceLayers.entries()) {
      const count = provinceFeedCount(province);
      const tooltip = count
        ? `${province} · ${count} gelişme`
        : `${province} · yeni gelişme yok`;
      if (layer.getTooltip()) layer.setTooltipContent(tooltip);
      else layer.bindTooltip(tooltip, { sticky: true, direction: "top", className: "activity-tooltip" });
    }
  };

  function syncMapSummary() {
    const current = feedVisibleSignals();
    const activeProvinceCount = new Set(current.map((signal) => signal.province).filter(Boolean)).size;
    statusText.textContent = selectedProvince
      ? `${current.length} gelişme · ${selectedProvince}`
      : `${current.length} gelişme · ${activeProvinceCount} il`;
  }

  renderFeeds = function renderBroaderProvinceFeeds() {
    const filtered = feedVisibleSignals();
    const title = selectedProvince
      ? `${selectedProvince} · ${timeLabel()} · ${categoryLabel()}`
      : `${timeLabel()} · ${categoryLabel()}`;
    const subtitle = `${filtered.length} gelişme bulundu`;

    feedTitle.textContent = mobileFeedTitle.textContent = title;
    feedSubtitle.textContent = mobileFeedSubtitle.textContent = subtitle;
    desktopFeedList.innerHTML = mobileFeedList.innerHTML = "";

    if (!filtered.length) {
      const empty = `<div class="empty-state"><strong>Şu anda yeni bir gelişme yok.</strong><span>Başka bir filtre veya şehir deneyebilirsin.</span></div>`;
      desktopFeedList.innerHTML = mobileFeedList.innerHTML = empty;
    } else {
      for (const signal of filtered.slice(0, 40)) {
        desktopFeedList.appendChild(createFeedCard(signal));
        mobileFeedList.appendChild(createFeedCard(signal));
      }
    }

    updateFavoriteButtons();
  };

  // pulse-experience keeps map markers deliberately strict. This outer render
  // layer only replaces province shading/tooltips/status with the broader feed
  // counts, so a province can correctly say "8 gelişme" even when it has zero
  // high-priority map markers.
  render = function renderWithFeedAwareProvinceMeta() {
    renderBeforeFeedLayer();
    refreshProvinceStyles();
    syncMapSummary();
  };

  async function loadProvinceFeed() {
    try {
      const response = await fetch("data/feed.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`Feed HTTP ${response.status}`);
      const rows = await response.json();
      if (!Array.isArray(rows)) throw new Error("Feed payload is not an array");

      provinceFeedSignals = rows.map(prepareFeedRow);
      window.turkeyPulseProvinceFeed = provinceFeedSignals;

      for (const row of provinceFeedSignals) {
        if (row.source_id && row.source_name && !SOURCE_NAMES[row.source_id]) {
          SOURCE_NAMES[row.source_id] = row.source_name;
        }
      }

      render();
    } catch (error) {
      console.warn("Broader province feed unavailable; using map signals", error);
    }
  }

  loadProvinceFeed();
})();
