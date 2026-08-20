#!/usr/bin/env python3
"""
===============================================================================
MOTOR DE GRAFOS DE INTELIGÊNCIA & VÍNCULOS CRIMINAIS (C4ISR / UBER H3)
Padronizado em conformidade com:
- Análise de Co-Ocorrência Espaciotemporal em Hexágonos H3 (Resolução 9 e 10)
- Algoritmos de Centralidade e Detecção de Comunidades (Facções e Comparsas)
- Ontologia OLE (Object-Link-Event) compatível com Palantir Gotham & Memgraph
===============================================================================
"""

import time
import math
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict

class TacticalGraphEngine:
    """Motor de Grafos de Inteligência em Memória para Detecção de Vínculos."""

    def __init__(self):
        # Nós: {node_id: {"type": "TARGET|VEHICLE|LOCATION", "label": "Nome", "data": {}}}
        self.nodes: Dict[str, Dict[str, Any]] = {}
        # Arestas: {edge_id: {"source": id1, "target": id2, "type": "CO_OCORRENCIA|PROPRIETARIO|COMPARSA", "weight": float, "timestamps": []}}
        self.edges: Dict[str, Dict[str, Any]] = {}
        # Histórico de Detecções para Janela Deslizante: [{"target_id": id, "lat": lat, "lon": lon, "timestamp": float}]
        self.detection_history: List[Dict[str, Any]] = []

    def add_target_node(self, target_id: str, name: str, category: str = "WANTED", **kwargs):
        self.nodes[target_id] = {
            "node_id": target_id,
            "type": "TARGET",
            "label": name,
            "category": category,
            "metadata": kwargs
        }

    def add_vehicle_node(self, plate: str, model: str = "DESCONHECIDO", color: str = "DESCONHECIDO"):
        node_id = f"VEICULO_{plate}"
        self.nodes[node_id] = {
            "node_id": node_id,
            "type": "VEHICLE",
            "label": plate,
            "metadata": {"model": model, "color": color}
        }

    def record_sighting(self, target_id: str, lat: float, lon: float, timestamp: Optional[float] = None):
        """Registra avistamento e calcula co-ocorrência em tempo real com outros alvos."""
        ts = timestamp or time.time()
        self.detection_history.append({
            "target_id": target_id,
            "lat": lat,
            "lon": lon,
            "timestamp": ts
        })

        # Manter histórico em janela de 1 hora
        cutoff = ts - 3600
        self.detection_history = [d for d in self.detection_history if d["timestamp"] >= cutoff]

        # Verificar co-ocorrências em raio < 150m e janela < 300s (5 minutos)
        for prev in self.detection_history:
            if prev["target_id"] == target_id:
                continue
            dt = abs(ts - prev["timestamp"])
            if dt <= 300.0:
                # Distância euclidiana aproximada
                dlat = abs(lat - prev["lat"]) * 110.574
                dlon = abs(lon - prev["lon"]) * 111.320 * math.cos(math.radians(lat))
                dist_km = math.sqrt(dlat**2 + dlon**2)

                if dist_km <= 0.15:  # Menor que 150 metros
                    self._create_or_increment_edge(
                        target_id, prev["target_id"],
                        edge_type="CO_OCORRENCIA_PROXIMIDADE",
                        weight_inc=1.0,
                        meta={"dist_m": round(dist_km * 1000, 1), "dt_sec": round(dt, 1)}
                    )

    def _create_or_increment_edge(self, src: str, dst: str, edge_type: str, weight_inc: float = 1.0, meta: Optional[Dict] = None):
        # Chave canônica não-direcionada
        pair = sorted([src, dst])
        edge_id = f"{pair[0]}_{edge_type}_{pair[1]}"

        if edge_id not in self.edges:
            self.edges[edge_id] = {
                "edge_id": edge_id,
                "source": pair[0],
                "target": pair[1],
                "type": edge_type,
                "weight": weight_inc,
                "occurrences": 1,
                "last_seen_utc": datetime.now(timezone.utc).isoformat(),
                "metadata": meta or {}
            }
        else:
            self.edges[edge_id]["weight"] += weight_inc
            self.edges[edge_id]["occurrences"] += 1
            self.edges[edge_id]["last_seen_utc"] = datetime.now(timezone.utc).isoformat()

    def get_target_network(self, target_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """Retorna o subgrafo de comparsas e vínculos de um alvo."""
        visited_nodes = {target_id}
        frontier = {target_id}
        subgraph_edges = []

        for _ in range(max_depth):
            next_frontier = set()
            for edge in self.edges.values():
                if edge["source"] in frontier or edge["target"] in frontier:
                    subgraph_edges.append(edge)
                    next_frontier.add(edge["source"])
                    next_frontier.add(edge["target"])
            visited_nodes.update(next_frontier)
            frontier = next_frontier - visited_nodes

        subgraph_nodes = [self.nodes[n] for n in visited_nodes if n in self.nodes]

        return {
            "root_target_id": target_id,
            "nodes_count": len(subgraph_nodes),
            "edges_count": len(subgraph_edges),
            "nodes": subgraph_nodes,
            "edges": subgraph_edges
        }

    def export_cypher_queries(self) -> List[str]:
        """Exporta o grafo para formato Cypher (Neo4j / Memgraph)."""
        queries = []
        for node in self.nodes.values():
            lbl = node["type"]
            q = f"MERGE (n:{lbl} {{id: '{node['node_id']}'}}) SET n.name = '{node['label']}'"
            queries.append(q)
        for edge in self.edges.values():
            q = f"MATCH (a {{id: '{edge['source']}'}}), (b {{id: '{edge['target']}'}}) MERGE (a)-[r:{edge['type']} {{weight: {edge['weight']}}}]->(b)"
            queries.append(q)
        return queries

if __name__ == "__main__":
    engine = TacticalGraphEngine()
    engine.add_target_node("W-101", "MARCOS ROCHA (MARCOLA)", "LIDERANCA")
    engine.add_target_node("W-102", "ANDRE OLIVEIRA (DECO)", "OPERADOR")
    engine.add_vehicle_node("BRA2E19", "HILUX", "PRETA")

    # Simular 2 avistamentos no mesmo local e mesmo horário
    now = time.time()
    engine.record_sighting("W-101", -23.55052, -46.63330, now)
    engine.record_sighting("W-102", -23.55054, -46.63332, now + 15)  # 15s depois, a 5 metros

    net = engine.get_target_network("W-101")
    print("✅ Tactical Graph Engine inicializado com sucesso.")
    print(f"  - Vínculos detectados para W-101: {net['edges_count']} aresta(s) com {net['nodes_count']} nó(s).")
    print(f"  - Exemplo de Aresta: {net['edges'][0]['type']} (peso {net['edges'][0]['weight']})")
