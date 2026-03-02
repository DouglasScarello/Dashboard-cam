use std::process::Command;
use std::fs;
use std::path::PathBuf;

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

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet, get_live_id, get_cameras])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
