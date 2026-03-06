#!/usr/bin/env python3
"""
Teste da calibração distance → probability → confidence.
Não depende de cv2/FAISS: só as funções matemáticas (rodar com qualquer Python).
"""
# Constantes espelhadas de biometric_processor
PROB_K = 1.2
CONFIDENCE_HIGH_PROB = 0.85
CONFIDENCE_MEDIUM_PROB = 0.60


def distance_to_probability(distance: float) -> float:
    return __import__("math").exp(-distance * PROB_K)


def probability_to_confidence(probability: float) -> str:
    if probability >= CONFIDENCE_HIGH_PROB:
        return "HIGH"
    if probability >= CONFIDENCE_MEDIUM_PROB:
        return "MEDIUM"
    return "LOW"


if __name__ == "__main__":
    print("Calibração: distance → probability → confidence (PROB_K = 1.2)\n")
    for d in [0.15, 0.25, 0.35, 0.45, 0.55]:
        p = distance_to_probability(d)
        c = probability_to_confidence(p)
        print(f"  distance={d:.2f}  →  prob={p:.3f}  →  {c}")
    print("\n(Thresholds: HIGH ≥ 0.85, MEDIUM ≥ 0.60 — calibrar com match_logs depois)")
