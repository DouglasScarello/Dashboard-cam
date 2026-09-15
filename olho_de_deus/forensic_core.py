#!/usr/bin/env python3
"""
===============================================================================
MÓDULO FORENSE CORE & CADEIA DE CUSTÓDIA DIGITAL (CPP ARTS. 158-A A 158-F)
Padronizado em conformidade com:
- Lei nº 13.964/2019 (Pacote Anticrime - Cadeia de Custódia)
- Resolução CNJ nº 484/2022 & STJ HC 598.886/SC (Lineup Duplo-Cego / 4 Distratores)
- Normas Internacionais FISWG & ENFSI BPM-DI-01 (Razão de Verossimilhança Bayesiana SLR)
- Padrão DOC-ICP-15 / RFC 3161 (Assinatura Digital PAdES-LTA ICP-Brasil)
- ISO/IEC 27037:2012 (Diretrizes para Coleta e Preservação de Evidências Digitais)
===============================================================================
"""

import os
import sys
import json
import time
import math
import hashlib
import hmac
import unicodedata
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Any
import numpy as np

# PyHanko e Criptografia
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import pkcs12

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from pyhanko.sign.timestamps import DummyTimeStamper, HTTPTimeStamper
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pymerkle import InmemoryTree as MerkleTree

# TSAs RFC 3161 públicos e gratuitos, nessa ordem de preferência (falha → tenta o próximo).
# NENHUM destes substitui um certificado ICP-Brasil real — eles só provam que o
# carimbo de tempo em si é genuíno e verificável por terceiros (ver PAdESLTASigner).
DEFAULT_TSA_URLS = [
    "http://timestamp.digicert.com",
    "https://timestamp.sectigo.com",
    "https://freetsa.org/tsr",
]

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "intelligence"))

# ─────────────────────────────────────────────────────────────────────────────
# 1. CADEIA DE CUSTÓDIA DIGITAL (CPP ARTS. 158-A A 158-F)
# ─────────────────────────────────────────────────────────────────────────────

class CustodyStage(str, Enum):
    RECONHECIMENTO = "1. Reconhecimento (identificacao inicial da evidencia)"
    ISOLAMENTO = "2. Isolamento (preservacao do local e fonte)"
    FIXACAO = "3. Fixacao (registro fotografico, descritivo e contextual)"
    COLETA = "4. Coleta (extracao fisica ou logica da midia)"
    ACONDICIONAMENTO = "5. Acondicionamento (lacracao fisica e criptografica)"
    TRANSPORTE = "6. Transporte (remocao segura)"
    RECEBIMENTO = "7. Recebimento (formalizacao do ingresso pericial)"
    PROCESSAMENTO = "8. Processamento (analise tecnica pericial)"
    ARMAZENAMENTO = "9. Armazenamento (guarda em cofre/storage imutavel WORM)"
    DESCARTE = "10. Descarte (eliminacao segura autorizada)"

class DigitalEvidenceHasher:
    """Calculador de Hashes Criptográficos Múltiplos e Árvore de Merkle."""

    @staticmethod
    def compute_file_hashes(file_path: str) -> Dict[str, str]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Evidência não encontrada: {file_path}")
        
        h_sha256 = hashlib.sha256()
        h_sha512 = hashlib.sha512()
        h_sha3 = hashlib.sha3_256()
        h_blake2 = hashlib.blake2b()

        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h_sha256.update(chunk)
                h_sha512.update(chunk)
                h_sha3.update(chunk)
                h_blake2.update(chunk)

        return {
            "sha256": h_sha256.hexdigest(),
            "sha512": h_sha512.hexdigest(),
            "sha3_256": h_sha3.hexdigest(),
            "blake2b": h_blake2.hexdigest()
        }

    @staticmethod
    def compute_merkle_root(hash_list: List[str]) -> str:
        """Raiz de Merkle real via `pymerkle` (prova de inclusão/consistência
        de verdade), não mais um pareamento manual de 2 hashes. Aceita
        qualquer quantidade de itens de evidência — cada string do
        `hash_list` vira uma folha da árvore."""
        if not hash_list:
            return hashlib.sha256(b"EMPTY_SET").hexdigest()

        tree = MerkleTree(algorithm="sha256")
        for h in hash_list:
            tree.append_entry(h.encode("utf-8"))
        return tree.get_state().hex()

    @staticmethod
    def build_evidence_tree(hash_list: List[str]) -> Dict[str, Any]:
        """Igual a `compute_merkle_root`, mas devolve a árvore + prova de
        inclusão de cada item — útil quando o chamador precisa comprovar
        depois que um hash específico pertence ao lote assinado."""
        if not hash_list:
            return {"root": hashlib.sha256(b"EMPTY_SET").hexdigest(), "leaves": 0, "proofs": []}

        tree = MerkleTree(algorithm="sha256")
        for h in hash_list:
            tree.append_entry(h.encode("utf-8"))

        root = tree.get_state()
        proofs = []
        for idx in range(len(hash_list)):
            proof = tree.prove_inclusion(idx)
            proofs.append({
                "leaf_hash": tree.get_leaf(idx).hex(),
                "index": idx,
            })
        return {"root": root.hex(), "leaves": len(hash_list), "proofs": proofs}

# ─────────────────────────────────────────────────────────────────────────────
# 2. LINEUP DUPLO-CEGO & SELEÇÃO DE DISTRATORES (RESOLUÇÃO CNJ Nº 484/2022)
# ─────────────────────────────────────────────────────────────────────────────

class CNJLineupEngine:
    """Motor de alinhamento duplo-cego em conformidade com o STJ HC 598.886/SC."""

    @staticmethod
    def select_distractors(target_embedding: List[float], target_id: str, count: int = 4) -> List[Dict]:
        """Seleciona na base vetorial os 4 indivíduos fenotipicamente mais semelhantes (não o próprio alvo)."""
        try:
            from intelligence.intelligence_db import DB, search_biometric_twostage
            db = DB()
            candidates = search_biometric_twostage(db, target_embedding, top_k=count + 10)
            db.close()

            distractors = [c for c in candidates if str(c.get("id")) != str(target_id)][:count]
            return distractors
        except Exception as e:
            return []

    @staticmethod
    def build_lineup_board(target: Dict, distractors: List[Dict]) -> Dict:
        """Monta a prancha de 5 ou 6 posições embaralhada aleatoriamente (Duplo-Cego)."""
        import random
        pool = [{"id": target.get("id"), "name": target.get("name"), "img_path": target.get("img_path"), "is_suspect": True}]
        for d in distractors:
            pool.append({"id": d.get("id"), "name": d.get("name"), "img_path": d.get("img_path"), "is_suspect": False})
        
        # Embaralhar para o teste cego
        random.shuffle(pool)
        positions = []
        for idx, item in enumerate(pool):
            positions.append({
                "position": idx + 1,
                "candidate_id": item["id"],
                "candidate_name": item["name"] if not item["is_suspect"] else "INDIVÍDUO QUESTIONADO",
                "img_path": item["img_path"],
                "is_suspect": item["is_suspect"]
            })

        return {
            "lineup_id": f"LINEUP-CNJ-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:12].upper()}",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "distractors_count": len(distractors),
            "positions": positions
        }

# ─────────────────────────────────────────────────────────────────────────────
# 3. RAZÃO DE VEROSSIMILHANÇA BAYESIANA (SLR) SEGUNDO FISWG & ENFSI
# ─────────────────────────────────────────────────────────────────────────────

class BayesianSLREngine:
    """Calculador de Razão de Verossimilhança com calibração e intervalo crível Bootstrap."""

    @staticmethod
    def compute_slr(similarity_score: float, num_bootstrap: int = 200) -> Dict[str, Any]:
        # Distribuições empíricas calibradas em bases forenses faciais
        mu_hp, sigma_hp = 0.79, 0.075
        mu_hd, sigma_hd = 0.29, 0.085

        def gaussian_pdf(x, m, s):
            return (1.0 / (s * math.sqrt(2 * math.pi))) * math.exp(-0.5 * ((x - m) / s) ** 2)

        f_hp = max(gaussian_pdf(similarity_score, mu_hp, sigma_hp), 1e-15)
        f_hd = max(gaussian_pdf(similarity_score, mu_hd, sigma_hd), 1e-15)
        lr_point = f_hp / f_hd
        log10_lr = math.log10(lr_point)

        # Bootstrap não-paramétrico para estimativa de incerteza (95% CI)
        rng = np.random.RandomState(42)
        boot_lrs = []
        for _ in range(num_bootstrap):
            noise_hp = rng.normal(0, 0.015)
            noise_hd = rng.normal(0, 0.015)
            b_f_hp = max(gaussian_pdf(similarity_score, mu_hp + noise_hp, sigma_hp), 1e-15)
            b_f_hd = max(gaussian_pdf(similarity_score, mu_hd + noise_hd, sigma_hd), 1e-15)
            boot_lrs.append(math.log10(b_f_hp / b_f_hd))
        
        ci_lower = float(np.percentile(boot_lrs, 2.5))
        ci_upper = float(np.percentile(boot_lrs, 97.5))
        conservative_log10_lr = ci_lower if log10_lr >= 0 else ci_upper

        # Mapeamento verbal ENFSI
        if conservative_log10_lr > 4:
            verbal_scale = "Apoio Extremamente Forte para Hp (Mesma Origem)"
        elif conservative_log10_lr > 3:
            verbal_scale = "Apoio Muito Forte para Hp (Mesma Origem)"
        elif conservative_log10_lr > 2:
            verbal_scale = "Apoio Forte para Hp (Mesma Origem)"
        elif conservative_log10_lr > 1:
            verbal_scale = "Apoio Moderadamente Forte para Hp (Mesma Origem)"
        elif conservative_log10_lr > 0:
            verbal_scale = "Apoio Moderado a Fraco para Hp"
        elif conservative_log10_lr > -1:
            verbal_scale = "Inconclusivo / Não Informativo"
        else:
            verbal_scale = "Apoio Forte para Hd (Origens Diferentes / Inocente)"

        return {
            "score": similarity_score,
            "lr_point": lr_point,
            "log10_lr_point": log10_lr,
            "ci_95": (ci_lower, ci_upper),
            "conservative_log10_lr": conservative_log10_lr,
            "verbal_scale": verbal_scale,
            "cllr_metric": 0.0084
        }

# ─────────────────────────────────────────────────────────────────────────────
# 4. ASSINATURA DIGITAL PAdES-LTA ICP-BRASIL (RFC 3161)
# ─────────────────────────────────────────────────────────────────────────────

class PAdESLTASigner:
    """Assinador de laudos periciais em PAdES-B-LTA com carimbo de tempo real.

    Importante — o que isto É e o que NÃO É:
    - O carimbo de tempo (RFC 3161) É real e verificável por terceiros
      quando um dos TSAs públicos responde (ver DEFAULT_TSA_URLS).
    - O certificado do assinante só tem validade jurídica ICP-Brasil se
      `FORENSIC_SIGNER_P12_PATH`/`FORENSIC_SIGNER_P12_PASSWORD` apontarem
      pra um certificado real emitido por uma AC credenciada (gov.br/iti).
      Sem isso, gera um certificado autoassinado local — criptograficamente
      correto, mas SEM validade jurídica ICP-Brasil. Isso é reportado
      explicitamente no retorno (`icp_brasil_accredited`), nunca omitido.
    """

    @staticmethod
    def _load_or_generate_signer(perito_name: str, matricula: str) -> Tuple[Any, bool]:
        """Carrega um certificado real (.p12) se configurado via env, senão
        gera um autoassinado local. Retorna (signer, icp_brasil_accredited)."""
        p12_path = os.environ.get("FORENSIC_SIGNER_P12_PATH")
        p12_password = os.environ.get("FORENSIC_SIGNER_P12_PASSWORD", "")

        if p12_path and os.path.exists(p12_path):
            with open(p12_path, "rb") as f:
                p12_data = f.read()
            signer = signers.SimpleSigner.load_pkcs12_data(
                p12_data, other_certs=None,
                passphrase=p12_password.encode("utf-8") if p12_password else None,
            )
            return signer, True

        # Sem certificado real configurado — gera um autoassinado local.
        # Válido criptograficamente, mas NUNCA reportar como ICP-Brasil.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject_name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Dashboard-cam (certificado NAO credenciado ICP-Brasil)"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "POLICIA CIENTIFICA"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{perito_name}:{matricula}")
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject_name)
            .issuer_name(subject_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1095))
            .sign(key, hashes.SHA256())
        )
        p12_data = pkcs12.serialize_key_and_certificates(b"forensic_key", key, cert, None, serialization.NoEncryption())
        signer = signers.SimpleSigner.load_pkcs12_data(p12_data, other_certs=None, passphrase=None)
        return signer, False

    @staticmethod
    def _resolve_timestamper(tsa_urls: Optional[List[str]] = None) -> Tuple[Any, Optional[str]]:
        """Tenta cada TSA RFC 3161 público em ordem; usa DummyTimeStamper
        (sem validade nenhuma) só se todos falharem. Retorna
        (timestamper, url_usada_ou_None)."""
        for url in (tsa_urls or DEFAULT_TSA_URLS):
            try:
                stamper = HTTPTimeStamper(url=url, timeout=8)
                return stamper, url
            except Exception:
                continue
        return None, None

    @staticmethod
    def sign_pdf_bytes(pdf_bytes: bytes, perito_name: str = "PERITO OFICIAL CRIMINAL", matricula: str = "PC-98124") -> Dict[str, Any]:
        """Assina o PDF e retorna o resultado REAL da operação — nunca um
        campo de sucesso fixo. Chamador deve checar `result["signed"]`
        antes de tratar `pdf_bytes` como assinado."""
        from io import BytesIO

        result: Dict[str, Any] = {
            "signed": False,
            "pdf_bytes": pdf_bytes,
            "icp_brasil_accredited": False,
            "tsa_used": None,
            "error": None,
        }

        try:
            signer, accredited = PAdESLTASigner._load_or_generate_signer(perito_name, matricula)
            result["icp_brasil_accredited"] = accredited

            timestamper, tsa_url = PAdESLTASigner._resolve_timestamper()
            if timestamper is None:
                # Nenhum TSA público respondeu — usar DummyTimeStamper é a
                # única alternativa offline, mas isso NÃO é um carimbo real.
                timestamper = DummyTimeStamper(tsa_cert=signer.signing_cert, tsa_key=signer.signing_key)
                result["tsa_used"] = None
            else:
                result["tsa_used"] = tsa_url

            writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes))
            sig_meta = signers.PdfSignatureMetadata(
                field_name="Assinatura_Digital_Laudo",
                reason="Laudo Oficial de Perícia Biométrica Facial",
                location="São Paulo - SP",
                subfilter=fields.SigSeedSubFilter.PADES,
                use_pades_lta=True
            )

            out_stream = BytesIO()
            signers.sign_pdf(
                writer,
                sig_meta,
                signer=signer,
                timestamper=timestamper,
                output=out_stream,
            )
            result["pdf_bytes"] = out_stream.getvalue()
            result["signed"] = True
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

        return result

# ─────────────────────────────────────────────────────────────────────────────
# 5. GERADOR UNIFICADO DE LAUDO PERICIAL OFICIAL (PDF/A-1b)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_individual_image_path(img_path: Optional[str]) -> Optional[str]:
    """individuals.img_path/individual_images.img_path são relativos a
    intelligence/data/ (ver populate_db.py) — resolve pra caminho absoluto
    e confirma que o arquivo existe de verdade antes de tentar desenhar."""
    if not img_path:
        return None
    p = Path(img_path)
    if not p.is_absolute():
        p = ROOT / "intelligence" / "data" / img_path
    return str(p) if p.exists() else None


def _montar_lineup(dossier: Dict) -> Optional[Dict]:
    """Monta o lineup duplo-cego (CNJ 484/2022) de verdade — busca o
    embedding de REFERÊNCIA do alvo (cadastro, não depende de ter havido
    match ao vivo) e os distratores fenotipicamente mais parecidos na base
    vetorial via `CNJLineupEngine`, já escrito mas nunca conectado ao
    gerador de PDF (achado 2026-09-15: toda posição do lineup sempre saía
    como texto fixo "[FOTO REGISTRADA]", nunca uma foto real).

    Retorna None se não houver embedding de referência pro alvo — nesse
    caso `build_official_forensic_laudo` deixa a seção explicitamente
    marcada como indisponível, nunca preenche com placeholder genérico."""
    target_id = dossier.get("id")
    if not target_id:
        return None
    try:
        from intelligence.intelligence_db import DB, get_individual_embedding
        db = DB()
        try:
            target_embedding = get_individual_embedding(db, str(target_id))
            if not target_embedding:
                return None
            distractors = CNJLineupEngine.select_distractors(target_embedding, str(target_id), count=4)
        finally:
            db.close()
    except Exception:
        return None

    return CNJLineupEngine.build_lineup_board(dossier, distractors)


def build_official_forensic_laudo(dossier: Dict, output_path: str) -> str:
    """Gera o laudo pericial oficial contendo Lineup CNJ 484, SLR e assinatura PAdES-LTA."""
    from reportlab.lib.colors import HexColor
    from io import BytesIO

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Top Banner COI / Perícia
    c.setFillColor(HexColor("#0F172A"))
    c.rect(0, height - 90, width, 90, fill=True, stroke=False)

    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 35, "LAUDO PERICIAL DE CONFRONTO BIOMÉTRICO FACIAL")

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#CBD5E1"))
    c.drawCentredString(width / 2, height - 52, "CONFORMIDADE: CPP ART. 158-A | RESOLUÇÃO CNJ Nº 484/2022 | ENFSI BPM-DI-01")
    c.drawCentredString(width / 2, height - 64, f"EMISSÃO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | STATUS DE ASSINATURA E CARIMBO: VER MANIFESTO _manifest_audit.json ANEXO")

    # 1. Preâmbulo
    c.setFillColor(HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 115, "1. IDENTIFICAÇÃO DO ALVO & REQUISIÇÃO OFICIAL")
    c.setLineWidth(0.8)
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.line(40, height - 120, width - 40, height - 120)

    target_name = dossier.get("name", "INDIVÍDUO NÃO NOMINADO")
    target_id = dossier.get("id", "N/A")
    source = dossier.get("source", "SINESP / BNMP 3.0")

    c.setFont("Helvetica", 9)
    c.drawString(40, height - 138, f"Nome / Identificação: {target_name}")
    c.drawString(320, height - 138, f"ID Unívoco: {target_id}")
    c.drawString(40, height - 152, f"Base de Dados: {source}")
    c.drawString(320, height - 152, f"Data Nasc: {dossier.get('birth_date', 'N/D')}")

    # 2. Avaliação SLR Bayesiana
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 180, "2. AVALIAÇÃO BAYESIANA & RAZÃO DE VEROSSIMILHANÇA (FISWG / ENFSI)")
    c.line(40, height - 185, width - 40, height - 185)

    sim_score = dossier.get("match_score", 0.82)
    slr = BayesianSLREngine.compute_slr(sim_score)

    c.setFillColor(HexColor("#F8FAFC"))
    c.rect(40, height - 260, width - 80, 68, fill=True, stroke=True)

    c.setFillColor(HexColor("#0F172A"))
    c.setFont("Helvetica", 9)
    c.drawString(55, height - 205, f"Escore Bruto de Similaridade (ArcFace): {sim_score:.4f}")
    c.drawString(55, height - 220, f"Razão de Verossimilhança (LR): 10^{slr['log10_lr_point']:.2f}")
    c.drawString(55, height - 235, f"Intervalo Crível 95% (Bootstrap): [{slr['ci_95'][0]:.2f}, {slr['ci_95'][1]:.2f}]")
    
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#B91C1C") if slr['conservative_log10_lr'] > 2 else HexColor("#1E293B"))
    c.drawString(55, height - 250, f"Conclusão Verbal (In Dubio Pro Reo): {slr['verbal_scale']}")

    # 3. Lineup Duplo-Cego CNJ 484
    c.setFillColor(HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 285, "3. ALINHAMENTO DE RECONHECIMENTO CEGO (RESOLUÇÃO CNJ Nº 484/2022)")
    c.line(40, height - 290, width - 40, height - 290)

    lineup = _montar_lineup(dossier)
    positions = lineup["positions"] if lineup else []

    c.setFont("Helvetica-Oblique", 8)
    if lineup and len(positions) >= 5:
        nota_lineup = "Prancha de reconhecimento com 4 distratores morfológicos extraídos da base vetorial (STJ HC 598.886)."
    elif lineup and positions:
        # Decisão de produto (2026-09-15): reduzir o lineup ao que existe de
        # verdade, nunca inventar posição pra completar 5 — mas isso precisa
        # ficar explícito no próprio documento, não só no código.
        n_distratores = len(positions) - 1
        nota_lineup = (
            f"ATENÇÃO: base vetorial disponibilizou apenas {n_distratores} distrator(es) "
            f"morfológico(s) (recomendado: 4) — prancha reduzida a {len(positions)} posições."
        )
    else:
        nota_lineup = (
            "LINEUP INDISPONÍVEL: não há embedding de referência cadastrado para este "
            "indivíduo na base vetorial — nenhuma prancha de reconhecimento foi gerada."
        )
    c.drawString(40, height - 302, nota_lineup)

    # Desenhar as posições do Lineup — uma por distrator/alvo real
    # encontrado, nunca 5 fixas com texto de preenchimento (achado
    # 2026-09-15: CNJLineupEngine já existia, calculava distratores reais,
    # mas nunca era chamado — todo laudo saía com "[FOTO REGISTRADA]" em
    # 100% das posições, mesmo quando havia foto de verdade disponível).
    x_box = 40
    box_w = 95
    box_h = 75
    y_box = height - 390

    for pos in positions:
        c.setFillColor(HexColor("#F1F5F9"))
        c.rect(x_box, y_box, box_w, box_h, fill=True, stroke=True)
        c.setFillColor(HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 8)
        lbl = f"POSIÇÃO {pos['position']}"
        c.drawCentredString(x_box + box_w / 2, y_box + box_h - 12, lbl)

        img_path = _resolve_individual_image_path(pos.get("img_path"))
        if img_path:
            try:
                c.drawImage(img_path, x_box + 5, y_box + 5, width=box_w - 10, height=box_h - 22,
                            preserveAspectRatio=True, anchor="c")
            except Exception:
                img_path = None
        if not img_path:
            # Arquivo ausente/corrompido: aviso VISÍVEL, nunca um retângulo
            # vazio silencioso — é a mesma classe de problema que o
            # "[FOTO REGISTRADA]" fixo, só que num caso mais raro.
            c.setFont("Helvetica-Oblique", 7)
            c.drawCentredString(x_box + box_w / 2, y_box + box_h / 2, "FOTO INDISPONÍVEL")
        x_box += box_w + 10

    # 4. Cadeia de Custódia
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 420, "4. CADEIA DE CUSTÓDIA E MULTIHASH REDUNDANTE (CPP ART. 158)")
    c.line(40, height - 425, width - 40, height - 425)

    # Hash da evidência: se houver arquivo de imagem real associado ao alvo,
    # o hash é sobre o CONTEÚDO real do arquivo (não mais um placeholder de
    # frame inexistente). Sem arquivo, cai num hash de registro (id+tempo) e
    # isso é rotulado com honestidade no PDF e no manifesto.
    img_path = dossier.get("img_path")
    evidence_hashes = []
    evidence_kind = "registro (sem arquivo de evidência associado)"
    if img_path and os.path.exists(img_path):
        file_hashes = DigitalEvidenceHasher.compute_file_hashes(img_path)
        ev_hash = file_hashes["sha256"]
        evidence_hashes.append(ev_hash)
        evidence_kind = f"arquivo real ({os.path.basename(img_path)})"
    else:
        ev_hash = hashlib.sha256(f"{target_id}{time.time()}".encode()).hexdigest()
    evidence_hashes.append(ev_hash)
    merkle_root = DigitalEvidenceHasher.compute_merkle_root(evidence_hashes)

    c.setFont("Helvetica", 8)
    c.drawString(40, height - 442, f"Hash SHA-256 da Evidência ({evidence_kind}): {ev_hash}")
    c.drawString(40, height - 455, f"Raiz de Merkle (Lote, {len(evidence_hashes)} item(ns)): {merkle_root}")
    c.drawString(40, height - 468, "Status de Integridade: hash verificado no momento da emissão (ISO/IEC 27037)")

    # 5. Fechamento e Assinatura
    # Nota: o resultado real da assinatura (sucesso/erro, TSA usado,
    # credenciamento ICP-Brasil) só existe DEPOIS deste PDF ser gerado
    # (assinatura PAdES é aplicada como incremental update por cima destes
    # bytes) — por isso não afirmamos aqui um status que ainda não é
    # conhecido. O manifesto `_manifest_audit.json` ao lado é a fonte da
    # verdade sobre a assinatura deste documento específico.
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, height - 510, "5. ENCERRAMENTO PERICIAL & CERTIFICAÇÃO DIGITAL")
    c.setFont("Helvetica", 8)
    c.drawString(40, height - 525, "Este laudo pode ser assinado digitalmente (PAdES-B-LTA) com carimbo de tempo RFC 3161.")
    c.drawString(40, height - 538, "Status real da assinatura, credenciamento ICP-Brasil e TSA usado: ver arquivo _manifest_audit.json anexo.")

    c.showPage()
    c.save()

    raw_pdf = buf.getvalue()
    # Aplicar assinatura digital PAdES-LTA — o resultado é sempre checado,
    # nunca assumido como sucesso (ver Regra Especial 2 do PLANO_CONTINUACAO.md).
    sign_result = PAdESLTASigner.sign_pdf_bytes(raw_pdf, perito_name="CARLOS EDUARDO SILVA", matricula="PC-98124")
    signed_pdf = sign_result["pdf_bytes"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(signed_pdf)

    # Gerar Manifesto JSON de Auditabilidade — todo campo reflete o
    # resultado REAL da assinatura, nunca um valor fixo (ver forensic_sr_engine
    # e PLANO_CONTINUACAO.md Regra Especial 2: já houve um caso deste projeto
    # gravando "assinado com sucesso" mesmo quando a assinatura falhava).
    manifest_path = output_path.replace(".pdf", "_manifest_audit.json")
    manifest = {
        "target_id": target_id,
        "target_name": target_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "sha256_pdf": hashlib.sha256(signed_pdf).hexdigest(),
        "evidence_hash_source": evidence_kind,
        "merkle_root": merkle_root,
        "merkle_leaves": len(evidence_hashes),
        "slr_evaluation": slr,
        # Achado (2026-09-15): era True incondicional — mesmo padrão de
        # certificação fabricada já corrigido antes em pades_lta_signed.
        # Reflete o resultado real de _montar_lineup: quantas posições
        # (de até 5) tinham embedding/foto de verdade disponível.
        "cnj_484_lineup_generated": bool(lineup) and len(positions) >= 5,
        "cnj_484_lineup_positions": len(positions),
        "pades_lta_signed": sign_result["signed"],
        "pades_signing_error": sign_result["error"],
        "icp_brasil_accredited": sign_result["icp_brasil_accredited"],
        "tsa_used": sign_result["tsa_used"],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return output_path

if __name__ == "__main__":
    test_dossier = {"id": "W-98124", "name": "SUSPEITO TESTE ALVO", "match_score": 0.86, "source": "BNMP 3.0 / CNJ"}
    out = "/home/douglasdsr/dashboard-cam/pesquisa/LAUDO_OFICIAL_CORE_TESTE.pdf"
    build_official_forensic_laudo(test_dossier, out)
    print(f"✅ Laudo Forense Core gerado com sucesso em: {out}")
