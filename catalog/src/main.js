// Intelligence Catalog — Frontend Logic
// Comunicação com backend Rust via window.__TAURI__.invoke

const invoke = window.__TAURI__?.invoke ?? (() => Promise.reject("Tauri não disponível — rode com cargo tauri dev"));

// ── Estado ────────────────────────────────────────────────────────────────────
const state = {
    page: 0,
    limit: 40,
    loading: false,
    hasMore: true,
    category: "",
    source: "",
    country: "",
    crime: "",
    bioOnly: false,
    searchTerm: "",
};

// ── Elementos ─────────────────────────────────────────────────────────────────
const grid = document.getElementById("grid");
const loadMoreBtn = document.getElementById("loadMoreBtn");
const emptyState = document.getElementById("emptyState");
const resultCount = document.getElementById("resultCount");
const searchInput = document.getElementById("searchInput");
const sourceFilter = document.getElementById("sourceFilter");
const countryFilter = document.getElementById("countryFilter");
const bioCheck = document.getElementById("bioOnly");
const modalOverlay = document.getElementById("modalOverlay");
const modalClose = document.getElementById("modalClose");
const modalBody = document.getElementById("modalBody");
const toast = document.getElementById("toast");

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
    await loadStats();
    await loadPage(true);
})();

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
    try {
        const s = await invoke("get_stats");
        document.getElementById("statWanted").textContent = s.wanted.toLocaleString();
        document.getElementById("statMissing").textContent = s.missing.toLocaleString();
        document.getElementById("statBio").textContent = s.with_biometrics.toLocaleString();
    } catch (e) { console.error("stats:", e); }
}

// ── Carregar página ───────────────────────────────────────────────────────────
async function loadPage(reset = false) {
    if (state.loading) return;
    state.loading = true;
    loadMoreBtn.textContent = "Carregando...";
    loadMoreBtn.disabled = true;

    if (reset) {
        state.page = 0;
        state.hasMore = true;
        grid.innerHTML = "";
        showSkeletons(8);
    }

    try {
        const results = await invoke("search_individuals", {
            name: state.searchTerm || null,
            category: state.category || null,
            country: state.country || null,
            crime: state.crime || null,
            hasEmbedding: state.bioOnly ? true : null,
            sourceFilter: state.source || null,
            page: state.page,
            limit: state.limit,
        });

        removeSkeletons();

        if (reset && results.length === 0) {
            emptyState.style.display = "flex";
            loadMoreBtn.classList.add("hidden");
            resultCount.textContent = "0 resultados";
            return;
        }

        emptyState.style.display = "none";
        results.forEach((p, i) => {
            const card = createCard(p, i);
            grid.appendChild(card);
        });

        // Carregar imagens em background
        results.forEach(p => {
            if (p.img_path) loadCardImage(p.id, p.img_path, p.category);
        });

        state.hasMore = results.length === state.limit;
        state.page++;

        const totalText = reset
            ? `${results.length < state.limit ? results.length : state.limit + "+"} resultados`
            : `${grid.children.length} registros`;
        resultCount.textContent = totalText;

        if (state.hasMore) {
            loadMoreBtn.classList.remove("hidden");
            loadMoreBtn.textContent = "Carregar mais";
            loadMoreBtn.disabled = false;
        } else {
            loadMoreBtn.classList.add("hidden");
        }
    } catch (e) {
        console.error(e);
        removeSkeletons();
        showToast("Erro ao carregar dados: " + e);
    } finally {
        state.loading = false;
    }
}

// ── Card ──────────────────────────────────────────────────────────────────────
function createCard(p, index) {
    const card = document.createElement("div");
    card.className = `card ${p.category}`;
    card.dataset.id = p.id;
    card.style.animationDelay = `${Math.min(index * 0.04, 0.4)}s`;

    const nats = parseNats(p.nationalities);
    const natTags = nats.slice(0, 3).map(n => `<span class="nat-tag">${n}</span>`).join("");
    const desc = (p.description || "Sem informações de crime").slice(0, 100);

    card.innerHTML = `
    <div class="card-img-wrap">
      <span class="card-no-img" id="noimg-${p.id}">👤</span>
      <img class="card-img" id="img-${p.id}" alt="${escHtml(p.name)}" style="display:none">
      <span class="card-badge ${p.category}">${p.category === "wanted" ? "🔴 PROCURADO" : "🟡 DESAPAR."}</span>
      ${p.has_embedding ? '<span class="bio-badge" title="Biometria disponível">🧬</span>' : ""}
    </div>
    <div class="card-body">
      <div class="card-name" title="${escHtml(p.name)}">${escHtml(p.name)}</div>
      <div class="card-source">${escHtml(p.source)}</div>
      <div class="card-crime">${escHtml(desc)}</div>
      <div class="card-nat">${natTags}</div>
    </div>`;

    card.addEventListener("click", () => openModal(p.id));
    return card;
}

async function loadCardImage(id, imgPath, category) {
    const imgEl = document.getElementById(`img-${id}`);
    const noImg = document.getElementById(`noimg-${id}`);
    if (!imgEl || !imgPath) return;
    try {
        const b64 = await invoke("get_image_base64", { imgPath });
        imgEl.src = b64;
        imgEl.style.display = "block";
        if (noImg) noImg.style.display = "none";
    } catch { /* sem imagem — keepplaceholder */ }
}

// ── Modal ─────────────────────────────────────────────────────────────────────
async function openModal(id) {
    modalBody.innerHTML = `<div style="text-align:center;padding:60px;color:var(--text-muted)">Carregando...</div>`;
    modalOverlay.classList.add("open");
    document.body.style.overflow = "hidden";

    try {
        const p = await invoke("get_individual", { id });
        renderModal(p);
        if (p.base.img_path) {
            const b64 = await invoke("get_image_base64", { imgPath: p.base.img_path });
            const imgEl = document.getElementById("modal-img");
            if (imgEl) {
                imgEl.src = b64;
                imgEl.style.display = "block";
                const noImg = document.getElementById("modal-no-img");
                if (noImg) noImg.style.display = "none";
            }
        }
    } catch (e) {
        modalBody.innerHTML = `<p style="color:var(--text-dim);padding:40px">Erro: ${e}</p>`;
    }
}

function renderModal(p) {
    const b = p.base;
    const nats = parseNats(b.nationalities).join(", ").toUpperCase() || "N/A";
    const isWanted = b.category === "wanted";
    const crimeStyle = isWanted ? "" : "missing-style";

    const crimes = p.crimes.length
        ? p.crimes.map(c => `<li class="${crimeStyle}">${escHtml(c)}</li>`).join("")
        : `<li class="${crimeStyle}">Não informado</li>`;

    const aliases = p.aliases ? (() => { try { return JSON.parse(p.aliases).join(", "); } catch { return p.aliases; } })() : "";

    modalBody.innerHTML = `
    <div class="modal-header">
      <div class="modal-img-wrap">
        <span class="modal-no-img" id="modal-no-img">👤</span>
        <img class="modal-img" id="modal-img" alt="${escHtml(b.name)}" style="display:none">
      </div>
      <div class="modal-info">
        <div class="modal-name">${escHtml(b.name)}</div>
        <div class="modal-badges">
          <span class="badge ${b.category}">${isWanted ? "🔴 PROCURADO" : "🟡 DESAPARECIDO"}</span>
          ${b.has_embedding ? '<span class="badge bio">🧬 Biometria</span>' : ""}
          <span class="badge source">${escHtml(b.source)}</span>
        </div>
        <div class="modal-grid">
          <div class="field"><label>Nome Completo</label><span>${escHtml(b.name)}</span></div>
          ${aliases ? `<div class="field"><label>Aliases</label><span>${escHtml(aliases)}</span></div>` : ""}
          ${b.birth_date ? `<div class="field"><label>Nascimento</label><span>${b.birth_date}</span></div>` : ""}
          ${p.sex ? `<div class="field"><label>Gênero</label><span>${p.sex}</span></div>` : ""}
          <div class="field"><label>Nacionalidade(s)</label><span>${nats}</span></div>
          <div class="field"><label>Categoria</label><span>${isWanted ? "Procurado" : "Desaparecido"}</span></div>
          ${b.ingested_at ? `<div class="field"><label>Indexado em</label><span>${b.ingested_at.slice(0, 10)}</span></div>` : ""}
        </div>
        ${b.reward ? `
        <div class="reward-box">
          <span class="reward-icon">💰</span>
          <div><div class="reward-label">Recompensa</div><div class="reward-value">${escHtml(b.reward)}</div></div>
        </div>` : ""}
        ${p.url ? `<a class="modal-link" href="${p.url}" target="_blank">🔗 Ver perfil oficial ↗</a>` : ""}
      </div>
    </div>
    ${p.crimes.length ? `<div class="section-title">Crimes / Acusações</div><ul class="crime-list">${crimes}</ul>` : ""}
    ${b.description ? `<div class="section-title">Descrição</div><div class="description-text">${escHtml(b.description.slice(0, 800))}</div>` : ""}
  `;
}

// ── Filtros ───────────────────────────────────────────────────────────────────
document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        state.category = btn.dataset.category;
        loadPage(true);
    });
});

sourceFilter.addEventListener("change", () => {
    state.source = sourceFilter.value;
    loadPage(true);
});
countryFilter.addEventListener("change", () => {
    state.country = countryFilter.value;
    loadPage(true);
});
bioCheck.addEventListener("change", () => {
    state.bioOnly = bioCheck.checked;
    loadPage(true);
});

loadMoreBtn.addEventListener("click", () => loadPage(false));

// Search debounce
let searchDebounce;
searchInput.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
        state.searchTerm = searchInput.value.trim();
        loadPage(true);
    }, 400);
});
searchInput.addEventListener("keydown", e => {
    if (e.key === "Enter") {
        clearTimeout(searchDebounce);
        state.searchTerm = searchInput.value.trim();
        loadPage(true);
    }
});

// Modal close
modalClose.addEventListener("click", closeModal);
modalOverlay.addEventListener("click", e => { if (e.target === modalOverlay) closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
function closeModal() {
    modalOverlay.classList.remove("open");
    document.body.style.overflow = "";
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function parseNats(natsJson) {
    try {
        const arr = JSON.parse(natsJson || "[]");
        return Array.isArray(arr) ? arr.filter(Boolean) : [];
    } catch { return natsJson ? natsJson.split(";").filter(Boolean) : []; }
}

function escHtml(str) {
    return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showSkeletons(n) {
    for (let i = 0; i < n; i++) {
        const sk = document.createElement("div");
        sk.className = "card-skeleton skeleton-el";
        sk.innerHTML = `<div class="skeleton-img"></div><div class="skeleton-body"><div class="skeleton-line"></div><div class="skeleton-line short"></div></div>`;
        grid.appendChild(sk);
    }
}
function removeSkeletons() {
    document.querySelectorAll(".skeleton-el").forEach(el => el.remove());
}

function showToast(msg, duration = 3000) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), duration);
}

// Export CSV  
document.getElementById("exportBtn")?.addEventListener("click", async () => {
    try {
        showToast("Exportando CSV...");
        // Chamar backend para export (futuro comando); por ora mostrar instrução
        showToast("Use: poetry run python intelligence_db.py search → opção 'e'");
    } catch (e) { showToast("Erro: " + e); }
});
