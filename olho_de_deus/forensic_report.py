import os
import sys
import time
from datetime import datetime
from fpdf import FPDF, XPos, YPos
from pathlib import Path
import logging
import hashlib
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from dotenv import load_dotenv

# Garantir que o root do projeto está no path para os helpers de intelligence
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

log = logging.getLogger("forensic_report")

# Carregar configurações de segurança
load_dotenv(ROOT / ".env")
ENCRYPTION_KEY = os.getenv("DOSSIIE_ENCRYPTION_KEY", "ghost_default_secure_key_32bytes")

def _encrypt_file(file_path: str, password: str):
    """Encripta um arquivo usando AES-256 (EAX mode para integridade)."""
    # Derivar chave de 32 bytes da senha
    key = hashlib.sha256(password.encode()).digest()
    
    with open(file_path, 'rb') as f:
        data = f.read()

    nonce = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_EAX, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(data)

    locked_path = file_path + ".locked"
    with open(locked_path, 'wb') as f:
        for x in [nonce, tag, ciphertext]:
            f.write(x)
    
    log.info(f"🛡️ Arquivo criptografado com sucesso: {locked_path}")
    return locked_path

def _sanitize_text(text: str) -> str:
    """Remove caracteres não compatíveis com latin-1 (emojis, símbolos especiais)."""
    if not text: return ""
    # Remove caracteres Unicode problemáticos mantendo a legibilidade
    return text.encode('latin-1', 'ignore').decode('latin-1')

class ForensicReport(FPDF):
    def header(self):
        # Banner de Topo - Estética COI
        self.set_fill_color(20, 30, 40)
        self.rect(0, 0, 210, 40, 'F')
        
        self.set_font("Helvetica", "B", 24)
        self.set_text_color(255, 255, 255)
        self.cell(0, 20, "DOSSIÊ PERICIAL - OLHO DE DEUS", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 5, _sanitize_text(f"RELATÓRIO DE INTELIGÊNCIA TÁTICA | GERADO EM: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Confidencial - Uso Exclusivo | Página {self.page_no()}/{{nb}} | GHOST PROTOCOL v9.0", align='C')

def generate_dossier_pdf(dossier: dict, output_path: str):
    """Gera um relatório PDF pericial completo p/ um indivíduo."""
    pdf = ForensicReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 1. IDENTIDADE VISUAL
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 10, _sanitize_text(f"ALVO: {dossier.get('name', 'DESCONHECIDO')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, _sanitize_text(f"ID ÚNICO: {dossier.get('id')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    # Grid de Fotos (Referência vs Captura)
    y_start = pdf.get_y()
    
    # Foto de Referência
    ref_path = dossier.get("img_path")
    if ref_path and os.path.exists(ref_path):
        try:
            pdf.image(ref_path, x=10, y=y_start, w=45)
            pdf.set_xy(10, y_start + 46)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(45, 5, "FOTO DE REFERÊNCIA", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        except Exception as e:
            log.error(f"Erro ao carregar imagem de referência: {e}")
            pdf.rect(10, y_start, 45, 45)
            pdf.set_xy(10, y_start + 20)
            pdf.cell(45, 5, "[ERRO IMAGEM]", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Última Evidência Capturada
    evidences = dossier.get("evidences", [])
    if evidences:
        last_ev = evidences[0]
        ev_path = last_ev.get("file_path")
        if ev_path and os.path.exists(ev_path):
            try:
                pdf.image(ev_path, x=65, y=y_start, w=45)
                pdf.set_xy(65, y_start + 46)
                pdf.cell(45, 5, "ÚLTIMA CAPTURA (LIVE)", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            except Exception:
                pdf.rect(65, y_start, 45, 45)

    pdf.ln(10)
    pdf.set_xy(120, y_start)
    
    # 2. ANÁLISE DE RISCO (Threat Score)
    threat = dossier.get("threat")
    if threat:
        score = threat.get("score", 1.0)
        # Cor baseada no risco
        if score >= 8.0: pdf.set_text_color(200, 0, 0)
        elif score >= 5.0: pdf.set_text_color(200, 100, 0)
        else: pdf.set_text_color(0, 100, 0)
        
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(80, 10, f"THREAT SCORE: {score:.1f}/10.0", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "B", 9)
        factors = threat.get("factors", {})
        for f, val in factors.items():
            if isinstance(val, (int, float)) and val != 0:
                pdf.cell(80, 4, _sanitize_text(f" - {f}: {val:+}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif isinstance(val, list) and val:
                pdf.cell(80, 4, _sanitize_text(f" - {f}: {', '.join(map(str, val))}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif val:
                pdf.cell(80, 4, _sanitize_text(f" - {f}: {val}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_xy(10, y_start + 65)

    # 3. LISTA DE CRIMES
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "HISTÓRICO CRIMINAL / ALERTAS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    crimes = dossier.get("crimes_list", [])
    if crimes:
        for c in crimes:
            pdf.cell(0, 5, _sanitize_text(f" - {c.get('crime')} [{c.get('severity', 'N/A')}]"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 5, "Nenhum crime específico catalogado.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(5)

    # 4. CADEIA DE CUSTÓDIA
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, "CADEIA DE CUSTÓDIA E INTEGRIDADE (FASE 16)", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(30, 6, "ID EVIDÊNCIA", border=1)
    pdf.cell(40, 6, "DATA CAPTURA", border=1)
    pdf.cell(120, 6, "HASH SHA-256 (INTEGRIDADE)", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", "", 7)
    for ev in evidences[:5]: # Mostrar as 5 mais recentes
        pdf.cell(30, 5, ev.get("id"), border=1)
        pdf.cell(40, 5, str(ev.get("captured_at")), border=1)
        pdf.cell(120, 5, ev.get("file_hash"), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # 5. DESCRIÇÃO E METADADOS
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "DESCRIÇÃO DETALHADA", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _sanitize_text(dossier.get("description", "Sem descrição adicional disponível no banco de inteligência.")))

    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, _sanitize_text(f"Fonte dos Dados: {dossier.get('source', 'GHOST_CORE')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Salvar
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    
    # Hardening (Fase 22): Encriptação Automática
    if ENCRYPTION_KEY:
        try:
            _encrypt_file(output_path, ENCRYPTION_KEY)
            # Opcional: remover o PDF original não criptografado por segurança
            # os.remove(output_path) 
        except Exception as e:
            log.error(f"Falha no Hardening de Criptografia: {e}")

    return output_path

if __name__ == "__main__":
    # Teste rápido se rodado diretamente
    from intelligence.intelligence_db import DB, get_full_individual_dossier
    db = DB()
    # Pegar o primeiro com score do banco (se houver)
    cur = db.execute("SELECT individual_id FROM threat_scores LIMIT 1")
    row = cur.fetchone()
    if row:
        d = get_full_individual_dossier(db, row[0])
        path = generate_dossier_pdf(d, "intelligence/data/test_dossier.pdf")
        print(f"Dossiê de teste gerado em: {path}")
    db.close()
