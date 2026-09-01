(() => {
  let provinceFeedSignals = [];

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

  function feedVisibleSignals() {
    const pool = provinceFeedSignals.length ? provinceFeedSignals : signals;
    const q = searchInput.value.trim().toLocaleLowerCase("tr-TR");

    return pool
      .filter((signal) =>
        passesTime(signal) &&
        (selectedCategory === "ALL" || signal.category === selectedCategory) &&
        (!selectedProvince || signal.province === selectedProvince) &&
        (!q || `${signal.province || ""} ${signal.title || ""}`.toLocaleLowerCase("tr-TR").includes(q))
      )
      .sort((a, b) => {
        const aDate = parseDate(a.published_at)?.getTime() || 0;
        const bDate = parseDate(b.published_at)?.getTime() || 0;
        return bDate - aDate;
      });
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

  async function loadProvinceFeed() {
    try {
      const response = await fetch("data/feed.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`Feed HTTP ${response.status}`);
      const rows = await response.json();
      if (!Array.isArray(rows)) throw new Error("Feed payload is not an array");

      provinceFeedSignals = rows.map(prepareFeedRow);

      for (const row of provinceFeedSignals) {
        if (row.source_id && row.source_name && !SOURCE_NAMES[row.source_id]) {
          SOURCE_NAMES[row.source_id] = row.source_name;
        }
      }

      renderFeeds();
    } catch (error) {
      // During the first deploy the collector may not have generated feed.json
      // yet. The existing strict map dataset remains a safe fallback.
      console.warn("Broader province feed unavailable; using map signals", error);
    }
  }

  loadProvinceFeed();
})();
