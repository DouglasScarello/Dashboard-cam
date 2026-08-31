import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "database" / "live_cameras.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_cameras(
    limit: int = 50, 
    offset: int = 0, 
    country: str = None, 
    area: str = None, 
    status: str = "ALL", 
    geo: str = "ALL",
    search: str = None
) -> Dict[str, Any]:
    
    conn = get_connection()
    query = "SELECT * FROM cameras WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM cameras WHERE 1=1"
    params = []
    
    if country:
        query += " AND (UPPER(pais) = ? OR UPPER(setor) = ?)"
        count_query += " AND (UPPER(pais) = ? OR UPPER(setor) = ?)"
        params.extend([country.upper(), country.upper()])
        
    if area:
        query += " AND UPPER(tipo_area) = ?"
        count_query += " AND UPPER(tipo_area) = ?"
        params.append(area.upper())
        
    if status == "ONLINE":
        query += " AND confirmed_dead = 0"
        count_query += " AND confirmed_dead = 0"
    elif status == "OFFLINE":
        query += " AND confirmed_dead = 1"
        count_query += " AND confirmed_dead = 1"
        
    if geo == "WITH_GEO":
        query += " AND lat IS NOT NULL AND long IS NOT NULL"
        count_query += " AND lat IS NOT NULL AND long IS NOT NULL"
    elif geo == "NO_GEO":
        query += " AND (lat IS NULL OR long IS NULL)"
        count_query += " AND (lat IS NULL OR long IS NULL)"
        
    if search:
        search_term = f"%{search.lower()}%"
        search_clause = """ AND (
            LOWER(nome) LIKE ? OR 
            LOWER(endereco) LIKE ? OR 
            LOWER(local) LIKE ? OR 
            LOWER(cidade) LIKE ? OR 
            LOWER(tipo_area) LIKE ? OR 
            LOWER(pais) LIKE ?
        )"""
        query += search_clause
        count_query += search_clause
        params.extend([search_term] * 6)
        
    # Somente retornar cameras REAIS (tem video_id ou url)
    real_cam_clause = " AND (video_id IS NOT NULL OR url IS NOT NULL AND url != '')"
    query += real_cam_clause
    count_query += real_cam_clause
    
    query += " LIMIT ? OFFSET ?"
    params_with_limit = params + [limit, offset]
    
    cursor = conn.cursor()
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]
    
    cursor.execute(query, params_with_limit)
    rows = cursor.fetchall()
    conn.close()
    
    cameras = [dict(row) for row in rows]
    return {
        "cameras": cameras,
        "total": total_count,
        "limit": limit,
        "offset": offset
    }

def get_cameras_in_bbox(north: float, south: float, east: float, west: float, limit: int = 1000) -> List[Dict[str, Any]]:
    conn = get_connection()
    # Somente cameras ativas e reais
    query = """
        SELECT * FROM cameras 
        WHERE confirmed_dead = 0 
        AND lat IS NOT NULL AND long IS NOT NULL
        AND (video_id IS NOT NULL OR url IS NOT NULL AND url != '')
        AND lat BETWEEN ? AND ? 
        AND long BETWEEN ? AND ?
        LIMIT ?
    """
    cursor = conn.cursor()
    # SQLite BETWEEN is inclusive. Make sure south is first, then north.
    cursor.execute(query, (south, north, west, east, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_unique_countries() -> List[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT UPPER(COALESCE(pais, setor)) FROM cameras WHERE pais IS NOT NULL OR setor IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return sorted([r[0] for r in rows if r[0] and len(r[0]) <= 3])

def get_unique_areas() -> List[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT UPPER(tipo_area) FROM cameras WHERE tipo_area IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return sorted([r[0] for r in rows if r[0]])

def get_camera_by_id(camera_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
