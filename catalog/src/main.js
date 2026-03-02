// Intelligence Catalog — Frontend Logic
// Dossier Premium / Fichas Individuais / Gallery Support

async function invoke(cmd, args) {
    const t = window.__TAURI__;
    const fn = t?.core?.invoke || t?.invoke;
    if (!fn) throw new Error("Tauri não disponível");
    return fn(cmd, args);
}

// ── Estado ────────────────────────────────────────────────────────────────────
const state = {
    page: 0,
    limit: 40,
    loading: false,
    hasMore: true,
    category: "",
    source: "",
    country: "",
    searchTerm: "",
    bioOnly: false,
    activeId: null,
    activeImages: []
};

// ── Elementos ─────────────────────────────────────────────────────────────────
const grid = document.getElementById("grid");
const emptyState = document.getElementById("emptyState");
const resultCount = document.getElementById("resultCount");
const searchInput = document.getElementById("searchInput");
const sourceFilter = document.getElementById("sourceFilter");
const countryFilter = document.getElementById("countryFilter");
const bioCheck = document.getElementById("bioOnly");
const modalOverlay = document.getElementById("modalOverlay");
const modalClose = document.getElementById("modalClose");
const modalBody = document.getElementById("modalBody");
const scrollSentinel = document.getElementById("scrollSentinel");

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
    window.addEventListener("hashchange", handleRouting);
    setupInfiniteScroll();
    await loadStats();
    await handleRouting();
})();

async function handleRouting() {
    const hash = window.location.hash;
    if (hash.startsWith("#/id/")) {
        const id = hash.replace("#/id/", "");
        if (id) openModal(id);
    } else {
        closeModal();
        if (grid.children.length === 0) await loadPage(true);
    }
}

async function loadStats() {
    try {
        const s = await invoke("get_stats");
        document.getElementById("statWanted").textContent = s.wanted.toLocaleString();
        document.getElementById("statMissing").textContent = s.missing.toLocaleString();
        if (document.getElementById("statBio")) {
            document.getElementById("statBio").textContent = (s.with_biometrics || 0).toLocaleString();
        }
    } catch (e) { console.error("stats_err", e); }
}

// ── Carregar Página ───────────────────────────────────────────────────────────
async function loadPage(reset = false) {
    if (state.loading) return;
    state.loading = true;

    if (reset) {
        state.page = 0;
        state.hasMore = true;
        grid.innerHTML = "";
    }

    try {
        const results = await invoke("search_individuals", {
            name: state.searchTerm || null,
            category: state.category || null,
            country: state.country || null,
            has_embedding: state.bioOnly ? true : null,
            source_filter: state.source || null,
            page: state.page,
            limit: state.limit,
        });

        if (reset && results.length === 0) {
            emptyState.style.display = "block";
            scrollSentinel.classList.add("hidden");
            resultCount.textContent = "0 resultados";
            return;
        }

        emptyState.style.display = "none";
        results.forEach((p, i) => grid.appendChild(createCard(p, i)));

        // Load images in background
        results.forEach(p => { if (p.img_path) loadCardImage(p.id, p.img_path); });

        state.hasMore = results.length === state.limit;
        state.page++;
        resultCount.textContent = `${grid.children.length}${state.hasMore ? "+" : ""} resultados`;
        scrollSentinel.classList.toggle("hidden", !state.hasMore);
    } catch (e) {
        console.error(e);
        showToast("Erro: " + e);
    } finally {
        state.loading = false;
    }
}

function setupInfiniteScroll() {
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && state.hasMore && !state.loading) {
            loadPage(false);
        }
    }, { rootMargin: "200px" });
    observer.observe(scrollSentinel);
}

// ── Card ──────────────────────────────────────────────────────────────────────
function createCard(p, index) {
    const card = document.createElement("div");
    card.className = "card";
    card.style.animationDelay = `${Math.min(index * 0.05, 0.5)}s`;

    const nats = parseNats(p.nationalities);
    const natTag = nats.length ? `<span class="nat-tag">${nats[0]}</span>` : "";
    const desc = stripHtml(p.description || "Sem descrição disponível").slice(0, 70);

    card.innerHTML = `
    <div class="card-img-wrap">
      <span class="card-no-img" id="noimg-${p.id}">👤</span>
      <img class="card-img" id="img-${p.id}" style="display:none">
      <span class="card-badge ${p.category}">${p.category.toUpperCase()}</span>
      ${p.has_embedding ? '<span class="bio-badge">🧬</span>' : ""}
    </div>
    <div class="card-body">
      <div class="card-source">${escHtml(p.source)}</div>
      <div class="card-name">${escHtml(p.name)}</div>
      <div class="card-desc">${escHtml(desc)}...</div>
      <div class="card-footer">${natTag}</div>
    </div>`;

    card.addEventListener("click", () => { window.location.hash = `#/id/${p.id}`; });
    return card;
}

async function loadCardImage(id, imgPath) {
    try {
        const b64 = await invoke("get_image_base64", { imgPath });
        const imgEl = document.getElementById(`img-${id}`);
        const noImg = document.getElementById(`noimg-${id}`);
        if (imgEl) {
            imgEl.src = b64;
            imgEl.style.display = "block";
            if (noImg) noImg.style.display = "none";
        }
    } catch { }
}

// ── Modal / Dossiê ────────────────────────────────────────────────────────────
async function openModal(id) {
    state.activeId = id;
    modalBody.innerHTML = `<div style="text-align:center;padding:100px;opacity:0.3;font-family:var(--font-mono)">[ ACESSANDO DOSSIÊ ${id} ]</div>`;
    modalOverlay.classList.add("open");
    document.body.style.overflow = "hidden";

    try {
        const p = await invoke("get_individual", { id });
        renderDossier(p);

        // Load Gallery Images
        state.activeImages = p.images || [];
        if (state.activeImages.length) {
            loadGalleryThumbnails();

            // Set primary image
            const primary = state.activeImages.find(img => img.is_primary) || state.activeImages[0];
            if (primary.img_path) switchDossierImage(primary.img_path);
        } else if (p.img_path) {
            switchDossierImage(p.img_path);
        }
    } catch (e) {
        modalBody.innerHTML = `<div style="padding:60px;color:var(--accent-red)">ERRO: ${e}</div>`;
    }
}

function renderDossier(p) {
    const isWanted = p.category === "wanted";
    const crimes = p.crimes.length ? p.crimes.map(c => `<li class="crime-tag">${escHtml(c)}</li>`).join("") : "<li>Sem acusações específicas.</li>";

    modalBody.innerHTML = `
    <div class="dossier">
      <aside class="dossier-sidebar">
        <div class="dossier-main-img-wrap">
          <div class="scanline"></div>
          <span class="card-no-img" id="dossier-no-img" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:120px;opacity:0.05">👤</span>
          <img class="main-img" id="dossier-main-img" style="display:none">
        </div>

        <div class="gallery-section" id="gallerySection">
          <h3 class="gallery-title">Galeria Forense / Membros</h3>
          <div class="gallery-grid" id="galleryGrid"></div>
        </div>
      </aside>

      <main class="dossier-content">
        <div class="dossier-status ${p.category}">${isWanted ? '🔴 INVESTIGAÇÃO ATIVA' : '🟡 ALERTA DE DESAPARECIMENTO'}</div>
        <h1 class="dossier-name">${escHtml(p.name)}</h1>
        <div class="dossier-meta">ID: ${p.id} | FONTE: ${p.source}</div>

        <div class="info-grid">
          <div class="info-item"><label>Gênero</label><span>${p.sex || 'N/A'}</span></div>
          <div class="info-item"><label>Nascimento</label><span>${p.birth_date || 'Desconhecido'}</span></div>
          <div class="info-item"><label>Países</label><span>${parseNats(p.nationalities).join(", ") || 'N/A'}</span></div>
          <div class="info-item"><label>Recompensa</label><span>${p.reward || 'N/A'}</span></div>
        </div>

        <h3 class="section-label">Acusações e Infrações</h3>
        <ul class="crimes-list">${crimes}</ul>

        <h3 class="section-label">Descrição Adicional</h3>
        <div class="desc-text">${escHtml(p.description) || 'Nenhum dado adicional.'}</div>
      </main>
    </div>`;
}

async function loadGalleryThumbnails() {
    const gridEl = document.getElementById("galleryGrid");
    if (!gridEl) return;

    state.activeImages.forEach(async (img, idx) => {
        const thumb = document.createElement("img");
        thumb.className = "gallery-thumb";
        if (img.is_primary) thumb.classList.add("active");

        try {
            const b64 = await invoke("get_image_base64", { imgPath: img.img_path });
            thumb.src = b64;
            thumb.addEventListener("click", () => {
                document.querySelectorAll(".gallery-thumb").forEach(t => t.classList.remove("active"));
                thumb.classList.add("active");
                switchDossierImage(img.img_path);
            });
            gridEl.appendChild(thumb);
        } catch { }
    });
}

async function switchDossierImage(path) {
    const mainImg = document.getElementById("dossier-main-img");
    const noImg = document.getElementById("dossier-no-img");
    try {
        const b64 = await invoke("get_image_base64", { imgPath: path });
        if (mainImg) {
            mainImg.src = b64;
            mainImg.style.display = "block";
            if (noImg) noImg.style.display = "none";
        }
    } catch { }
}

// ── Filtros ───────────────────────────────────────────────────────────────────
document.querySelectorAll(".cat-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".cat-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        state.category = btn.dataset.category;
        loadPage(true);
    });
});

sourceFilter.addEventListener("change", () => { state.source = sourceFilter.value; loadPage(true); });
countryFilter.addEventListener("change", () => { state.country = countryFilter.value; loadPage(true); });
bioCheck.addEventListener("change", () => { state.bioOnly = bioCheck.checked; loadPage(true); });

let searchDeb;
searchInput.addEventListener("input", () => {
    clearTimeout(searchDeb);
    searchDeb = setTimeout(() => {
        state.searchTerm = searchInput.value.trim();
        loadPage(true);
    }, 400);
});

// Keyboard Shortcut ⌘K / Ctrl+K
window.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchInput.focus();
    }
});

modalClose.addEventListener("click", () => window.location.hash = "");
modalOverlay.addEventListener("click", e => { if (e.target === modalOverlay) window.location.hash = ""; });
document.getElementById("exportBtn")?.addEventListener("click", () => showToast("Exportando CSV..."));

// ── Helpers ───────────────────────────────────────────────────────────────────
function parseNats(json) {
    if (!json) return [];
    try { return JSON.parse(json); } catch { return json.split(",").map(s => s.trim()); }
}
function stripHtml(s) { return (s || "").replace(/<[^>]*>?/gm, ''); }
function escHtml(s) { return stripHtml(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function showToast(m) {
    const t = document.getElementById("toast");
    t.textContent = m; t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 3000);
}
