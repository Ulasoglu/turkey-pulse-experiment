(() => {
  const ECMWF_SOURCE = "ecmwf_open_data_weather";
  const originalSourceName = window.sourceName;
  const originalOpenDetail = window.openDetail;

  const style = document.createElement("style");
  style.textContent = `
    .model-badge{display:inline-flex;align-items:center;gap:6px;margin:8px 0 2px;padding:6px 9px;border-radius:999px;background:#edf6ff;color:#255d87;font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}
    .model-note{margin:12px 0;padding:12px 14px;border-radius:12px;background:#f5f9fc;border:1px solid #d9e8f2;color:#34505f;font-size:13px;line-height:1.45}
    .feed-card[data-model-weather="true"] .feed-source::after{content:" · Model tahmini";font-weight:700;color:#3c769c}
  `;
  document.head.appendChild(style);

  window.sourceName = function(id){
    if(id === ECMWF_SOURCE) return "ECMWF Open Data (IFS)";
    return originalSourceName ? originalSourceName(id) : (id || "Kaynak");
  };

  const originalCreateFeedCard = window.createFeedCard;
  if(originalCreateFeedCard){
    window.createFeedCard = function(s){
      const frag = originalCreateFeedCard(s);
      if(s?.source_id === ECMWF_SOURCE){
        const card = frag.querySelector?.(".feed-card");
        if(card) card.dataset.modelWeather = "true";
      }
      return frag;
    };
  }

  window.openDetail = function(s){
    if(!s || s.source_id !== ECMWF_SOURCE){
      return originalOpenDetail ? originalOpenDetail(s) : undefined;
    }

    document.querySelector(".detail-overlay")?.remove();
    const meta = window.categoryMeta ? window.categoryMeta(s.category) : {css:"weather",icon:"⌁",label:"Hava Durumu"};
    const priority = window.signalPriority ? window.signalPriority(s) : "normal";
    const escape = window.escapeHtml || (v => String(v ?? ""));
    const date = window.formatDate ? window.formatDate(s.published_at) : (s.published_at || "");
    const valid = window.validUrl ? window.validUrl(s.source_url) : false;
    const overlay = document.createElement("div");
    overlay.className = "detail-overlay";
    overlay.innerHTML = `<article class="detail-card">
      <button class="detail-close" aria-label="Kapat">×</button>
      <div class="detail-kicker"><span class="feed-row-icon ${meta.css}">${meta.icon}</span><b>${meta.label.toUpperCase()}</b><span class="priority-pill ${priority}">${priority==="high"?"Yüksek":priority==="low"?"Düşük":"Normal"}</span></div>
      <div class="model-badge">⌁ ECMWF model tahmini</div>
      <h2>${escape(s.title || "Hava sinyali")}</h2>
      <p class="detail-summary">Bu gelişme resmî bir meteoroloji uyarısı değildir. ECMWF IFS hava tahmin modelinden türetilmiş yaklaşık +24 saatlik bir sinyaldir.</p>
      <div class="model-note"><strong>Model verisi</strong><br>Yerel koşullar değişebilir. Kritik kararlar için resmî meteoroloji duyurularını ayrıca kontrol et.</div>
      <div class="detail-grid"><div><small>Yer</small><b>${escape(s.province || "Türkiye")}</b></div><div><small>Tahmin zamanı</small><b>${date}</b></div></div>
      <div class="detail-source"><small>VERİ KAYNAĞI</small><strong>ECMWF Open Data (IFS)</strong><span>ECMWF Open Data · CC BY 4.0. Model tahmini; MGM uyarısı değildir.</span></div>
      <div class="detail-actions"><button data-map>⌖ Haritada Göster</button>${valid?`<a href="${s.source_url}" target="_blank" rel="noopener noreferrer">ECMWF Kaynağını Aç ↗</a>`:""}</div>
    </article>`;
    document.body.appendChild(overlay);
    overlay.querySelector(".detail-close").onclick = () => overlay.remove();
    overlay.onclick = e => { if(e.target === overlay) overlay.remove(); };
    overlay.querySelector("[data-map]").onclick = () => {
      const p = window.signalPosition ? window.signalPosition(s) : null;
      overlay.remove();
      if(p && window.map){
        const sheet = document.getElementById("mobileSheet");
        sheet?.classList.remove("open");
        window.map.flyTo(p, Number.isFinite(s.latitude) ? 9 : 7, {duration:.4});
      }
    };
  };
})();
