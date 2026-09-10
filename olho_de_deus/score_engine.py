#!/usr/bin/env python3
"""
score_engine.py — Olho de Deus [Fase 12: Threat Scoring Engine]

Algoritmo de cálculo dinâmico de periculosidade.
Analisa crimes, descrições e recompensas para atribuir um score de 1.0 a 10.0.
"""

import os
import sys
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from intelligence_db import DB, upsert_threat_score

log = logging.getLogger("score_engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Tabela de Pesos por Categoria de Crime (Keywords)
WEIGHTS = {
    "TERRORISM": 1.0,
    "MURDER": 1.0,
    "HOMICIDIO": 1.0,
    "LATROCINIO": 1.0,
    # "HOMICIDE"/"HOMICIDES" (inglês, sem acento) — achado em 2026-09-10:
    # a categoria real da FBI "ViCAP Homicides and Sexual Assaults" (38
    # indivíduos, incluindo casos de homicídio de verdade) tirava nota 1.0
    # (a mínima, igual a "desaparecido sem nenhum crime") porque "HOMICIDIO"
    # (português) nunca batia com "HOMICIDES" (inglês) — são grafias
    # diferentes, não é a mesma palavra em maiúscula/minúscula.
    "HOMICIDE": 1.0,
    "RAPE": 0.9,
    "ESTUPRO": 0.9,
    "SEXUAL ASSAULT": 0.9,
    "KIDNAPPING": 0.9,
    "SEQUESTRO": 0.9,
    "HUMAN TRAFFICKING": 0.9,
    "CRIMES AGAINST CHILDREN": 0.9,
    "ENDANGERED CHILD": 0.8,
    # "ECAP" = sigla da FBI pro mesmo programa "Endangered Child Alert
    # Program" acima — achado logo depois da correção de HOMICIDE/CHILDREN
    # (mesma classe de bug): a categoria vem gravada abreviada em 10 dos 13
    # casos no banco, então "ENDANGERED CHILD" sozinho não cobria. Um deles
    # (JOHN DOE 5) tem descrição explícita de abuso infantil e tirava 1.0.
    "ECAP": 0.8,

    "ADDITIONAL VIOLENT CRIMES": 0.8,
    "DRUGS": 0.8,
    "TRAFICO": 0.8,
    "NARCOTICS": 0.8,
    "ROBBERY": 0.7,
    "ROUBO": 0.7,
    "FRAUD": 0.5,
    "ESTELIONATO": 0.5,
    "MONEY LAUNDERING": 0.5,
    "LAVAGEM": 0.5,
    "THEFT": 0.4,
    "FURTO": 0.4,
}

class ThreatScorer:
    def __init__(self, db: DB):
        self.db = db

    def calculate_individual_score(self, individual_id: str) -> float:
        """Calcula o score de um indivíduo baseado em seus dados e crimes."""
        # 1. Buscar dados do indivíduo
        q_ind = "SELECT description, reward FROM individuals WHERE id = ?"
        cur = self.db.execute(q_ind, (individual_id,))
        ind = cur.fetchone()
        if not ind:
            return 1.0

        # 2. Buscar crimes associados
        q_crimes = "SELECT crime FROM crimes WHERE individual_id = ?"
        cur = self.db.execute(q_crimes, (individual_id,))
        crimes = [row["crime"] for row in cur.fetchall()]

        score = 1.0
        factors = {
            "max_crime_weight": 0.0,
            "reward_bonus": 0.0,
            "armed_and_dangerous": False,
            "keywords_found": []
        }

        # Análise de Crimes
        max_weight = 0.1
        crime_text = " ".join(crimes).upper()
        # Adiciona a descrição (agora inclui caution/warning_message/remarks — ver populate_db.py)
        full_context = (crime_text + " " + (ind["description"] or "").upper())

        for kw, weight in WEIGHTS.items():
            if kw in full_context:
                factors["keywords_found"].append(kw)
                if weight > max_weight:
                    max_weight = weight

        factors["max_crime_weight"] = max_weight
        score = max_weight * 10.0

        # "ARMED AND DANGEROUS" é um selo oficial da fonte (FBI warning_message), não uma
        # palavra-chave genérica de crime — pesa mais que qualquer keyword de WEIGHTS e
        # estabelece um piso alto de score, já que é literalmente um aviso de risco físico.
        if "ARMED AND DANGEROUS" in full_context or "CONSIDERED DANGEROUS" in full_context:
            factors["armed_and_dangerous"] = True
            score = max(score, 9.0)

        # Análise de Recompensa
        reward_str = ind["reward"]
        if reward_str:
            # Extrair números da string de recompensa (ex: "$1,000,000" -> 1000000)
            nums = re.findall(r'\d+', reward_str.replace(",", "").replace(".", ""))
            if nums:
                val = int("".join(nums))
                # Bônus logarítmico (ex: 10k -> +0.5, 100k -> +1.0, 1M -> +1.5, 10M -> +2.0)
                import math
                if val > 1000:
                    bonus = min(2.0, math.log10(val/1000) * 0.5)
                    factors["reward_bonus"] = round(bonus, 2)
                    score += bonus

        final_score = min(10.0, max(1.0, round(score, 1)))
        
        # Persistir no banco
        upsert_threat_score(self.db, individual_id, final_score, factors)
        return final_score

    def batch_process(self):
        """Processa todos os indivíduos que ainda não têm score."""
        log.info("Iniciando processamento em lote de scores...")
        q = """
        SELECT i.id FROM individuals i 
        LEFT JOIN threat_scores t ON i.id = t.individual_id 
        WHERE t.individual_id IS NULL
        """
        cur = self.db.execute(q)
        to_process = [row["id"] for row in cur.fetchall()]
        
        log.info(f"Encontrados {len(to_process)} indivíduos para pontuar.")
        
        count = 0
        for uid in to_process:
            self.calculate_individual_score(uid)
            count += 1
            if count % 100 == 0:
                log.info(f"Processados {count}/{len(to_process)}...")

        log.info(f"Processamento concluído. {count} scores gerados/atualizados.")

if __name__ == "__main__":
    from intelligence_db import init_db
    init_db()
    db = DB()
    scorer = ThreatScorer(db)
    scorer.batch_process()
    db.close()

