#!/usr/bin/env python3
"""
plate_matching.py — Olho de Deus

Comparação de placa TOLERANTE a erro de OCR — pesquisado em 2026-09-12
depois de reparar, testando ao vivo (câmera de Davao, Filipinas), que o
mesmo veículo real às vezes lê "LAB3631" e às vezes "ILAB3631" (um "I"
sobrando no início). Uma busca por igualdade exata de texto NUNCA
reconheceria isso como o mesmo carro.

Duas técnicas reais combinadas (não inventadas — ver pesquisa):
  1. Distância de edição (Levenshtein) generalizada — cobre inserção/
     remoção de caractere (exatamente o nosso padrão de erro observado),
     técnica padrão da indústria de ANPR/fuzzy matching.
  2. Custo de substituição ponderado por confusão visual de caractere
     (0↔O, 1↔I, 8↔B, 2↔Z, 5↔S) — mesma ideia da "P-table" descrita na
     patente US8798325B2 (Xerox, "Efficient and fault tolerant license
     plate matching method"): trocar "0" por "O" é um erro muito mais
     plausível de OCR do que trocar "0" por "K", então deve pesar menos
     na distância.
"""
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

# Pares de caractere que sistemas reais de ANPR documentam como as
# confusões de OCR mais comuns (formato visual parecido). Substituir
# um pelo outro custa CONFUSION_COST em vez do custo cheio de 1.0.
_CONFUSABLE_PAIRS = [
    ("0", "O"), ("0", "D"), ("0", "Q"),
    ("1", "I"), ("1", "L"), ("1", "T"),
    ("8", "B"),
    ("2", "Z"),
    ("5", "S"),
    ("6", "G"),
]
CONFUSION_COST = 0.3   # substituição entre par confundível
SUBSTITUTION_COST = 1.0
INDEL_COST = 1.0       # inserir/remover 1 caractere — cobre "I" ou "1" sobrando


def _build_confusion_set() -> Dict[str, set]:
    table: Dict[str, set] = {}
    for a, b in _CONFUSABLE_PAIRS:
        table.setdefault(a, set()).add(b)
        table.setdefault(b, set()).add(a)
    return table


_CONFUSION_TABLE = _build_confusion_set()


def _sub_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if b in _CONFUSION_TABLE.get(a, ()):
        return CONFUSION_COST
    return SUBSTITUTION_COST


@lru_cache(maxsize=4096)
def weighted_edit_distance(a: str, b: str) -> float:
    """Levenshtein generalizado com custo de substituição ponderado por
    confusão visual. Cacheado — a mesma comparação se repete muito ao
    varrer o histórico de veículos."""
    n, m = len(a), len(b)
    if n == 0:
        return m * INDEL_COST
    if m == 0:
        return n * INDEL_COST

    prev = [j * INDEL_COST for j in range(m + 1)]
    for i in range(1, n + 1):
        curr = [i * INDEL_COST] + [0.0] * m
        for j in range(1, m + 1):
            cost_sub = prev[j - 1] + _sub_cost(a[i - 1], b[j - 1])
            cost_del = prev[j] + INDEL_COST
            cost_ins = curr[j - 1] + INDEL_COST
            curr[j] = min(cost_sub, cost_del, cost_ins)
        prev = curr
    return prev[m]


def similarity(a: str, b: str) -> float:
    """0..1, 1 = idêntico. Normaliza pela placa mais longa — duas placas
    de tamanho muito diferente nunca vão bater bem, o que é o comportamento
    certo (não confundir "LAB3631" com "AB363", só com "ILAB3631")."""
    if not a or not b:
        return 0.0
    longest = max(len(a), len(b))
    dist = weighted_edit_distance(a.upper(), b.upper())
    return max(0.0, 1.0 - dist / longest)


def find_best_match(candidate: str, known_plates: List[str],
                     threshold: float = 0.75) -> Optional[Tuple[str, float]]:
    """Compara `candidate` contra uma lista de placas já conhecidas
    (histórico) e devolve a melhor batida acima do limiar, ou None.
    threshold=0.75 é conservador de propósito — abaixo disso o risco de
    juntar dois veículos DIFERENTES como se fossem o mesmo cresce rápido
    (ver achado da pesquisa: heurística comum na indústria é tolerar
    ~1 erro a cada 5 caracteres, que pra uma placa de 7 chars é ~0.85)."""
    best_plate, best_score = None, 0.0
    for known in known_plates:
        score = similarity(candidate, known)
        if score > best_score:
            best_plate, best_score = known, score
    if best_plate is not None and best_score >= threshold:
        return best_plate, best_score
    return None


if __name__ == "__main__":
    # Sanity check com os erros REAIS observados testando a câmera de Davao.
    cases = [
        ("LAB3631", "ILAB3631"),   # "I" sobrando no início
        ("KBB5852", "KBB15852"),   # "1" sobrando no meio
        ("LAL5967", "LAL5967"),    # idêntico
        ("LAN9936", "LAP4401"),    # veículos DIFERENTES — não deve bater
    ]
    for a, b in cases:
        s = similarity(a, b)
        print(f"{a!r} vs {b!r} -> similaridade={s:.3f}")
