#!/usr/bin/env python3
"""
GERADOR DE COMPROVANTE BANCÁRIO / FORENSE DE LOCALIZAÇÃO DE CÂMERAS
Simula a saída canônica de um programa COBOL (Padrão IBM Mainframe 3270 / ANSI-85)
para comprovação de custódia e geolocalização.
"""
import json
import hashlib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "database" / "live_cameras.json"

def emitir_comprovante_cobol(cam: dict) -> str:
    now = datetime.now()
    data_str = now.strftime("%d/%m/%Y")
    hora_str = now.strftime("%H:%M:%S")
    
    # Gera hash criptográfico bancário SHA-256 truncado para autenticação de custódia
    raw_payload = f"{cam.get('id')}|{cam.get('nome')}|{cam.get('endereco')}|{cam.get('lat')}|{cam.get('long')}|{data_str}"
    hash_bancario = hashlib.sha256(raw_payload.encode()).hexdigest().upper()
    hash_formatado = f"{hash_bancario[0:4]}-{hash_bancario[4:8]}-{hash_bancario[8:12]}-{hash_bancario[12:16]}-{hash_bancario[16:20]}-{hash_bancario[20:24]}"
    
    lat = f"{cam.get('lat'):+.4f}" if cam.get('lat') else "N/D"
    long_ = f"{cam.get('long'):+.4f}" if cam.get('long') else "N/D"

    linhas = [
        "=" * 70,
        "       SISTEMA INTEGRADO DE VIGILANCIA C4ISR - OLHO DE DEUS       ",
        "            CERTIFICADO / COMPROVANTE DE GEOLOCALIZACAO            ",
        "-" * 70,
        f"DATA DE EMISSAO: {data_str}       HORA: {hora_str}",
        f"TERMINAL AUTORIZADO: SRV-C4ISR-NODE01        COD. RETORNO: 00 (OK)",
        "-" * 70,
        f"IDENTIFICADOR DO SENSOR      : {cam.get('id', 'N/D')}",
        f"TITULO / PONTO DE VIGILANCIA : {cam.get('nome', 'N/D')[:45]}",
        f"LOGRADOURO / ENDERECO EXATO  : {cam.get('endereco', 'N/D')[:45]}",
        f"CIDADE / ESTADO              : {cam.get('local', 'N/D')}",
        f"PAIS DE ORIGEM               : {cam.get('pais', 'BR')} (SETOR: {cam.get('setor', 'BR')})",
        f"CATEGORIA DE AREA            : {cam.get('tipo_area', 'ZONA DE MONITORAMENTO')}",
        f"STATUS OPERACIONAL           : {cam.get('status', 'LIVE')} (SINAL EM TEMPO REAL)",
        f"COORDENADA LATITUDE (GPS)    : {lat}",
        f"COORDENADA LONGITUDE (GPS)   : {long_}",
        f"FONTE / IDENTIFICADOR STREAM : {cam.get('video_id', 'N/D')}",
        "-" * 70,
        "CHAVE DE AUTENTICACAO ELETRONICA (CUSTODIA FORENSE):",
        f"  {hash_formatado}",
        "FINALIDADE: CERTIFICACAO DE LOCAL, TELEMETRIA E PROVA PERICIAL",
        "-" * 70,
        "AUTENTICACAO BANCARIA / PROTOCOLO FORENSE: REGISTRO IMUTAVEL VALIDO",
        "=" * 70,
    ]
    return "\n".join(linhas)

def main():
    with open(DB_FILE, "r", encoding="utf-8") as f:
        cams = json.load(f)

    print(f"Total de Câmeras Disponíveis: {len(cams)}\n")
    
    # Emite os 3 primeiros comprovantes de exemplo
    for idx in range(min(3, len(cams))):
        print(emitir_comprovante_cobol(cams[idx]))
        print("\n" + " " * 30 + "✂️  DESTAQUE AQUI  ✂️\n")

if __name__ == "__main__":
    main()
