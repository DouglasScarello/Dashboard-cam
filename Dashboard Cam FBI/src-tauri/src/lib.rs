use std::fs;
use std::path::PathBuf;
use sysinfo::{CpuExt, System, SystemExt, ComponentExt};

#[derive(serde::Serialize)]
struct SystemStats {
    cpu_usage: f32,
    cpu_count: usize,
    memory_total: u64,
    memory_used: u64,
    temp: f32,
    uptime: u64,
    cores_usage: Vec<f32>,
}

#[tauri::command]
fn get_live_id(search_term: String) -> Result<String, String> {
    // Executa o yt-dlp para buscar o ID mais recente
    // Usamos o comando que já validamos no Python
    let search_query = format!("ytsearch1:{} live", search_term);
    let output = Command::new("yt-dlp")
        .args(&[
            "--get-id",
            "--no-warnings",
            "--flat-playlist",
            &search_query
        ])
        .output()
        .map_err(|e| e.to_string())?;

    if output.status.success() {
        let id = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if id.is_empty() {
            Err("Nenhum vídeo encontrado".to_string())
        } else {
            Ok(id)
        }
    } else {
        let err = String::from_utf8_lossy(&output.stderr);
        Err(err.to_string())
    }
}

#[tauri::command]
fn get_cameras() -> Result<String, String> {
    // Usando caminho absoluto para garantir acesso em ambiente de desenvolvimento
    let path = PathBuf::from("/home/douglasdsr/Documentos/Projects/FBI/Dashboard/database/omni_cams.json");

    if !path.exists() {
        println!("[OSS ERROR] Arquivo não encontrado em: {:?}", path);
        return Ok("[]".to_string());
    }

    fs::read_to_string(path).map_err(|e| e.to_string())
}

#[derive(serde::Serialize)]
struct Sighting {
    id: String,
    individual_id: String,
    camera_id: Option<String>,
    captured_at: String,
    name: String,
    threat_score: f64,
}

#[tauri::command]
fn get_recent_sightings() -> Result<Vec<Sighting>, String> {
    let path = "/home/douglasdsr/Documentos/Projects/FBI/Dashboard/intelligence/data/intelligence.db";
    let conn = rusqlite::Connection::open(path).map_err(|e| e.to_string())?;

    let mut stmt = conn.prepare(
        "SELECT e.id, e.individual_id, e.camera_id, e.captured_at, i.name, COALESCE(t.score, 1.0) as threat_score
         FROM evidence e
         JOIN individuals i ON e.individual_id = i.id
         LEFT JOIN threat_scores t ON e.individual_id = t.individual_id
         ORDER BY e.captured_at DESC
         LIMIT 50"
    ).map_err(|e| e.to_string())?;

    let sighting_iter = stmt.query_map([], |row| {
        Ok(Sighting {
            id: row.get(0)?,
            individual_id: row.get(1)?,
            camera_id: row.get(2)?,
            captured_at: row.get(3)?,
            name: row.get(4)?,
            threat_score: row.get(5)?,
        })
    }).map_err(|e| e.to_string())?;

    let mut sightings = Vec::new();
    for sighting in sighting_iter {
        sightings.push(sighting.map_err(|e| e.to_string())?);
    }

    Ok(sightings)
}

#[tauri::command]
fn get_system_stats() -> SystemStats {
    let mut sys = System::new_all();
    sys.refresh_all();
    
    // Pequena pausa para o sysinfo calcular o uso da CPU corretamente na primeira vez (ou se for chamado rápido demais)
    std::thread::sleep(std::time::Duration::from_millis(100));
    sys.refresh_cpu();

    let cpu_usage = sys.global_cpu_info().cpu_usage();
    let cpu_count = sys.cpus().len();
    let memory_total = sys.total_memory() / 1024 / 1024; // MB
    let memory_used = sys.used_memory() / 1024 / 1024;   // MB
    let uptime = sys.uptime();
    
    let cores_usage: Vec<f32> = sys.cpus().iter().map(|cpu| cpu.cpu_usage()).collect();

    // Tenta pegar a temperatura do primeiro componente relevante (Linux)
    let mut temp = 0.0;
    for component in sys.components() {
        if component.label().contains("CPU") || component.label().contains("Package") || component.label().contains("k10temp") {
            temp = component.temperature();
            break;
        }
    }

    SystemStats {
        cpu_usage,
        cpu_count,
        memory_total,
        memory_used,
        temp,
        uptime,
        cores_usage,
    }
}

#[tauri::command]
fn get_live_id(search_term: String) -> Result<String, String> {
    use std::process::Command;
    // Executa o yt-dlp para buscar o ID mais recente
    // Usamos o comando que já validamos no Python
    let search_query = format!("ytsearch1:{} live", search_term);
    let output = Command::new("yt-dlp")
        .args(&[
            "--get-id",
            "--no-warnings",
            "--flat-playlist",
            &search_query
        ])
        .output()
        .map_err(|e| e.to_string())?;

    if output.status.success() {
        let id = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if id.is_empty() {
            Err("Nenhum vídeo encontrado".to_string())
        } else {
            Ok(id)
        }
    } else {
        let err = String::from_utf8_lossy(&output.stderr);
        Err(err.to_string())
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet, get_live_id, get_cameras, get_recent_sightings, get_system_stats])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
