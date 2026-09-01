(() => {
  const baseSourceName = sourceName;
  const baseRender = render;
  const baseVisibleSignals = visibleSignals;
  const baseFitTurkey = fitTurkey;

  SOURCE_NAMES.afad_event_service = "AFAD";
  SOURCE_NAMES.akom_istanbul_news = "İstanbul AKOM";
  SOURCE_NAMES.istanbul_ibb_news = "İstanbul Büyükşehir Belediyesi";

  function finiteNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function normalizeCoordinates() {
    for (const signal of signals) {
      signal.latitude = finiteNumber(signal.latitude);
      signal.longitude = finiteNumber(signal.longitude);
    }
  }

  function provinceForSource(id) {
    return signals.find(signal => signal.source_id === id)?.province || null;
  }

  sourceName = function enhancedSourceName(id) {
    if (!id) return "Resmî kaynak";
    if (SOURCE_NAMES[id]) return SOURCE_NAMES[id];

    const province = provinceForSource(id);
    if (province) {
      if (/_bb_(news|events)$/.test(id) || /_ibb_(news|events)$/.test(id)) {
        return `${province} Büyükşehir Belediyesi`;
      }
      if (/_bel_(news|duyurular|events)$/.test(id)) {
        return `${province} Belediyesi`;
      }
    }

    return baseSourceName(id);
  };

  function freshnessRank(value) {
    return ({NOW:0, RECENT:1, OLD:2, UNKNOWN:3})[value] ?? 4;
  }

  function relevanceRank(value) {
    return ({HIGH:0, MEDIUM:1, LOW:2})[value] ?? 3;
  }

  visibleSignals = function enhancedVisibleSignals(options = {}) {
    const now = Date.now();
    return [...baseVisibleSignals(options)].sort((a, b) => {
      const freshnessDiff = freshnessRank(a.freshness) - freshnessRank(b.freshness);
      if (freshnessDiff) return freshnessDiff;

      const relevanceDiff = relevanceRank(a.relevance) - relevanceRank(b.relevance);
      if (relevanceDiff) return relevanceDiff;

      const aDate = parseDate(a.published_at);
      const bDate = parseDate(b.published_at);
      const aDistance = aDate ? Math.abs(aDate.getTime() - now) : Number.MAX_SAFE_INTEGER;
      const bDistance = bDate ? Math.abs(bDate.getTime() - now) : Number.MAX_SAFE_INTEGER;
      if (aDistance !== bDistance) return aDistance - bDistance;

      return (bDate?.getTime() || 0) - (aDate?.getTime() || 0);
    });
  };

  formatTime = function enhancedFormatTime(value) {
    const date = parseDate(value);
    if (!date) return "Zaman yok";

    const now = new Date();
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const diffDays = Math.round((day.getTime() - today.getTime()) / 864e5);
    const hasClockTime = date.getHours() !== 0 || date.getMinutes() !== 0;
    const clock = hasClockTime
      ? new Intl.DateTimeFormat("tr-TR", {hour:"2-digit", minute:"2-digit"}).format(date)
      : null;

    if (diffDays === 0) return clock || "Bugün";
    if (diffDays === 1) return clock ? `Yarın · ${clock}` : "Yarın";
    if (diffDays === -1) return clock ? `Dün · ${clock}` : "Dün";

    return new Intl.DateTimeFormat("tr-TR", {day:"numeric", month:"short"}).format(date);
  };

  fitTurkey = function enhancedFitTurkey() {
    if (innerWidth <= 820 && map) {
      map.fitBounds(turkeyBounds, {
        paddingTopLeft:[10, 24],
        paddingBottomRight:[10, 176],
        animate:true,
        duration:.35
      });
      return;
    }
    baseFitTurkey();
  };

  function provinceActivity(province) {
    if (!province) return 0;
    return visibleSignals({ignoreProvince:true}).filter(signal => signal.province === province).length;
  }

  function activityFill(count) {
    if (count >= 5) return "#ea6d59";
    if (count >= 3) return "#f49b62";
    if (count === 2) return "#ffd18a";
    if (count === 1) return "#fff0bf";
    return "#f6f4e9";
  }

  baseProvinceStyle = function enhancedProvinceStyle(feature) {
    const province = normalizeProvinceName(feature?.properties?.name);
    const selected = Boolean(selectedProvince && province === selectedProvince);
    const count = provinceActivity(province);
    return {
      color: selected ? "#ef2f35" : "#d8ddd6",
      weight: selected ? 2.2 : .8,
      fillColor: activityFill(count),
      fillOpacity: selected ? 1 : count ? .96 : 1
    };
  };

  refreshProvinceStyles = function enhancedRefreshProvinceStyles() {
    if (!provinceLayer) return;
    provinceLayer.setStyle(baseProvinceStyle);

    for (const [province, layer] of provinceLayers.entries()) {
      const count = provinceActivity(province);
      const text = count
        ? `${province} · ${count} gelişme`
        : `${province} · yeni gelişme yok`;
      if (layer.getTooltip()) layer.setTooltipContent(text);
      else layer.bindTooltip(text, {sticky:true, direction:"top", className:"activity-tooltip"});
    }
  };

  render = function enhancedRender() {
    normalizeCoordinates();
    baseRender();

    const current = visibleSignals();
    const activeProvinceCount = new Set(current.map(signal => signal.province).filter(Boolean)).size;
    statusText.textContent = selectedProvince
      ? `${current.length} gelişme · ${selectedProvince}`
      : `${current.length} gelişme · ${activeProvinceCount} il`;
  };
})();
