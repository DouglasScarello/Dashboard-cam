"""
Intelligence Module — Olho de Deus OSS
Ingestão e banco de dados global de procurados e desaparecidos.

Fontes:
  - FBI Wanted API
  - OpenSanctions (Interpol Red/Yellow, Europol, NCA UK)
  - Interpol Gallery (Playwright)

Banco:
  - SQLite: data/intelligence.db
  - FAISS:  data/global_vector_db.faiss
"""
