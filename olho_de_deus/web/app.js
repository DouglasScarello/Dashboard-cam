/* Mesa de Investigação — Olho de Deus
   Sem framework, sem build — mesmo espírito das páginas /live-ai e
   /live-plates, só que reunindo tudo numa casca só com navegação por aba. */

const ROUTES = ["painel", "ao-vivo", "pessoas", "veiculos", "procurados"];
const CAM_FACE = "globetv_soi11_bangkok";
const CAM_PLATE_ID = "globetv_davao_leongarcia";
const CAM_PLATE_LIVEVIEW = "globetv_davao_leongarcia"; // nome do arquivo em live_view/

const board = document.getElementById("board");
const tabs = document.querySelectorAll(".tab");
const seal = document.getElementById("seal");
const lightbox = document.getElementById("lightbox");
const lightboxPanel = document.getElementById("lightbox-panel");

let pollHandle = null;

function currentRoute() {
  const h = (location.hash || "").replace("#", "");
  return ROUTES.includes(h) ? h : "painel";
}

function setActiveTab(route) {
  tabs.forEach(t => t.classList.toggle("active", t.dataset.route === route));
}

function stopPolling() {
  if (pollHandle) { clearInterval(pollHandle); pollHandle = null; }
}

async function fetchJSON(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso.replace(" ", "T") + "Z");
    return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch (e) { return iso; }
}

function timeAgo(iso) {
  if (!iso) return "nunca";
  const then = new Date(iso.replace(" ", "T") + "Z").getTime();
  const diffMin = Math.round((Date.now() - then) / 60000);
  if (diffMin < 1) return "agora mesmo";
  if (diffMin < 60) return `${diffMin} min atrás`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h atrás`;
  return `${Math.round(diffH / 24)}d atrás`;
}

/* ------------------------------------------------------------------ */
/* Roteador                                                             */
/* ------------------------------------------------------------------ */

async function render() {
  stopPolling();
  const route = currentRoute();
  setActiveTab(route);
  board.setAttribute("aria-busy", "true");

  const renderers = {
    "painel": renderPainel,
    "ao-vivo": renderAoVivo,
    "pessoas": renderPessoas,
    "veiculos": renderVeiculos,
    "procurados": renderProcurados,
  };
  await renderers[route]();
  board.setAttribute("aria-busy", "false");
}

window.addEventListener("hashchange", render);
tabs.forEach(t => t.addEventListener("click", () => { location.hash = t.dataset.route; }));

/* ------------------------------------------------------------------ */
/* Painel                                                                */
/* ------------------------------------------------------------------ */

async function renderPainel() {
  board.innerHTML = `<div class="section-head"><h2>Painel</h2><span class="meta">visão geral da operação</span></div>
    <div class="status-grid" id="status-grid"><div class="empty-state">carregando…</div></div>
    <div class="section-head" style="margin-top:8px;"><h2 style="font-size:16px;">Atividade recente</h2></div>
    <div class="activity-list" id="activity-list"><div class="empty-state">carregando…</div></div>`;

  const [persons, vehicles, plates, status] = await Promise.all([
    fetchJSON("/api/persons?limit=200"),
    fetchJSON("/api/vehicles?limit=200"),
    fetchJSON("/plates/recent?limit=10"),
    fetchJSON("/status"),
  ]);

  const pList = Array.isArray(persons) ? persons : [];
  const vList = Array.isArray(vehicles) ? vehicles : [];
  const plateList = Array.isArray(plates) ? plates : [];

  const lastPerson = pList[0]?.last_seen_at;
  const lastVehicle = vList[0]?.last_seen_at;

  document.getElementById("status-grid").innerHTML = `
    <div class="status-card ${lastPerson ? "on" : "off"}">
      <div class="status-card__label">Pessoas catalogadas</div>
      <div class="status-card__value">${pList.length}</div>
      <div class="status-card__sub">última: ${timeAgo(lastPerson)}</div>
    </div>
    <div class="status-card ${lastVehicle ? "on" : "off"}">
      <div class="status-card__label">Veículos catalogados</div>
      <div class="status-card__value">${vList.length}</div>
      <div class="status-card__sub">última: ${timeAgo(lastVehicle)}</div>
    </div>
    <div class="status-card ${plateList.length ? "on" : "off"}">
      <div class="status-card__label">Leituras de placa</div>
      <div class="status-card__value">${plateList.length}+</div>
      <div class="status-card__sub">consenso multi-frame</div>
    </div>
    <div class="status-card ${status ? "on" : "off"}">
      <div class="status-card__label">API</div>
      <div class="status-card__value">${status ? "ONLINE" : "OFFLINE"}</div>
      <div class="status-card__sub">cache: ${status?.redis?.mode || "degradado"}</div>
    </div>`;

  seal.textContent = status ? "sistema ativo" : "sem conexão";
  seal.className = "seal " + (status ? "seal--ok" : "seal--down");

  // Mescla pessoas + veículos + placas por hora, mais recente primeiro
  const rows = [
    ...pList.slice(0, 8).map(p => ({ t: p.last_seen_at, kind: "person", label: `${p.code} apareceu de novo`, img: null, times: p.times_seen })),
    ...vList.slice(0, 8).map(v => ({ t: v.last_seen_at, kind: "plate", label: `${v.code} (${v.plate_text}) — ${v.color || "?"} ${v.body_type || ""}`, img: null, times: v.times_seen })),
  ].sort((a, b) => new Date(b.t) - new Date(a.t)).slice(0, 12);

  document.getElementById("activity-list").innerHTML = rows.length
    ? rows.map(r => `<div class="activity-row">
        <span class="dot ${r.kind}"></span>
        <span>${r.label}${r.times > 1 ? ` <b style="color:var(--evidence-red)">·${r.times}x</b>` : ""}</span>
        <span class="time">${timeAgo(r.t)}</span>
      </div>`).join("")
    : `<div class="empty-state">Nenhuma atividade ainda — as câmeras estão rodando, aguardando alguém passar.</div>`;

  pollHandle = setInterval(renderPainel, 15000);
}

/* ------------------------------------------------------------------ */
/* Ao vivo                                                               */
/* ------------------------------------------------------------------ */

function renderAoVivo() {
  board.innerHTML = `
    <div class="section-head"><h2>Ao vivo</h2><span class="meta">reconhecimento facial + leitura de placa em tempo real</span></div>
    <div class="live-grid">
      <div class="live-feed">
        <div class="live-feed__label"><span class="rec"></span>ROSTO — Soi 11, Bangkok</div>
        <img id="feed-face" alt="carregando…">
      </div>
      <div class="live-feed">
        <div class="live-feed__label"><span class="rec"></span>PLACA — Leon Garcia St, Davao</div>
        <img id="feed-plate" alt="carregando…">
      </div>
    </div>`;

  const faceImg = document.getElementById("feed-face");
  const plateImg = document.getElementById("feed-plate");

  function refresh() {
    faceImg.src = `/live-frames/${CAM_FACE.includes("bangkok") ? "UemFRPrl1hk" : CAM_FACE}.jpg?t=${Date.now()}`;
    plateImg.src = `/live-frames/${CAM_PLATE_LIVEVIEW}_plates.jpg?t=${Date.now()}`;
  }
  refresh();
  pollHandle = setInterval(refresh, 700);
}

/* ------------------------------------------------------------------ */
/* Pessoas                                                               */
/* ------------------------------------------------------------------ */

async function renderPessoas() {
  board.innerHTML = `<div class="section-head"><h2>Pessoas</h2><span class="meta">identidade anônima — nunca nome real</span></div>
    <div class="card-grid" id="grid"><div class="empty-state">carregando…</div></div>`;

  const rows = await fetchJSON("/api/persons?limit=200");
  const grid = document.getElementById("grid");
  if (!Array.isArray(rows) || rows.length === 0) {
    grid.innerHTML = `<div class="empty-state">Ninguém catalogado ainda. Assim que um rosto de qualidade boa passar numa câmera, aparece aqui sozinho.</div>`;
    return;
  }
  grid.innerHTML = rows.map(p => `
    <article class="pin-card" data-kind="person" data-id="${p.id}" tabindex="0">
      <span class="pin-card__pin"></span>
      <img class="pin-card__photo" src="/api/persons/${p.id}" data-lazy-photo="${p.id}" alt="${p.code}">
      <div class="pin-card__code">${p.code}${p.times_seen > 1 ? `<span class="pin-card__tag">${p.times_seen}× visto</span>` : ""}</div>
      <div class="pin-card__meta">1ª vez: <b>${fmtTime(p.first_seen_at)}</b><br>última: <b>${fmtTime(p.last_seen_at)}</b></div>
    </article>`).join("");

  // Resolve a foto mais recente de cada card (a lista /api/persons não traz evidence_url — só a ficha traz)
  rows.forEach(async p => {
    const detail = await fetchJSON(`/api/persons/${p.id}`);
    const url = detail?.history?.[detail.history.length - 1]?.evidence_url;
    const el = grid.querySelector(`img[data-lazy-photo="${p.id}"]`);
    if (el && url) el.src = url;
  });

  grid.querySelectorAll(".pin-card").forEach(card => {
    card.addEventListener("click", () => openPersonDossier(card.dataset.id));
    card.addEventListener("keypress", e => { if (e.key === "Enter") openPersonDossier(card.dataset.id); });
  });
}

async function openPersonDossier(id) {
  const p = await fetchJSON(`/api/persons/${id}`);
  if (!p) return;
  const lastPhoto = p.history?.[p.history.length - 1]?.evidence_url || "";
  lightboxPanel.innerHTML = `
    <button class="dossier__close" id="dossier-close">×</button>
    <div class="dossier__head">
      <img class="dossier__photo" src="${lastPhoto}" alt="${p.code}">
      <div>
        <h3 class="dossier__code">${p.code}</h3>
        <div class="dossier__meta">
          Visto <b>${p.times_seen}×</b> · câmeras: ${p.cameras_seen || "—"}<br>
          1ª vez: ${fmtTime(p.first_seen_at)} · última: ${fmtTime(p.last_seen_at)}
        </div>
      </div>
    </div>
    <div class="timeline">${(p.history || []).slice().reverse().map(h => `
      <div class="timeline__item">
        <span class="timeline__dot"></span>
        ${h.evidence_url ? `<img src="${h.evidence_url}" alt="">` : ""}
        <div class="timeline__body"><span class="cam">${h.camera_id}</span><br><span class="t">${fmtTime(h.created_at)} · distância ${Number(h.distance).toFixed(3)}</span></div>
      </div>`).join("") || `<div class="empty-state">Sem histórico.</div>`}
    </div>`;
  openLightbox();
}

/* ------------------------------------------------------------------ */
/* Veículos                                                              */
/* ------------------------------------------------------------------ */

async function renderVeiculos() {
  board.innerHTML = `<div class="section-head"><h2>Veículos</h2><span class="meta">placa, cor e carroceria — reidentificação tolerante a erro de OCR</span></div>
    <div class="card-grid" id="grid"><div class="empty-state">carregando…</div></div>`;

  const rows = await fetchJSON("/api/vehicles?limit=200");
  const grid = document.getElementById("grid");
  if (!Array.isArray(rows) || rows.length === 0) {
    grid.innerHTML = `<div class="empty-state">Nenhum veículo catalogado ainda. Assim que uma placa fechar consenso, aparece aqui sozinho.</div>`;
    return;
  }
  grid.innerHTML = rows.map(v => `
    <article class="pin-card" data-kind="vehicle" data-id="${v.id}" tabindex="0">
      <span class="pin-card__pin"></span>
      <img class="pin-card__photo" data-lazy-photo="${v.id}" alt="${v.plate_text}">
      <div class="pin-card__code">${v.code || "V-?????????-?"}${v.times_seen > 1 ? `<span class="pin-card__tag">${v.times_seen}× visto</span>` : ""}</div>
      <div class="pin-card__meta">placa <b>${v.plate_text}</b> · ${v.color || "?"} ${v.body_type || ""}<br>última: <b>${fmtTime(v.last_seen_at)}</b></div>
    </article>`).join("");

  rows.forEach(async v => {
    const detail = await fetchJSON(`/api/vehicles/${v.id}`);
    const url = detail?.history?.[detail.history.length - 1]?.evidence_url;
    const el = grid.querySelector(`img[data-lazy-photo="${v.id}"]`);
    if (el && url) el.src = url;
  });

  grid.querySelectorAll(".pin-card").forEach(card => {
    card.addEventListener("click", () => openVehicleDossier(card.dataset.id));
    card.addEventListener("keypress", e => { if (e.key === "Enter") openVehicleDossier(card.dataset.id); });
  });
}

async function openVehicleDossier(id) {
  const v = await fetchJSON(`/api/vehicles/${id}`);
  if (!v) return;
  const lastPhoto = v.history?.[v.history.length - 1]?.evidence_url || "";
  lightboxPanel.innerHTML = `
    <button class="dossier__close" id="dossier-close">×</button>
    <div class="dossier__head">
      <img class="dossier__photo" src="${lastPhoto}" alt="${v.plate_text}">
      <div>
        <h3 class="dossier__code">${v.code || "V-?????????-?"}</h3>
        <div class="dossier__meta">
          Placa <b>${v.plate_text}</b> (${v.country_code || "?"}) · ${v.color || "?"} ${v.body_type || ""}<br>
          Visto <b>${v.times_seen}×</b> · câmeras: ${v.cameras_seen || "—"}<br>
          1ª vez: ${fmtTime(v.first_seen_at)} · última: ${fmtTime(v.last_seen_at)}
        </div>
      </div>
    </div>
    <div class="timeline">${(v.history || []).slice().reverse().map(h => `
      <div class="timeline__item">
        <span class="timeline__dot"></span>
        ${h.evidence_url ? `<img src="${h.evidence_url}" alt="">` : ""}
        <div class="timeline__body"><span class="cam">${h.camera_id}</span><br><span class="t">${fmtTime(h.created_at)} · confiança ${Math.round((h.confidence||0)*100)}% · ${h.frames_voted} frames</span></div>
      </div>`).join("") || `<div class="empty-state">Sem histórico.</div>`}
    </div>`;
  openLightbox();
}

/* ------------------------------------------------------------------ */
/* Procurados (banco FBI existente)                                      */
/* ------------------------------------------------------------------ */

async function renderProcurados() {
  board.innerHTML = `<div class="section-head"><h2>Procurados</h2><span class="meta">banco público (FBI) já cadastrado</span></div>
    <div class="card-grid" id="grid"><div class="empty-state">carregando…</div></div>`;

  const data = await fetchJSON("/api/catalog/individuals?limit=60");
  const rows = Array.isArray(data) ? data : (data?.individuals || data?.items || []);
  const grid = document.getElementById("grid");
  if (!rows || rows.length === 0) {
    grid.innerHTML = `<div class="empty-state">Não consegui carregar o catálogo — confira se /api/catalog/individuals está disponível.</div>`;
    return;
  }
  grid.innerHTML = rows.map(r => `
    <article class="pin-card">
      <span class="pin-card__pin"></span>
      <img class="pin-card__photo" src="${r.img_url || ""}" alt="${r.name || ""}" onerror="this.style.opacity=0.15">
      <div class="pin-card__code" style="font-family:var(--font-body);font-weight:700;font-size:13px;">${r.name || "sem nome"}</div>
      <div class="pin-card__meta">${(r.category || "").toUpperCase()}${r.threat_score ? ` · risco ${r.threat_score}` : ""}</div>
    </article>`).join("");
}

/* ------------------------------------------------------------------ */
/* Lightbox                                                              */
/* ------------------------------------------------------------------ */

function openLightbox() {
  lightbox.hidden = false;
  document.getElementById("dossier-close")?.addEventListener("click", closeLightbox);
}
function closeLightbox() { lightbox.hidden = true; lightboxPanel.innerHTML = ""; }
document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeLightbox(); });

/* ------------------------------------------------------------------ */
/* Boot                                                                  */
/* ------------------------------------------------------------------ */

render();
