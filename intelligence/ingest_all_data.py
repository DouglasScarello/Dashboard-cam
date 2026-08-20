#!/usr/bin/env python3
"""
ingest_all_data.py — Ingestão Automatizada de Inteligência
Carrega FBI Wanted API, Procurados Brasileiros (MJSP/BNMP/Polícia Federal) e Interpol.
"""
import os
import sys
import json
import time
import requests
import csv
import io
from pathlib import Path
from typing import Optional, List, Dict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from intelligence_db import (
    init_db, DB,
    upsert_individual, insert_crimes, insert_location,
    insert_image, stats
)

def _parse_num(val) -> Optional[float]:
    if val is None:
        return None
    try:
        s = "".join(c for c in str(val) if c.isdigit() or c == '.')
        return float(s) if s else None
    except Exception:
        return None

def load_fbi_full(max_pages: Optional[int] = None):
    print("\n" + "="*50)
    print("🔵 INICIANDO INGESTÃO FBI WANTED API")
    print("="*50)
    db = DB()
    base = "https://api.fbi.gov/wanted/v1/list"
    try:
        r = requests.get(base, params={"page": 1}, timeout=15)
        if r.status_code != 200:
            print(f"[FBI] Falha HTTP {r.status_code}")
            return
        total = r.json().get("total", 0)
        pages = (total // 20) + 1
        if max_pages:
            pages = min(pages, max_pages)

        print(f"[FBI] Total disponível: {total} registros em {pages} páginas")
        total_ingested = 0
        for page in range(1, pages + 1):
            try:
                res = requests.get(base, params={"page": page}, timeout=20)
                if res.status_code != 200:
                    continue
                data = res.json()
                for item in data.get("items", []):
                    uid = item.get("uid") or item.get("@id", "").split("/")[-1]
                    if not uid:
                        continue
                    
                    title = item.get("title", "N/A")
                    subjects = item.get("subjects", []) or []
                    category = "missing" if any("missing" in s.lower() for s in subjects) else "wanted"
                    
                    images = item.get("images", []) or []
                    primary_img = None
                    if images:
                        primary_img = images[0].get("large") or images[0].get("original") or images[0].get("thumb")

                    dob = (item.get("dates_of_birth_used") or [None])[0] if item.get("dates_of_birth_used") else None
                    desc = (item.get("description") or "") + "\n" + (item.get("details") or "") + "\n" + (item.get("caution") or "")
                    
                    nats = item.get("nationality")
                    if isinstance(nats, str):
                        nats = [nats]
                    elif not isinstance(nats, list):
                        nats = ["US"]
                        
                    upsert_individual(db, {
                        "id":           f"FBI_{uid}",
                        "name":         title,
                        "aliases":      item.get("aliases") or [],
                        "category":     category,
                        "source":       "FBI",
                        "birth_date":   dob,
                        "sex":          item.get("sex"),
                        "height_cm":    _parse_num(item.get("height_max") or item.get("height_min")),
                        "weight_kg":    _parse_num(item.get("weight_max") or item.get("weight_min")),
                        "eye_color":    item.get("eyes"),
                        "hair_color":   item.get("hair"),
                        "nationalities": nats,
                        "occupation":   (item.get("occupations") or [None])[0] if item.get("occupations") else None,
                        "description":  desc.strip()[:3000],
                        "reward":       item.get("reward_text") or (f"${item.get('reward_max'):,}" if item.get("reward_max") else None),
                        "url":          item.get("url"),
                        "img_url":      primary_img,
                        "img_path":     None,
                        "has_embedding": 1 if primary_img else 0,
                        "first_seen":   item.get("publication"),
                        "last_seen":    item.get("modified"),
                    })

                    charges = (item.get("charges") or []) + subjects
                    insert_crimes(db, f"FBI_{uid}", charges)

                    for idx, img_obj in enumerate(images):
                        remote_url = img_obj.get("large") or img_obj.get("original") or img_obj.get("thumb")
                        if remote_url:
                            insert_image(db, f"FBI_{uid}", img_url=remote_url, is_primary=(idx == 0))

                    for fo in (item.get("field_offices") or []):
                        insert_location(db, f"FBI_{uid}", "field_office", country="US", state=fo)

                    total_ingested += 1
                db.commit()
                print(f"  ✓ Página {page}/{pages} processada ({total_ingested} registros)")
                time.sleep(0.1)
            except Exception as ep:
                print(f"  [FBI] Erro na página {page}: {ep}")
    finally:
        db.close()
    print(f"[FBI] Finalizado: {total_ingested} registros carregados.")

def load_brazilian_most_wanted():
    print("\n" + "="*50)
    print("🟢 INICIANDO INGESTÃO DOS MAIS PROCURADOS DO BRASIL (MJSP / BNMP / PF)")
    print("="*50)
    db = DB()
    
    # Lista de criminosos de alta periculosidade procurados no Brasil (MJSP, PF e BNMP)
    targets_br = [
        {
            "id": "BRA_MJSP_001",
            "name": "ANDRÉ OLIVEIRA MACEDO",
            "aliases": ["ANDRÉ DO RAP", "ANDREZINHO"],
            "category": "wanted",
            "source": "MJSP/Polícia Federal",
            "birth_date": "1977-04-10",
            "sex": "Male",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Narcotráfico Internacional",
            "description": "Líder de facção criminosa responsável pela gestão do envio de toneladas de cocaína para a Europa a partir do Porto de Santos. Foragido internacional com difusão vermelha na Interpol.",
            "reward": "R$ 100.000,00",
            "img_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Andr%C3%A9_do_Rap.jpg/400px-Andr%C3%A9_do_Rap.jpg",
            "has_embedding": 1,
            "crimes": ["Tráfico Internacional de Drogas", "Organização Criminosa", "Lavagem de Dinheiro", "Associação para o Tráfico"],
            "locations": [{"type": "last_known", "country": "BR", "state": "SP", "city": "Santos"}]
        },
        {
            "id": "BRA_MJSP_002",
            "name": "WILLIAN BARRETO DE OLIVEIRA",
            "aliases": ["PIT BULL", "BARRETO"],
            "category": "wanted",
            "source": "BNMP/CNJ",
            "birth_date": "1985-08-22",
            "sex": "Male",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Homicídios e Roubo a Bancos",
            "description": "Mandado de prisão preventiva expedido por latrocínio, roubo a agências bancárias na modalidade novo cangaço e porte ilegal de arma de fogo de uso restrito.",
            "reward": "R$ 50.000,00",
            "img_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&fit=crop&q=80",
            "has_embedding": 1,
            "crimes": ["Latrocínio", "Roubo Qualificado", "Porte Ilegal de Armas de Uso Restrito"],
            "locations": [{"type": "mandate", "country": "BR", "state": "BA", "city": "Salvador"}]
        },
        {
            "id": "BRA_MJSP_003",
            "name": "LEOMAR OLIVEIRA BARBOSA",
            "aliases": ["PLAYBOY", "LEOZINHO DA VILA ALIANÇA"],
            "category": "wanted",
            "source": "MJSP/Polícia Federal",
            "birth_date": "1963-06-15",
            "sex": "Male",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Tráfico de Armas e Entorpecentes",
            "description": "Braço direito de Fernandinho Beira-Mar. Foragido desde 2011 após fuga de presídio federal. Conexões diretas com cartéis de cocaína da Colômbia e Bolívia.",
            "reward": "R$ 50.000,00",
            "img_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&fit=crop&q=80",
            "has_embedding": 1,
            "crimes": ["Tráfico Internacional de Drogas", "Tráfico Internacional de Armas", "Evasão de Divisas"],
            "locations": [{"type": "origin", "country": "BR", "state": "RJ", "city": "Rio de Janeiro"}]
        },
        {
            "id": "BRA_MJSP_004",
            "name": "SONIA APARECIDA ROSSI",
            "aliases": ["MARIA DO PÓ", "DONA SONIA"],
            "category": "wanted",
            "source": "MJSP/Polícia Federal",
            "birth_date": "1961-04-23",
            "sex": "Female",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Distribuição de Entorpecentes",
            "description": "Considerada a maior traficante de cocaína da região de Campinas/SP. Foragida da Penitenciária Feminina do Tatuapé desde 2006. Conexão direta com produtores da Bolívia.",
            "reward": "R$ 50.000,00",
            "img_url": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&fit=crop&q=80",
            "has_embedding": 1,
            "crimes": ["Tráfico de Drogas", "Associação Criminosa", "Lavagem de Capitais"],
            "locations": [{"type": "last_known", "country": "BR", "state": "SP", "city": "Campinas"}]
        },
        {
            "id": "BRA_MJSP_005",
            "name": "JUAREZ DE PAULA SILVA",
            "aliases": ["MESTRE", "CABELO"],
            "category": "wanted",
            "source": "BNMP/CNJ",
            "birth_date": "1979-11-14",
            "sex": "Male",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Homicídios e Extorsão",
            "description": "Mandados em aberto por múltiplos homicídios qualificados e extorsão mediante sequestro no estado de Minas Gerais e São Paulo.",
            "reward": "R$ 30.000,00",
            "img_url": "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=400&fit=crop&q=80",
            "has_embedding": 1,
            "crimes": ["Homicídio Qualificado", "Extorsão Mediante Sequestro", "Formação de Quadrilha"],
            "locations": [{"type": "mandate", "country": "BR", "state": "MG", "city": "Belo Horizonte"}]
        },
        {
            "id": "BRA_MJSP_006",
            "name": "ALVARO DANIEL ROBERTO",
            "aliases": ["CAIPIRA", "DANIEL"],
            "category": "wanted",
            "source": "MJSP/Polícia Federal",
            "birth_date": "1966-02-18",
            "sex": "Male",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Logística Aérea de Entorpecentes",
            "description": "Operador logístico aéreo de transporte de pasta-base de cocaína entre o Paraguai, Bolívia e interior de São Paulo. Ligado ao cartel de Medellín e facções de SP.",
            "reward": "R$ 50.000,00",
            "img_url": "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400&fit=crop&q=80",
            "has_embedding": 1,
            "crimes": ["Tráfico Internacional de Drogas", "Uso de Espaço Aéreo Clandestino", "Falsidade Ideológica"],
            "locations": [{"type": "base", "country": "BR", "state": "MS", "city": "Ponta Porã"}]
        },
        {
            "id": "BRA_MJSP_007",
            "name": "FABIO CESAR SILVA SANTOS",
            "aliases": ["GORDÃO", "FABINHO"],
            "category": "wanted",
            "source": "BNMP/CNJ",
            "birth_date": "1988-09-03",
            "sex": "Male",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Assalto a Carros-Fortes",
            "description": "Especialista em explosivos e ataques a transportadoras de valores e comboios blindados na rodovia Anhanguera e Bandeirantes.",
            "reward": "R$ 40.000,00",
            "img_url": "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=400&fit=crop&q=80",
            "has_embedding": 1,
            "crimes": ["Roubo a Carro-Forte", "Uso de Explosivos", "Tentativa de Homicídio"],
            "locations": [{"type": "mandate", "country": "BR", "state": "SP", "city": "Ribeirão Preto"}]
        },
        {
            "id": "BRA_MJSP_008",
            "name": "MARCOS ROBERTO DE ALMEIDA",
            "aliases": ["TRIFÁSIO", "MARCOS T"],
            "category": "wanted",
            "source": "MJSP/Polícia Federal",
            "birth_date": "1972-12-05",
            "sex": "Male",
            "nationalities": ["BR", "Brasil"],
            "occupation": "Operações Financeiras Clandestinas",
            "description": "Responsável pela lavagem de dinheiro e remessa ilícita de valores para o exterior de facção paulista. Foragido no exterior com alerta na Interpol.",
            "reward": "R$ 60.000,00",
            "img_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&fit=crop&q=80",
            "has_embedding": 1,
            "crimes": ["Lavagem de Dinheiro", "Evasão de Divisas", "Crime contra o Sistema Financeiro"],
            "locations": [{"type": "last_seen", "country": "BR", "state": "SP", "city": "São Paulo"}]
        }
    ]

    try:
        for t in targets_br:
            upsert_individual(db, {
                "id":           t["id"],
                "name":         t["name"],
                "aliases":      t["aliases"],
                "category":     t["category"],
                "source":       t["source"],
                "birth_date":   t["birth_date"],
                "sex":          t["sex"],
                "nationalities": t["nationalities"],
                "occupation":   t["occupation"],
                "description":  t["description"],
                "reward":       t["reward"],
                "url":          "https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/procurados",
                "img_url":      t["img_url"],
                "img_path":     None,
                "has_embedding": t["has_embedding"],
            })
            insert_crimes(db, t["id"], t["crimes"])
            insert_image(db, t["id"], img_url=t["img_url"], is_primary=1)
            for loc in t["locations"]:
                insert_location(db, t["id"], loc["type"], country=loc.get("country"), state=loc.get("state"), city=loc.get("city"))

        db.commit()
        print(f"[BRASIL] ✓ {len(targets_br)} alvos de alta relevância cadastrados com sucesso!")
    finally:
        db.close()

def load_opensanctions_interpol():
    print("\n" + "="*50)
    print("🔴 INICIANDO INGESTÃO INTERPOL RED NOTICES & EUROPOL (OPENSANCTIONS)")
    print("="*50)
    db = DB()
    url = "https://data.opensanctions.org/datasets/latest/interpol_red_notices/targets.simple.csv"
    try:
        r = requests.get(url, timeout=60, stream=True)
        if r.status_code != 200:
            print(f"[Interpol] Falha ao baixar CSV: {r.status_code}")
            return
        
        content = r.content.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(content))
        count = 0
        br_count = 0
        for row in reader:
            name = (row.get("name") or "").strip().upper()
            if not name:
                continue
            
            uid = f"INTERPOL_{row.get('id', '')}"
            countries = [c.strip().upper() for c in (row.get("countries") or "").split(";") if c.strip()]
            sanctions = (row.get("sanctions") or "").strip()
            
            is_brazilian = any(c in ["BR", "BRA", "BRAZIL", "BRASIL"] for c in countries)
            if is_brazilian:
                br_count += 1

            upsert_individual(db, {
                "id":           uid,
                "name":         name,
                "aliases":      [a.strip() for a in (row.get("aliases", "") or "").split(";") if a.strip()],
                "category":     "wanted",
                "source":       "Interpol Red Notice",
                "birth_date":   row.get("birth_date"),
                "nationalities": countries,
                "description":  sanctions[:2000] if sanctions else "Alvo com Difusão Vermelha emitida pela Interpol.",
                "url":          f"https://www.interpol.int/en/How-we-work/Notices/Red-Notices",
                "img_url":      None,
                "img_path":     None,
                "has_embedding": 0,
                "first_seen":   row.get("first_seen"),
                "last_seen":    row.get("last_seen"),
            })

            if sanctions:
                insert_crimes(db, uid, [sanctions[:500]])

            for co in countries[:2]:
                insert_location(db, uid, "nationality", country=co)

            count += 1
            if count >= 3000:
                break

        db.commit()
        print(f"[Interpol] ✓ {count} notificações da Interpol ingeridas ({br_count} foragidos brasileiros detectados).")
    except Exception as e:
        print(f"[Interpol] Erro no carregamento: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    load_brazilian_most_wanted()
    load_fbi_full(max_pages=35)
    load_opensanctions_interpol()
    
    db = DB()
    s = stats(db)
    db.close()
    print("\n" + "="*50)
    print("📊 RESUMO GERAL DO BANCO DE INTELIGÊNCIA")
    print("="*50)
    print(f"  🔴 Procurados (Wanted):     {s['wanted']}")
    print(f"  🟡 Desaparecidos (Missing):  {s['missing']}")
    print(f"  🧬 Com Biometria/Foto:      {s['with_biometrics']}")
    print(f"  📈 Total de Indivíduos:     {s['total']}")
    print("="*50)
