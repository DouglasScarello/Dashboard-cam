#!/usr/bin/env python3
"""
build_plate_formats_db.py — Olho de Deus

Banco de referência LEVE (SQLite, 1 tabela) com o formato de placa veicular
por país — pedido do usuário em 2026-09-11 depois de descobrir, testando o
ALPR ao vivo numa câmera japonesa, que o motor de OCR/validação do projeto
(forensic_sr_engine.py) só reconhece formato brasileiro (Mercosul/Antigo).
Sem saber o formato de cada país, não dá pra saber como interpretar (ou nem
tentar) o texto que o OCR devolve numa câmera estrangeira.

Cobertura: NÃO são os ~195 países do mundo — seria preciso pesquisar cada um
individualmente (as páginas da Wikipédia/Europlate são por país, sem uma
tabela central confiável). Este é um ponto de partida real, pesquisado com
fontes (ver campo source_urls de cada linha), cobrindo:
  - os 3 países já testados neste projeto com câmera real (BR, JP, TH)
  - os países mais relevantes por população/uso de ANPR (EUA, China, Índia,
    Coreia do Sul, Indonésia, Filipinas, Vietnã, México, Argentina, além de
    um perfil genérico da faixa azul da UE)
Extensível: rodar este script de novo com mais linhas em PLATE_FORMATS não
apaga as existentes (INSERT OR REPLACE por country_code).

Uso:
    poetry run python3 build_plate_formats_db.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "plate_formats.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plate_formats (
    country_code      TEXT PRIMARY KEY,   -- ISO 3166-1 alpha-2 (BR, JP, TH...)
    country_name_pt   TEXT NOT NULL,
    layout             TEXT NOT NULL,      -- 'single_line' | 'two_line'
    script             TEXT NOT NULL,      -- ex: 'latin', 'latin+kanji+hiragana'
    pattern_desc_pt    TEXT NOT NULL,      -- descrição legível do formato
    regex              TEXT,               -- regex best-effort (NULL se varia demais, ex: EUA por estado)
    example            TEXT,
    ocr_langs          TEXT NOT NULL,      -- códigos de idioma pro EasyOCR, separados por vírgula
    color_scheme_pt    TEXT,
    confidence         TEXT NOT NULL,      -- 'verificado_multi_fonte' | 'fonte_unica' | 'padrao_regional_generico'
    source_urls        TEXT,
    notes_pt           TEXT,
    tested_in_project  INTEGER NOT NULL DEFAULT 0,  -- 1 = já testamos com câmera real deste país
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Cada tupla: (country_code, country_name_pt, layout, script, pattern_desc_pt,
#              regex, example, ocr_langs, color_scheme_pt, confidence,
#              source_urls, notes_pt, tested_in_project)
PLATE_FORMATS = [
    (
        "BR", "Brasil", "single_line", "latin",
        "Mercosul (2018+): 3 letras + 1 dígito + 1 letra + 2 dígitos. "
        "Antigo (pré-2018, ainda circula muito): 3 letras + 4 dígitos.",
        r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$|^[A-Z]{3}[0-9]{4}$",
        "ABC1D23 (Mercosul) / ABC1234 (antigo)",
        "en",
        "Mercosul: cinza/branco com faixa do Mercosul. Antigo: cinza com letras pretas (particular).",
        "verificado_multi_fonte",
        "https://pt.wikipedia.org/wiki/Sistema_de_Placas_de_Identificação_de_Veículos",
        "JÁ IMPLEMENTADO no forensic_sr_engine.py (ForensicALPR) — formato padrão/default do motor hoje.",
        0,
    ),
    (
        "JP", "Japão", "two_line", "latin+kanji+hiragana",
        "Linha de cima: nome da região/prefeitura em KANJI + código de classificação "
        "(até 3 dígitos). Linha de baixo: 1 caractere HIRAGANA + número de série de 4 "
        "dígitos separado XX-XX (zero à esquerda vira um ponto '・').",
        r"^\d{2}-\d{2}$",  # só a parte numérica da linha de baixo é validável sem OCR em japonês
        "大阪 330 さ 11-28",
        "en,ja",
        "Branco+texto verde = particular padrão (>660cc). Amarelo+preto = kei car (<660cc). "
        "Verde+branco = uso comercial.",
        "verificado_multi_fonte",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_Japan; "
        "https://www.zervtek.com/resources/understanding-japanese-license-plates",
        "TESTADO AO VIVO nesta sessão (câmera de Minoh, Osaka) — OCR em inglês só lê a "
        "parte numérica da linha de baixo; kanji/hiragana exigem easyocr.Reader(['ja']), "
        "não testado ainda. Regex acima cobre só o fragmento numérico.",
        1,
    ),
    (
        "TH", "Tailândia", "two_line", "thai+latin_digits",
        "Linha de cima: até 1 dígito (só se o pool de letras acabou) + 2 consoantes "
        "tailandesas + até 4 algarismos arábicos. Linha de baixo: nome da província em "
        "escrita tailandesa (não é sigla — nome completo).",
        None,  # letras tailandesas não são A-Z, regex ASCII não se aplica sem transliteração
        "1กข 1234 (Bangkok) — ก and ข são consoantes tailandesas",
        "th,en",
        "Branco+preto = padrão. Cores variam por categoria (táxi, uso pessoal, etc — não "
        "confirmado em detalhe nesta pesquisa).",
        "verificado_multi_fonte",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_Thailand",
        "TESTADO AO VIVO nesta sessão (câmeras de Bangkok e Khon Kaen) — resolução da "
        "câmera de trânsito não foi suficiente pra OCR nenhum, nem com easyocr.Reader(['th']) "
        "(não chegamos a testar esse idioma, a imagem já não dava nem pra detectar a placa).",
        1,
    ),
    (
        "US", "Estados Unidos", "single_line", "latin",
        "Varia POR ESTADO (50 formatos diferentes) — não existe padrão nacional único. "
        "Exemplos: Nova York ABC-1234, Califórnia 1ABC234, Kansas 1234ABC, "
        "Delaware/Rhode Island 123456 (só dígitos).",
        None,  # inerentemente multi-formato, precisaria 1 regex por estado
        "ABC-1234 (NY) / 1ABC234 (CA)",
        "en",
        "Varia por estado, geralmente branco com texto colorido + nome do estado no topo.",
        "padrao_regional_generico",
        "https://en.wikipedia.org/wiki/United_States_license_plate_designs_and_serial_formats",
        "Pra validar de verdade precisaria de uma regex por estado (50 entradas) — não feito "
        "aqui, fica como próximo passo se algum dia usarmos câmera dos EUA pra placa.",
        0,
    ),
    (
        "CN", "China", "single_line", "han+latin",
        "7 caracteres: 1 caractere chinês (região/província) + 1 letra latina (cidade/"
        "distrito administrativo) + 5 caracteres alfanuméricos (série única do veículo).",
        r"^[A-Z][A-Z0-9]{5}$",  # sem o caractere han inicial, que regex ASCII não cobre
        "京A12345",
        "ch_sim,en",
        "Azul = particular a combustão. Verde = elétrico/híbrido plug-in. Amarelo = comercial/ônibus. "
        "Branco = polícia/militar.",
        "fonte_unica",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_China",
        "Regex cobre só os 6 caracteres depois do han inicial (região) — precisa "
        "easyocr.Reader(['ch_sim']) pra ler o han também.",
        0,
    ),
    (
        "IN", "Índia", "single_line", "latin",
        "XX NN XX NNNN — 2 letras (código do estado) + 2 dígitos (código do RTO/distrito) "
        "+ 1-2 letras (série) + 4 dígitos (número único). Letras I e O não são usadas "
        "(confundem com 1 e 0).",
        r"^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$",
        "TS09AB1234",
        "en",
        "Branco+preto = particular. Amarelo+preto = comercial/táxi. Verde = veículo elétrico. "
        "Vermelho = temporário/novo sem registro definitivo.",
        "verificado_multi_fonte",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_India; "
        "https://www.godigit.com/traffic-rules/different-types-of-number-plates",
        None,
        0,
    ),
    (
        "KR", "Coreia do Sul", "single_line", "hangul+latin_digits",
        "Sistema novo (2019+, 8 dígitos): 3 dígitos + 1 caractere HANGUL (categoria de uso) "
        "+ 4 dígitos. Sistema antigo (7 dígitos) ainda circula: 2-3 dígitos + hangul + 4 dígitos.",
        r"^\d{3,4}$",  # só os blocos numéricos — hangul não é ASCII
        "123 가 4567",
        "ko,en",
        "Branco = particular. Verde = comercial/transporte (táxi, caminhão). "
        "Amarelo-esverdeado = veículo elétrico (novo padrão).",
        "verificado_multi_fonte",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_South_Korea",
        None,
        0,
    ),
    (
        "ID", "Indonésia", "single_line", "latin",
        "1-2 letras (código da província) + 1-4 dígitos (código de área/série) + até 3 "
        "letras (série do veículo).",
        r"^[A-Z]{1,2}[0-9]{1,4}[A-Z]{1,3}$",
        "B1234ABC (Jacarta)",
        "en",
        "Preto+branco = particular. Amarelo+preto = público/transporte. Vermelho = governo. "
        "Branco+azul = corpo diplomático.",
        "fonte_unica",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_Indonesia",
        "Já temos câmeras ATCS de trânsito na Indonésia catalogadas (Tasikmalaya) — "
        "candidatas naturais pra testar esse formato.",
        0,
    ),
    (
        "PH", "Filipinas", "single_line", "latin",
        "3 letras (a 1ª indica o escritório regional emissor, ex: N=Metro Manila) + "
        "espaço + 4 dígitos.",
        r"^[A-Z]{3}[0-9]{4}$",
        "NAB1234",
        "en",
        "Branco+preto = padrão particular atual.",
        "fonte_unica",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_the_Philippines",
        None,
        0,
    ),
    (
        "VN", "Vietnã", "single_line", "latin",
        "2 dígitos (código da província/cidade) + 1 letra (série) + 4-5 dígitos.",
        r"^[0-9]{2}[A-Z][0-9]{4,5}$",
        "29A12345",
        "en",
        "Branco+preto = particular. Amarelo+preto = comercial. Azul+branco = órgão do governo. "
        "Vermelho+branco = militar.",
        "fonte_unica",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_Vietnam",
        None,
        0,
    ),
    (
        "MX", "México", "single_line", "latin",
        "3 letras + 2 dígitos + 2 dígitos (varia visualmente por estado, mas essa é a "
        "estrutura predominante no padrão federal atual).",
        r"^[A-Z]{3}[0-9]{2}[0-9]{2}$",
        "ABC1234",
        "en",
        "Design varia por estado.",
        "fonte_unica",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plate",
        None,
        0,
    ),
    (
        "AR", "Argentina", "single_line", "latin",
        "Novo padrão Mercosul (2016+): 2 letras + 3 dígitos + 2 letras. "
        "Antigo (1995-2016): 3 letras + 3 dígitos.",
        r"^[A-Z]{2}[0-9]{3}[A-Z]{2}$|^[A-Z]{3}[0-9]{3}$",
        "AB123CD (Mercosul) / ABC123 (antigo)",
        "en",
        "Padrão Mercosul com faixa/logo do bloco, igual ao Brasil.",
        "fonte_unica",
        "https://en.wikipedia.org/wiki/Vehicle_registration_plate",
        "Mesmo bloco Mercosul do Brasil — regex bem parecida, mas ORDEM letra/dígito é "
        "diferente (Brasil: LLLNLNN: Argentina: LLNNNLL). Não usar a mesma regex do BR.",
        0,
    ),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA_SQL)
    conn.executemany(
        """INSERT INTO plate_formats
           (country_code, country_name_pt, layout, script, pattern_desc_pt, regex,
            example, ocr_langs, color_scheme_pt, confidence, source_urls, notes_pt,
            tested_in_project)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(country_code) DO UPDATE SET
             country_name_pt=excluded.country_name_pt, layout=excluded.layout,
             script=excluded.script, pattern_desc_pt=excluded.pattern_desc_pt,
             regex=excluded.regex, example=excluded.example, ocr_langs=excluded.ocr_langs,
             color_scheme_pt=excluded.color_scheme_pt, confidence=excluded.confidence,
             source_urls=excluded.source_urls, notes_pt=excluded.notes_pt,
             tested_in_project=excluded.tested_in_project, updated_at=datetime('now')""",
        PLATE_FORMATS,
    )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM plate_formats").fetchone()[0]
    print(f"[plate_formats] banco pronto em {DB_PATH} — {count} países cadastrados.")
    conn.close()


if __name__ == "__main__":
    main()
