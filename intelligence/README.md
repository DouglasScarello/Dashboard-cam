# 🌐 Módulo Intelligence — Olho de Deus OSS

Banco de dados global de procurados e desaparecidos.

## Estrutura

```
intelligence/
├── fbi_ingestion.py       # Ingestão FBI API → FAISS (embeddings biométricos)
├── global_ingestion.py    # Ingestão multi-fonte (FBI + OpenSanctions + Interpol)
├── intelligence_db.py     # Banco SQLite + CLI de busca interativa
├── populate_db.py         # Popula o SQLite com todas as fontes
├── data/
│   ├── intelligence.db        # Banco SQLite principal
│   ├── global_vector_db.faiss # Índice de embeddings biométricos
│   ├── global_metadata.json   # Metadados dos embeddings
│   ├── global_faces/          # Imagens baixadas (procurados/desaparecidos)
│   └── fbi_faces/             # Imagens FBI
└── pyproject.toml
```

## Fontes de Dados

| Fonte | Registros | Tipo |
|-------|-----------|------|
| FBI Wanted API | ~1.100 | Procurados EUA (com foto) |
| Interpol Red (OpenSanctions) | 6.437 | Procurados internacionais |
| Interpol Yellow (OpenSanctions) | 8.543 | Desaparecidos internacionais |
| Europol EU Most Wanted | ~200 | Procurados Europa |
| NCA UK Most Wanted | ~20 | Procurados Reino Unido |

## Comandos

```bash
# Instalar dependências
poetry install

# Ingestão completa (FBI + OpenSanctions + Interpol Gallery)
TF_CPP_MIN_LOG_LEVEL=3 poetry run python global_ingestion.py

# Popular banco SQLite com todos os dados
TF_CPP_MIN_LOG_LEVEL=3 poetry run python populate_db.py

# Busca interativa no banco
poetry run python intelligence_db.py search

# Exportar para CSV
# (dentro do modo search, pressione 'e')
```

## Banco de Dados (SQLite)

Tabelas:
- `individuals` — dados completos (nome, nascimento, descrição, recompensa, foto local)
- `crimes` — crimes associados por indivíduo
- `locations` — localizações (last seen, operação, nacionalidade)
- `face_embeddings` — embeddings ArcFace 512-d em blob binário

## Integração com Olho de Deus

O módulo Olho de Deus (`../olho_de_deus/`) lê o banco FAISS para comparação em tempo real.
Aponte o `biometric_processor.py` para `../intelligence/data/global_vector_db.faiss`.
