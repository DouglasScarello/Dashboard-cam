---
name: osint-intelligence
description: >-
  Procedimentos para ingestão OSINT multi-fonte (Interpol, FBI), indexação vetorial pgvector/FAISS,
  cálculo dinâmico de Threat Score e geração de dossiês periciais criptografados em PDF.
---

# OSINT Intelligence Skill

Esta skill descreve o funcionamento do módulo de inteligência e base de dados tática:

## 1. Módulos Principais
- **global_ingestion.py**: Coleta assíncrona de perfis de criminosos procurados e desaparecidos via APIs e scrapers estruturados com UIDs determinísticos SHA-256.
- **intelligence_db.py**: Camada dual de banco de dados com suporte automático a SQLite (desenvolvimento local) e PostgreSQL/pgvector (produção).
- **score_engine.py**: Motor ponderado de cálculo de periculosidade baseado em crimes, recompensas e histórico biométrico.
- **forensic_report.py**: Geração de dossiê pericial criptografado em PDF com chave AES-256-EAX.

## 2. Padrões de Integridade
- Todas as evidências salvas devem registrar o hash SHA-256 do arquivo no momento exato do match biométrico.
- Consultas SQL devem utilizar parâmetros parametrizados (`?` / `%s`) para total proteção contra SQL Injection.
