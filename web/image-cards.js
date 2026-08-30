(() => {
  let byTitle = new Map();

  function key(value) {
    return String(value || "").trim().toLocaleLowerCase("tr-TR");
  }

  async function loadImageIndex() {
    try {
      const response = await fetch("data/signals.json", { cache: "no-store" });
      if (!response.ok) return;
      const rows = await response.json();
      byTitle = new Map(rows.filter((row) => row.image_url).map((row) => [key(row.title), row]));
      enhance(document);
    } catch (error) {
      console.warn("Image enhancement unavailable", error);
    }
  }

  function addFeedImage(card, row) {
    if (card.classList.contains("has-image")) return;
    const body = card.querySelector(".feed-card-body");
    if (!body) return;
    const image = document.createElement("img");
    image.className = "feed-thumb";
    image.src = row.image_url;
    image.alt = row.title || "Etkinlik görseli";
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";
    image.addEventListener("error", () => {
      image.classList.add("image-broken");
      card.classList.remove("has-image");
    });
    card.insertBefore(image, body);
    card.classList.add("has-image");
  }

  function addDetailImage(container, row) {
    if (!container || container.querySelector(".detail-hero-image")) return;
    const title = [...container.querySelectorAll("h1,h2,h3")].find((node) => key(node.textContent) === key(row.title));
    if (!title) return;
    const image = document.createElement("img");
    image.className = "detail-hero-image";
    image.src = row.image_url;
    image.alt = row.title || "Gelişme görseli";
    image.loading = "eager";
    image.decoding = "async";
    image.referrerPolicy = "no-referrer";
    image.addEventListener("error", () => image.remove());
    title.insertAdjacentElement("afterend", image);
  }

  function enhance(root) {
    root.querySelectorAll?.(".feed-card").forEach((card) => {
      const titleNode = card.querySelector("h3,h2");
      const row = byTitle.get(key(titleNode?.textContent));
      if (row) addFeedImage(card, row);
    });

    const detailContainers = [];
    if (root.matches?.(".detail-overlay,.detail-card,.detail-panel,.signal-detail,.detail-view,.mobile-detail,.modal,.overlay")) detailContainers.push(root);
    root.querySelectorAll?.(".detail-overlay,.detail-card,.detail-panel,.signal-detail,.detail-view,.mobile-detail,.modal,.overlay").forEach((container) => detailContainers.push(container));
    for (const container of detailContainers) {
      const titleNode = container.querySelector("h1,h2,h3");
      const row = byTitle.get(key(titleNode?.textContent));
      if (row) addDetailImage(container, row);
    }
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === 1) enhance(node);
      }
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    observer.observe(document.body, { childList: true, subtree: true });
    loadImageIndex();
  });
})();
