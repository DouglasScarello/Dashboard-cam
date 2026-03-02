// Intelligence Catalog — Backend Tauri (Rust)
// Lê a base SQLite intelligence.db e expõe comandos para o frontend.

use rusqlite::{Connection, Result as SqlResult, params};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use base64::{Engine as _, engine::general_purpose::STANDARD as B64};

// ─── Caminho do banco (relativo ao executável ou configurável) ───────────────
fn db_path() -> PathBuf {
    // Procura em locais padrão
    let candidates = [
        "../intelligence/data/intelligence.db",
        "../../intelligence/data/intelligence.db",
        "data/intelligence.db",
        "../data/intelligence.db",
    ];
    for c in candidates {
        let p = PathBuf::from(c);
        if p.exists() { return p; }
    }
    // Fallback
    PathBuf::from("intelligence/data/intelligence.db")
}

fn open_db() -> SqlResult<Connection> {
    Connection::open(db_path())
}

// ─── Structs serializáveis ────────────────────────────────────────────────────
#[derive(Serialize, Deserialize)]
pub struct Individual {
    pub id:            String,
    pub name:          String,
    pub category:      String,           // "wanted" | "missing"
    pub source:        String,
    pub birth_date:    Option<String>,
    pub nationalities: Option<String>,   // JSON array string
    pub description:   Option<String>,
    pub reward:        Option<String>,
    pub img_path:      Option<String>,
    pub has_embedding: i32,
    pub ingested_at:   Option<String>,
}

#[derive(Serialize, Deserialize)]
pub struct IndividualDetail {
    #[serde(flatten)]
    pub base:      Individual,
    pub aliases:   Option<String>,
    pub sex:       Option<String>,
    pub url:       Option<String>,
    pub crimes:    Vec<String>,
    pub locations: Vec<LocationRow>,
}

#[derive(Serialize, Deserialize)]
pub struct LocationRow {
    pub loc_type: String,
    pub country:  Option<String>,
    pub state:    Option<String>,
    pub city:     Option<String>,
    pub details:  Option<String>,
}

#[derive(Serialize, Deserialize)]
pub struct Stats {
    pub total:            i64,
    pub wanted:           i64,
    pub missing:          i64,
    pub with_biometrics:  i64,
    pub by_source:        Vec<SourceCount>,
}

#[derive(Serialize, Deserialize)]
pub struct SourceCount {
    pub source: String,
    pub count:  i64,
}

// ─── Comandos Tauri ───────────────────────────────────────────────────────────

#[tauri::command]
pub fn search_individuals(
    name:          Option<String>,
    category:      Option<String>,
    country:       Option<String>,
    crime:         Option<String>,
    has_embedding: Option<bool>,
    source_filter: Option<String>,
    page:          Option<u32>,
    limit:         Option<u32>,
) -> Result<Vec<Individual>, String> {
    let conn   = open_db().map_err(|e| e.to_string())?;
    let limit  = limit.unwrap_or(40) as i64;
    let offset = (page.unwrap_or(0) as i64) * limit;

    let mut conditions = vec!["1=1".to_string()];
    let mut values: Vec<Box<dyn rusqlite::ToSql>> = vec![];

    if let Some(n) = &name {
        if !n.is_empty() {
            conditions.push("(i.name LIKE ? OR i.aliases LIKE ? OR i.description LIKE ?)".into());
            let pat = format!("%{}%", n);
            values.push(Box::new(pat.clone()));
            values.push(Box::new(pat.clone()));
            values.push(Box::new(pat));
        }
    }
    if let Some(c) = &category {
        if !c.is_empty() {
            conditions.push("i.category = ?".into());
            values.push(Box::new(c.clone()));
        }
    }
    if let Some(co) = &country {
        if !co.is_empty() {
            conditions.push("i.nationalities LIKE ?".into());
            values.push(Box::new(format!("%{}%", co)));
        }
    }
    if let Some(src) = &source_filter {
        if !src.is_empty() {
            conditions.push("i.source LIKE ?".into());
            values.push(Box::new(format!("%{}%", src)));
        }
    }
    if let Some(has_bio) = has_embedding {
        conditions.push("i.has_embedding = ?".into());
        values.push(Box::new(if has_bio { 1i64 } else { 0i64 }));
    }

    // Crime join
    let crime_join = if let Some(cr) = &crime {
        if !cr.is_empty() {
            conditions.push("c.crime LIKE ?".into());
            values.push(Box::new(format!("%{}%", cr)));
            "LEFT JOIN crimes c ON c.individual_id = i.id"
        } else { "" }
    } else { "" };

    let sql = format!(
        "SELECT DISTINCT i.id, i.name, i.category, i.source,
                i.birth_date, i.nationalities, i.description,
                i.reward, i.img_path, i.has_embedding, i.ingested_at
         FROM individuals i {crime_join}
         WHERE {where}
         ORDER BY i.has_embedding DESC, i.name ASC
         LIMIT ? OFFSET ?",
        crime_join = crime_join,
        where = conditions.join(" AND ")
    );

    values.push(Box::new(limit));
    values.push(Box::new(offset));

    let params: Vec<&dyn rusqlite::ToSql> = values.iter().map(|v| v.as_ref()).collect();

    let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
    let rows = stmt.query_map(params.as_slice(), |row| {
        Ok(Individual {
            id:            row.get(0)?,
            name:          row.get(1)?,
            category:      row.get(2)?,
            source:        row.get(3)?,
            birth_date:    row.get(4)?,
            nationalities: row.get(5)?,
            description:   row.get(6)?,
            reward:        row.get(7)?,
            img_path:      row.get(8)?,
            has_embedding: row.get(9)?,
            ingested_at:   row.get(10)?,
        })
    }).map_err(|e| e.to_string())?;

    rows.collect::<SqlResult<Vec<_>>>().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_individual(id: String) -> Result<IndividualDetail, String> {
    let conn = open_db().map_err(|e| e.to_string())?;

    let base: Individual = conn.query_row(
        "SELECT id, name, category, source, birth_date, nationalities,
                description, reward, img_path, has_embedding, ingested_at
         FROM individuals WHERE id = ?",
        params![id],
        |row| Ok(Individual {
            id:            row.get(0)?,
            name:          row.get(1)?,
            category:      row.get(2)?,
            source:        row.get(3)?,
            birth_date:    row.get(4)?,
            nationalities: row.get(5)?,
            description:   row.get(6)?,
            reward:        row.get(7)?,
            img_path:      row.get(8)?,
            has_embedding: row.get(9)?,
            ingested_at:   row.get(10)?,
        }),
    ).map_err(|e| e.to_string())?;

    let (aliases, sex, url): (Option<String>, Option<String>, Option<String>) =
        conn.query_row(
            "SELECT aliases, sex, url FROM individuals WHERE id = ?",
            params![id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        ).unwrap_or((None, None, None));

    // Crimes
    let mut stmt = conn.prepare("SELECT crime FROM crimes WHERE individual_id = ?")
        .map_err(|e| e.to_string())?;
    let crimes: Vec<String> = stmt.query_map(params![id], |row| row.get(0))
        .map_err(|e| e.to_string())?
        .filter_map(|r| r.ok())
        .collect();

    // Locais
    let mut stmt = conn.prepare(
        "SELECT type, country, state, city, details FROM locations WHERE individual_id = ?"
    ).map_err(|e| e.to_string())?;
    let locations: Vec<LocationRow> = stmt.query_map(params![id], |row| {
        Ok(LocationRow {
            loc_type: row.get(0)?,
            country:  row.get(1)?,
            state:    row.get(2)?,
            city:     row.get(3)?,
            details:  row.get(4)?,
        })
    }).map_err(|e| e.to_string())?
      .filter_map(|r| r.ok())
      .collect();

    Ok(IndividualDetail { base, aliases, sex, url, crimes, locations })
}

#[tauri::command]
pub fn get_stats() -> Result<Stats, String> {
    let conn = open_db().map_err(|e| e.to_string())?;

    let total:           i64 = conn.query_row("SELECT COUNT(*) FROM individuals", [], |r| r.get(0)).unwrap_or(0);
    let wanted:          i64 = conn.query_row("SELECT COUNT(*) FROM individuals WHERE category='wanted'", [], |r| r.get(0)).unwrap_or(0);
    let missing:         i64 = conn.query_row("SELECT COUNT(*) FROM individuals WHERE category='missing'", [], |r| r.get(0)).unwrap_or(0);
    let with_biometrics: i64 = conn.query_row("SELECT COUNT(*) FROM individuals WHERE has_embedding=1", [], |r| r.get(0)).unwrap_or(0);

    let mut stmt = conn.prepare(
        "SELECT source, COUNT(*) as cnt FROM individuals GROUP BY source ORDER BY cnt DESC LIMIT 10"
    ).map_err(|e| e.to_string())?;
    let by_source: Vec<SourceCount> = stmt.query_map([], |row| {
        Ok(SourceCount { source: row.get(0)?, count: row.get(1)? })
    }).map_err(|e| e.to_string())?
      .filter_map(|r| r.ok())
      .collect();

    Ok(Stats { total, wanted, missing, with_biometrics, by_source })
}

#[tauri::command]
pub fn get_image_base64(img_path: String) -> Result<String, String> {
    let bytes = std::fs::read(&img_path).map_err(|e| e.to_string())?;
    Ok(format!("data:image/jpeg;base64,{}", B64.encode(&bytes)))
}

// ─── Entry point ─────────────────────────────────────────────────────────────
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            search_individuals,
            get_individual,
            get_stats,
            get_image_base64,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
