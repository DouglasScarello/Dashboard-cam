// Intelligence Catalog — Backend Tauri (Rust)
// Lê intelligence.db via rusqlite e expõe comandos ao frontend.

use rusqlite::{Connection, Result as SqlResult, params};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use base64::{Engine as _, engine::general_purpose::STANDARD as B64};

fn db_path() -> PathBuf {
    let candidates = [
        "/home/douglasdsr/Documentos/Projects/FBI/Dashboard/intelligence/data/intelligence.db",
        "../../intelligence/data/intelligence.db",
        "../intelligence/data/intelligence.db",
        "data/intelligence.db",
    ];
    for c in &candidates {
        let p = PathBuf::from(c);
        if p.exists() { 
            println!("[CATALOG] Usando banco de dados em: {:?}", p);
            return p; 
        }
    }
    let fallback = PathBuf::from("/home/douglasdsr/Documentos/Projects/FBI/Dashboard/intelligence/data/intelligence.db");
    println!("[CATALOG] Banco não encontrado nos candidatos, tentando fallback: {:?}", fallback);
    fallback
}

fn open_db() -> SqlResult<Connection> {
    Connection::open(db_path())
}

#[derive(Serialize, Deserialize)]
struct Individual {
    id:            String,
    name:          String,
    category:      String,
    source:        String,
    birth_date:    Option<String>,
    nationalities: Option<String>,
    description:   Option<String>,
    reward:        Option<String>,
    img_path:      Option<String>,
    has_embedding: i32,
    ingested_at:   Option<String>,
}

#[derive(Serialize, Deserialize)]
struct IndividualImage {
    img_url:     Option<String>,
    img_path:    Option<String>,
    caption:     Option<String>,
    is_primary:  i32,
}

#[derive(Serialize, Deserialize)]
struct IndividualDetail {
    id:            String,
    name:          String,
    category:      String,
    source:        String,
    birth_date:    Option<String>,
    nationalities: Option<String>,
    description:   Option<String>,
    reward:        Option<String>,
    img_path:      Option<String>,
    has_embedding: i32,
    aliases:       Option<String>,
    sex:           Option<String>,
    url:           Option<String>,
    // Novos campos
    height_cm:     Option<f64>,
    weight_kg:     Option<f64>,
    eye_color:     Option<String>,
    hair_color:    Option<String>,
    occupation:    Option<String>,
    images:        Vec<IndividualImage>,
    crimes:        Vec<String>,
    locations:     Vec<Location>,
    ingested_at:   Option<String>,
}

#[derive(Serialize, Deserialize)]
struct Location {
    loc_type: String,
    country:  Option<String>,
    state:    Option<String>,
    city:     Option<String>,
    details:  Option<String>,
}

#[derive(Serialize, Deserialize)]
struct Stats {
    total:           i64,
    wanted:          i64,
    missing:         i64,
    with_biometrics: i64,
    by_source:       Vec<SourceCount>,
}

#[derive(Serialize, Deserialize)]
struct SourceCount { source: String, count: i64 }

struct TranslateState {
    client: reqwest::Client,
}

// ─── Comandos ─────────────────────────────────────────────────────────────────

#[tauri::command]
fn search_individuals(
    name:          Option<String>,
    category:      Option<String>,
    country:       Option<String>,
    crime:         Option<String>,
    has_embedding: Option<bool>,
    source_filter: Option<String>,
    page:          Option<u32>,
    limit:         Option<u32>,
) -> Result<Vec<Individual>, String> {
    let conn  = open_db().map_err(|e| e.to_string())?;
    let lim   = limit.unwrap_or(40) as i64;
    let off   = (page.unwrap_or(0) as i64) * lim;

    let mut conds = vec!["1=1".to_string()];
    let mut vals: Vec<String> = vec![];

    if let Some(n) = name.as_deref() {
        if !n.is_empty() {
            conds.push("(i.name LIKE ? OR i.description LIKE ?)".into());
            vals.push(format!("%{n}%"));
            vals.push(format!("%{n}%"));
        }
    }
    if let Some(c) = category.as_deref() {
        if !c.is_empty() { conds.push("i.category = ?".into()); vals.push(c.into()); }
    }
    if let Some(co) = country.as_deref() {
        if !co.is_empty() { conds.push("i.nationalities LIKE ?".into()); vals.push(format!("%{co}%")); }
    }
    if let Some(src) = source_filter.as_deref() {
        if !src.is_empty() { conds.push("i.source LIKE ?".into()); vals.push(format!("%{src}%")); }
    }
    if let Some(has_bio) = has_embedding {
        conds.push("i.has_embedding = ?".into());
        vals.push(if has_bio { "1".into() } else { "0".into() });
    }

    let crime_join = if let Some(cr) = crime.as_deref() {
        if !cr.is_empty() {
            conds.push("c.crime LIKE ?".into());
            vals.push(format!("%{cr}%"));
            "LEFT JOIN crimes c ON c.individual_id = i.id"
        } else { "" }
    } else { "" };

    let sql = format!(
        "SELECT DISTINCT i.id, i.name, i.category, i.source, i.birth_date, i.nationalities,
                i.description, i.reward, i.img_path, i.has_embedding, i.ingested_at
         FROM individuals i {crime_join}
         WHERE {where_clause}
         ORDER BY i.has_embedding DESC, i.ingested_at DESC, i.name ASC LIMIT ? OFFSET ?",
        crime_join = crime_join,
        where_clause = conds.join(" AND ")
    );

    println!("[TAURI-DEBUG] SQL: {}", sql);
    println!("[TAURI-DEBUG] Params: {:?}", vals);

    let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
    
    let mut query_params: Vec<&dyn rusqlite::ToSql> = Vec::new();
    for v in &vals {
        query_params.push(v);
    }
    query_params.push(&lim);
    query_params.push(&off);

    let rows = stmt.query_map(rusqlite::params_from_iter(query_params), |row| {
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

    let mut results = Vec::new();
    for row in rows {
        results.push(row.map_err(|e| e.to_string())?);
    }
    println!("[TAURI-DEBUG] Encontrados: {} indivíduos", results.len());
    Ok(results)
}

#[tauri::command]
fn get_individual(id: String) -> Result<IndividualDetail, String> {
    let conn = open_db().map_err(|e| e.to_string())?;
    
    let mut stmt = conn.prepare(
        "SELECT id,name,category,source,birth_date,nationalities,description,
                reward,img_path,has_embedding,aliases,sex,url,ingested_at,
                height_cm, weight_kg, eye_color, hair_color, occupation
         FROM individuals WHERE id=?"
    ).map_err(|e| e.to_string())?;
    
    let row = stmt.query_row(params![id], |r| Ok(IndividualDetail {
            id:            r.get(0)?,
            name:          r.get(1)?,
            category:      r.get(2)?,
            source:        r.get(3)?,
            birth_date:    r.get(4)?,
            nationalities: r.get(5)?,
            description:   r.get(6)?,
            reward:        r.get(7)?,
            img_path:      r.get(8)?,
            has_embedding: r.get(9)?,
            aliases:       r.get(10)?,
            sex:           r.get(11)?,
            url:           r.get(12)?,
            ingested_at:   r.get(13)?,
            height_cm:     r.get(14)?,
            weight_kg:     r.get(15)?,
            eye_color:     r.get(16)?,
            hair_color:    r.get(17)?,
            occupation:    r.get(18)?,
            images:        vec![], // Preenchido depois
            crimes:        vec![],
            locations:     vec![],
        })).map_err(|e| e.to_string())?;

    // Crimes
    let mut stmt_crimes = conn.prepare("SELECT crime FROM crimes WHERE individual_id=?")
        .map_err(|e| e.to_string())?;
    let crimes: Vec<String> = stmt_crimes.query_map(params![id], |r| r.get(0))
        .map_err(|e| e.to_string())?
        .filter_map(|r| r.ok()).collect();

    // Locations
    let mut stmt_locs = conn.prepare("SELECT type, country, state, city, details FROM locations WHERE individual_id=?")
        .map_err(|e| e.to_string())?;
    let locations: Vec<Location> = stmt_locs.query_map(params![id], |r| {
        Ok(Location {
            loc_type: r.get(0)?,
            country:  r.get(1)?,
            state:    r.get(2)?,
            city:     r.get(3)?,
            details:  r.get(4)?,
        })
    }).map_err(|e| e.to_string())?.filter_map(|r| r.ok()).collect();

    // Images (Galeria)
    let mut stmt_imgs = conn.prepare("SELECT img_url, img_path, caption, is_primary FROM individual_images WHERE individual_id=?")
        .map_err(|e| e.to_string())?;
    let images: Vec<IndividualImage> = stmt_imgs.query_map(params![id], |r| {
        Ok(IndividualImage {
            img_url:  r.get(0)?,
            img_path: r.get(1)?,
            caption:  r.get(2)?,
            is_primary: r.get(3)?,
        })
    }).map_err(|e| e.to_string())?.filter_map(|r| r.ok()).collect();

    Ok(IndividualDetail { crimes, locations, images, ..row })
}

#[tauri::command]
fn get_stats() -> Result<Stats, String> {
    let conn = open_db().map_err(|e| e.to_string())?;
    
    let total: i64 = conn.query_row("SELECT COUNT(*) FROM individuals", params![], |r| r.get(0))
        .map_err(|e| format!("Erro total: {}", e))?;
        
    let wanted: i64 = conn.query_row("SELECT COUNT(*) FROM individuals WHERE category='wanted'", params![], |r| r.get(0))
        .map_err(|e| format!("Erro wanted: {}", e))?;
        
    let missing: i64 = conn.query_row("SELECT COUNT(*) FROM individuals WHERE category='missing'", params![], |r| r.get(0))
        .map_err(|e| format!("Erro missing: {}", e))?;
        
    let with_biometrics: i64 = conn.query_row("SELECT COUNT(*) FROM individuals WHERE has_embedding=1", params![], |r| r.get(0))
        .map_err(|e| format!("Erro bio: {}", e))?;

    println!("[TAURI-DEBUG] Stats - Total: {}, Bio: {}", total, with_biometrics);

    let mut stmt = conn.prepare("SELECT source,COUNT(*) FROM individuals GROUP BY source ORDER BY COUNT(*) DESC LIMIT 10")
        .map_err(|e| e.to_string())?;
    let rows = stmt.query_map([], |r| Ok(SourceCount { source: r.get(0)?, count: r.get(1)? }))
        .map_err(|e| e.to_string())?;
    
    let mut by_source = Vec::new();
    for r in rows {
        by_source.push(r.map_err(|e| e.to_string())?);
    }

    Ok(Stats { total, wanted, missing, with_biometrics, by_source })
}

#[tauri::command]
fn get_image_base64(img_path: String) -> Result<String, String> {
    // Resolve caminho relativo para absoluto baseado na localização do banco
    let base_dir = PathBuf::from("/home/douglasdsr/Documentos/Projects/FBI/Dashboard/intelligence/");
    let mut abs_path = base_dir;
    abs_path.push(img_path);
    
    if !abs_path.exists() {
        println!("[CATALOG] Imagem não encontrada: {:?}", abs_path);
        return Err(format!("Imagem inexistente: {:?}", abs_path));
    }

    let bytes = std::fs::read(&abs_path).map_err(|e| e.to_string())?;
    Ok(format!("data:image/jpeg;base64,{}", B64.encode(&bytes)))
}
#[tauri::command]
async fn translate_text(
    q: String,
    source: String,
    target: String,
    state: tauri::State<'_, TranslateState>,
) -> Result<String, String> {
    let res = state.client
        .post("http://localhost:5000/translate")
        .json(&serde_json::json!({
            "q": q,
            "source": source,
            "target": target,
            "format": "text",
            "api_key": ""
        }))
        .send()
        .await
        .map_err(|e| format!("Erro na requisição: {}", e))?;

    if !res.status().is_success() {
        return Err(format!("LibreTranslate retornou erro: {}", res.status()));
    }

    let json: serde_json::Value = res.json().await.map_err(|e| format!("Erro ao ler JSON: {}", e))?;
    let translated = json["translatedText"]
        .as_str()
        .ok_or_else(|| "translatedText não encontrado no JSON".to_string())?;

    Ok(translated.to_string())
}

// ─── Entry ────────────────────────────────────────────────────────────────────
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(TranslateState { client: reqwest::Client::new() })
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            search_individuals,
            get_individual,
            get_stats,
            get_image_base64,
            translate_text,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
