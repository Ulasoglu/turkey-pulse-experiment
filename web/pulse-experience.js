(() => {
  const baseSourceName = sourceName;
  const baseRender = render;

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
