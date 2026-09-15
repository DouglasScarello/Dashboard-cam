"""
test_alpr_pipeline.py — Olho de Deus

Testes de regressão pro pipeline de leitura de placa, contra os bugs REAIS
encontrados e corrigidos em 2026-09-14. Como o test_biometric_pipeline.py, roda
contra os artefatos de verdade (imagens de evidência, modelo YOLO, EasyOCR) —
não são unitários com mock, são testes de que o sistema funciona mesmo.

Por que isso existe: os três bugs corrigidos nessa data eram todos SILENCIOSOS.
O deskew não estourava exceção, ele devolvia um retângulo cinza; o OCR não
falhava, ele devolvia um texto plausível de um objeto errado. Não dava pra
perceber olhando log — só comparando com uma referência humana. Daí o gabarito
em fixtures/placas_gabarito.json, lido a olho, imagem por imagem.

Uso:
    poetry run pytest tests/test_alpr_pipeline.py -v
"""
import json
import os
import sys
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "olho_de_deus"))

import cv2
import numpy as np
import pytest

from forensic_sr_engine import alpr_engine, plate_enhancer

GABARITO = Path(__file__).parent / "fixtures" / "placas_gabarito.json"
EVIDENCIA = ROOT / "intelligence" / "evidence"

# Acurácia medida em 2026-09-14 logo depois das correções: 20 de 26 placas de
# confiança alta, contra 16/26 do pipeline antigo que gerou os arquivos.
# A trava é contra PIORA, não uma meta inventada. Se uma mudança futura subir
# esse número, suba a linha de base junto — é assim que ela vira catraca.
ACERTOS_MINIMOS = 20


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def gabarito():
    with open(GABARITO, encoding="utf-8") as fh:
        dados = json.load(fh)
    return dados


@pytest.fixture(scope="module")
def placas_conferidas(gabarito):
    """Só as linhas que eu consegui ler com certeza. As de confiança 'media'
    ficam de fora do teste estrito justamente porque um caractere ambíguo no
    gabarito faria o teste medir a minha dúvida, não o sistema."""
    return [p for p in gabarito["placas"] if p["legivel"] and p["confianca"] == "alta"]


def _carrega(nome: str) -> np.ndarray:
    caminho = EVIDENCIA / nome
    img = cv2.imread(str(caminho))
    assert img is not None, f"evidência sumiu do disco: {caminho}"
    return img


def _le_placa(img: np.ndarray, pais: str):
    """Mesma cadeia do laboratório forense: acha a placa, retifica, lê."""
    bbox, _conf = alpr_engine.detect_plate_bbox(img)
    recorte = img[bbox[1]:bbox[3], bbox[0]:bbox[2]] if bbox else img
    retificada, _homog = plate_enhancer.auto_deskew_homography(recorte, target_size=(400, 130))
    return alpr_engine.read_plate(retificada, country=pais)


# ─── 1. O deskew não pode apagar a placa ──────────────────────────────────

def test_deskew_nunca_devolve_imagem_vazia(gabarito):
    """auto_deskew_homography aceitava QUALQUER maior contorno de 4 lados e
    esticava pra 400x130. Num recorte já apertado na placa, o maior
    quadrilátero costuma ser um detalhe interno (parafuso, moldura, sombra), e
    a homografia apagava a placa — devolvia um retângulo cinza uniforme.

    O bug era invisível: nenhuma exceção, nenhum log, só a leitura virando None
    depois de funcionar (LAB3415 lia com 0.998 no recorte cru e sumia depois do
    deskew). A assinatura dele é desvio-padrão colapsado. É isso que travamos.
    """
    quase_uniformes = []
    for p in gabarito["placas"]:
        img = _carrega(p["arquivo"])
        retificada, _ = plate_enhancer.auto_deskew_homography(img, target_size=(400, 130))
        desvio = float(cv2.cvtColor(retificada, cv2.COLOR_BGR2GRAY).std())
        if desvio < 10.0:
            quase_uniformes.append((p["arquivo"], round(desvio, 2)))

    assert not quase_uniformes, (
        "o deskew devolveu imagem sem conteúdo (o bug do retângulo cinza "
        f"voltou) em: {quase_uniformes}"
    )


def test_deskew_preserva_a_leitura(placas_conferidas):
    """Complemento do teste acima: não basta a imagem ter contraste, a placa
    precisa continuar legível depois de passar pelo deskew. Aqui comparamos ler
    antes e depois — o deskew pode melhorar ou manter, nunca destruir em massa.
    """
    perdidas = []
    for p in placas_conferidas:
        img = _carrega(p["arquivo"])
        bbox, _ = alpr_engine.detect_plate_bbox(img)
        recorte = img[bbox[1]:bbox[3], bbox[0]:bbox[2]] if bbox else img

        antes, _, _ = alpr_engine.read_plate(recorte, country="PH")
        retificada, _ = plate_enhancer.auto_deskew_homography(recorte, target_size=(400, 130))
        depois, _, _ = alpr_engine.read_plate(retificada, country="PH")

        if antes is not None and depois is None:
            perdidas.append(p["arquivo"])

    # Uma ou outra pode se perder por ruído de OCR; um terço já é sinal de que
    # a retificação voltou a destruir imagem.
    limite = max(1, len(placas_conferidas) // 3)
    assert len(perdidas) < limite, (
        f"o deskew matou {len(perdidas)} de {len(placas_conferidas)} leituras "
        f"que funcionavam no recorte cru: {perdidas}"
    )


# ─── 2. Não inventar placa onde não tem placa ─────────────────────────────

def _emblema_de_capo(texto: str) -> np.ndarray:
    """Imita um emblema de carroceria: fundo escuro fora de foco, letras
    cromadas, proporção larga. Deliberadamente NÃO é um retângulo branco com
    texto preto — isso seria uma placa, e o YOLO acerta ao detectá-la."""
    img = cv2.GaussianBlur(np.full((220, 520, 3), (58, 52, 48), np.uint8), (0, 0), 8)
    cv2.putText(img, texto, (60, 130), cv2.FONT_HERSHEY_DUPLEX, 2.0,
                (205, 205, 210), 5, cv2.LINE_AA)
    return img


def test_ocr_sozinho_ainda_le_o_emblema():
    """Documenta o comportamento de base, pra deixar claro de onde vem o risco:
    o OCR isolado LÊ 'FIAT' e devolve como candidato INCERTO. Isso não é bug
    dele — é um leitor de texto fazendo o trabalho dele. O bug era o chamador
    tratar esse texto como placa."""
    for texto in ("FIAT", "TAXI", "SUZUKI"):
        img = _emblema_de_capo(texto)
        bbox, _ = alpr_engine.detect_plate_bbox(img)
        assert bbox is None, f"YOLO achou 'placa' num emblema escrito {texto!r}"
        lido, fmt, _ = alpr_engine.read_plate(img, country="BR")
        assert (lido, fmt) == (texto, "INCERTO"), (
            f"comportamento de base mudou: {texto!r} agora sai como {lido!r}/{fmt!r}. "
            "Reavaliar se o teste do laboratório forense abaixo ainda cobre o bug."
        )


def test_laboratorio_forense_nao_reporta_emblema_como_placa():
    """Família de falso positivo que o usuário reportou quatro vezes: telefone
    de fachada, letreiro "TAXI", rota de ônibus, e o emblema FIAT do capô
    reportado como a placa "FIHT".

    A raiz: sem bbox de placa detectada, o recorte inteiro da cena era tratado
    como se fosse a placa, e qualquer texto ali virava "candidato a placa" na
    tela do usuário. A correção é só aceitar leitura sem bbox quando ela casa
    com o formato oficial do país — a regex é a evidência de que é placa, não
    o detector. Por isso o teste roda o endpoint inteiro: é lá que mora a
    guarda, e é lá que o usuário vê o resultado.
    """
    import asyncio
    import base64

    from forensic_sr_engine import EnhanceROIRequest, enhance_roi

    for texto in ("FIAT", "TAXI", "SUZUKI"):
        img = _emblema_de_capo(texto)
        b64 = base64.b64encode(cv2.imencode(".jpg", img)[1].tobytes()).decode()
        resp = asyncio.run(enhance_roi(EnhanceROIRequest(
            image_base64=b64, roi_type="plate", scale_factor=2,
            apply_deskew=False, binarization="none", country="BR",
        )))
        assert resp.plate_bbox_detected is False
        assert resp.plate_ocr_candidate is None, (
            f"o laboratório reportou {resp.plate_ocr_candidate!r} como candidato a "
            f"placa a partir do emblema {texto!r} — o falso positivo voltou"
        )


def test_borrao_ilegivel_nao_vira_placa(gabarito):
    """O que nem um humano lê, o sistema não pode afirmar que leu. No gabarito
    tem um recorte de 26x11px que é borrão puro e onde o sistema antigo ainda
    assim cuspiu 'E0'."""
    ilegiveis = [p for p in gabarito["placas"] if not p["legivel"]]
    assert ilegiveis, "gabarito sem caso ilegível — o teste perdeu o sentido"

    for p in ilegiveis:
        lido, fmt, _ = _le_placa(_carrega(p["arquivo"]), gabarito["pais"])
        assert lido is None or fmt == gabarito["pais"], (
            f"{p['arquivo']} é ilegível a olho nu e o motor afirmou {lido!r}"
        )


# ─── 3. O país precisa chegar até o OCR ───────────────────────────────────

def test_pais_muda_a_leitura(placas_conferidas):
    """Achado de 2026-09-14: o laboratório forense chamava read_plate sem país,
    então assumia Brasil pra qualquer câmera. A correção posicional do Mercosul
    (LLLNLNN, letra obrigatória na 5ª posição) aplicada numa placa filipina
    (LLLNNNN) transformava todo dígito da 5ª posição em letra — LAF6673 saía
    LAF6G73, MAZ6041 saía MAZ6O41. Acurácia caía de 77% pra 31%.

    Este teste garante que o parâmetro país não vire enfeite ignorado: com o
    país errado o resultado TEM que ser pior.

    Sutileza que custou uma rodada de teste: passar country="BR" NÃO é o mesmo
    que passar None. A correção posicional do Mercosul só roda no ramo
    `self.country == "BR" and country is None` (forensic_sr_engine.py:676) —
    com "BR" explícito o motor só valida a regex, sem corrigir. Quem tinha o
    bug era o caminho None, então é ele que este teste compara.
    """
    def acertos(pais):
        return sum(1 for p in placas_conferidas
                   if _le_placa(_carrega(p["arquivo"]), pais)[0] == p["leitura_humana"])

    com_pais = acertos("PH")
    sem_pais = acertos(None)
    assert com_pais > sem_pais, (
        f"ler placa filipina sem informar o país deu o mesmo resultado "
        f"({com_pais} vs {sem_pais}) — sinal de que 'country' parou de ser "
        "propagado até o OCR, ou de que a correção posicional do Mercosul saiu"
    )


def test_endpoint_forense_aceita_pais():
    """Trava o contrato da API: o corpo do /api/forensic/enhance-roi precisa
    continuar carregando o país, senão a interface volta a assumir Brasil sem
    ninguém perceber."""
    from forensic_sr_engine import EnhanceROIRequest
    assert "country" in EnhanceROIRequest.model_fields, (
        "EnhanceROIRequest perdeu o campo 'country' — o laboratório forense "
        "volta a assumir formato brasileiro pra toda câmera"
    )


# ─── 4. Acurácia contra a referência humana ───────────────────────────────

def test_acuracia_nao_regride(placas_conferidas):
    """A única medida honesta de acerto que o projeto tem.

    Importante: o nome dos arquivos de evidência guarda o que o SISTEMA leu, não
    o que está na placa — comparar contra ele mede repetibilidade, não acerto.
    Por isso o gabarito foi lido a olho, imagem por imagem.
    """
    acertos, erros = 0, []
    for p in placas_conferidas:
        lido, _, _ = _le_placa(_carrega(p["arquivo"]), "PH")
        if lido == p["leitura_humana"]:
            acertos += 1
        else:
            erros.append(f"{p['leitura_humana']} -> {lido}")

    assert acertos >= ACERTOS_MINIMOS, (
        f"acurácia caiu: {acertos}/{len(placas_conferidas)} "
        f"(mínimo {ACERTOS_MINIMOS}). Erros: {erros}"
    )


def test_pipeline_atual_bate_o_antigo(placas_conferidas):
    """O pipeline que gerou os nomes dos arquivos acertou 16 de 26. Se uma
    mudança futura fizer o sistema atual ficar abaixo disso, ela desfez o
    trabalho de 2026-09-14."""
    antigo = sum(1 for p in placas_conferidas
                 if p["leitura_sistema"] == p["leitura_humana"])
    atual = sum(1 for p in placas_conferidas
                if _le_placa(_carrega(p["arquivo"]), "PH")[0] == p["leitura_humana"])

    assert atual > antigo, (
        f"o pipeline atual ({atual}/{len(placas_conferidas)}) não é melhor que "
        f"o antigo ({antigo}/{len(placas_conferidas)})"
    )
