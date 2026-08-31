CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    nome TEXT,
    local TEXT,
    endereco TEXT,
    cidade TEXT,
    uf TEXT,
    tipo_area TEXT,
    setor TEXT,
    pais TEXT,
    thumbnail_url TEXT,
    url TEXT,
    video_id TEXT,
    lat REAL,
    long REAL,
    confirmed_dead BOOLEAN DEFAULT 0,
    live_confirmed BOOLEAN DEFAULT 0,
    live_status TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cameras_lat_long ON cameras(lat, long);
CREATE INDEX IF NOT EXISTS idx_cameras_pais ON cameras(pais);
CREATE INDEX IF NOT EXISTS idx_cameras_tipo_area ON cameras(tipo_area);
CREATE INDEX IF NOT EXISTS idx_cameras_confirmed_dead ON cameras(confirmed_dead);
