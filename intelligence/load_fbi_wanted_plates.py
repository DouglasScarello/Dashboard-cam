#!/usr/bin/env python3
"""
load_fbi_wanted_plates.py — Olho de Deus

Popula wanted_plates com placas reais mencionadas em TEXTO LIVRE (campo
description) dos 1242 registros já baixados da API do FBI — a API não tem
campo estruturado de placa, mas ~29 casos citam a placa na narrativa
("...Florida license plate QVHX48...").

Extraído e revisado manualmente em 2026-09-11 (ver conversa da sessão) —
o regex bruto pegou 3 falsos-positivos que foram removidos daqui:
  - "in an attemp" (de "stole multiple license plates in an attempt to...")
  - "on the rear" (de "displayed a FRAUDULENT temporary...license plate" —
    texto explícito de que a placa é falsa/roubada, não do veículo real)
  - "found abando"/"on the truck" (fragmentos sem placa de verdade capturada)

AVISO IMPORTANTE (o usuário optou por carregar tudo mesmo sabendo disso):
boa parte destes são casos de pessoas desaparecidas de DÉCADAS atrás
(1978-2011) — a placa citada no boletim original quase certamente já foi
REEMITIDA pra outro dono pelo DMV do estado. Um match aqui não é prova de
nada sozinho, precisa de checagem humana antes de qualquer ação — mesmo
princípio já documentado pro lado de rosto (nenhum threshold sozinho
resolve, revisão humana recomendada).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intelligence_db import DB, init_db

# (plate_text, country_code, reason)
FBI_WANTED_PLATES = [
    ("QVHX48", "US", "Triple Homicide - Delaware (2026) - veículo do suspeito, Florida"),
    ("X5725T", "US", "Amber Lynn Wilde - desaparecida, Green Bay WI (1998) - veículo dela"),
    ("TARAMAE", "US", "Robert Lee Hourihan - desaparecido, Palmyra VA (2011) - placa personalizada"),
    ("L20NAZ", "US", "Haneul Oh - desaparecida, Davie FL (2021) - veículo dela, placa de New Jersey"),
    ("SM15454", "US", "Wesley Dixon Jones - desaparecido, Pendleton OR (2025) - veículo dele"),
    ("931KSW", "US", "Paige Summer Moore - desaparecida, Broken Arrow OK (2012) - veículo suspeito"),
    ("RW3-48E", "US", "Hakan Karacay - desaparecido, Clifton NJ (1999) - veículo dele"),
    ("8C4696", "US", "Janet Callies - desaparecida, Grand Island NE (1978) - veículo dela"),
    ("EM 62829", "US", "Assaults on Federal Officers - Chicago IL (2025) - Chevy Tahoe suspeito"),
    ("2BBS966", "US", "Ylva Annika Hagner - desaparecida, Belmont CA (1996) - veículo dela"),
    ("E273380", "US", "Erica L. Thompson - desaparecida, Brookfield IL (2019) - veículo dela"),
    ("AFE7101", "US", "Ella Mae Begay - desaparecida, Sweetwater AZ (2021) - Ford F-150 dela"),
    ("J051EC", "US", "Tracy Eileen Ocasio - desaparecida, Ocoee FL (caso ativo) - veículo dela"),
    ("PEX755", "US", "Marcus Rutledge - desaparecido, Nashville TN - Plymouth Neon, placa Michigan"),
    ("KBYE67", "US", "Josue Calderon - caso ativo - Chevrolet Equinox, Florida"),
    ("936-VET", "US", "Luis Davila - caso ativo - Nissan Maxima, Arkansas"),
    ("ETD5587", "US", "Karen S. Adams - caso ativo - Suzuki Forenza, Pennsylvania"),
    ("YFH 2319", "US", "Richard Petrone / Danielle Imbo - caso conjunto - Dodge Dakota, Pennsylvania"),
    ("8862RA", "US", "Diego Trejo - caso ativo - Ford F-150, Georgia"),
    ("BKM9384", "US", "Caris E. Ayala - caso ativo - Toyota T-100, Georgia"),
]


def main():
    init_db()
    db = DB()
    inserted, skipped = 0, 0
    for plate, country, reason in FBI_WANTED_PLATES:
        try:
            db.execute(
                "INSERT INTO wanted_plates (plate_text, country_code, reason, source) VALUES (?, ?, ?, ?)",
                (plate, country, reason, "FBI API (texto livre, extraído 2026-09-11)"),
            )
            inserted += 1
        except Exception:
            skipped += 1  # já existia (plate_text é PRIMARY KEY)
    db.commit()
    total = db.execute("SELECT COUNT(*) as c FROM wanted_plates").fetchone()["c"]
    print(f"[wanted_plates] {inserted} inseridas, {skipped} já existiam. Total na tabela: {total}")
    db.close()


if __name__ == "__main__":
    main()
