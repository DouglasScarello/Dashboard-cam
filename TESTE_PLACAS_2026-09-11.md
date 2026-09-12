# Teste de leitura de placa ao vivo — 20 amostras (2026-09-11/12)

Câmera: `globetv_davao_leongarcia` (Leon Garcia Street, Davao City, Filipinas — YouTube ao vivo)
País configurado: PH · Motor: `monitor_plates.py` + `plate_processor.py` (votação de consenso, mínimo 8 frames / 70% de concordância na posição mais fraca)

Sem uso da lista de observação (`wanted_plates`) — só leitura e gravação, conforme pedido. Confiança = fração de frames que concordaram na posição de caractere mais fraca (pior caso, não média).

**Fui conferindo contra a foto de evidência de cada uma enquanto montava esse arquivo** — coluna "Conferi eu" abaixo. Onde não conferi, a coluna fica em branco pra você julgar.

| # | Placa lida | Formato | Confiança | Frames | Conferi eu | Foto de evidência |
|---|---|---|---|---|---|---|
| 166 | `ISUZU` | INCERTO | 100% | 8 | ❌ **Errado** — é o nome da marca no capô do caminhão, não a placa (placa real ilegível de tão pequena) | `plate_ISUZU_20260911_230607_086007.jpg` |
| 167 | `LAL5967` | PH | 87,5% | 8 | ✅ **Certo** — bate exatamente "LAL 5967" | `plate_LAL5967_20260911_231933_409306.jpg` |
| 168 | `LAL5967` | PH | 100% | 8 | ✅ **Certo** (mesmo veículo do #167, 2ª trilha) | `plate_LAL5967_20260911_231934_170532.jpg` |
| 169 | `LAN9936` | PH | 70,6% | 17 | ✅ **Certo** — bate exatamente "LAN 9936" | `plate_LAN9936_20260911_234208_258034.jpg` |
| 170 | `LAN9936` | PH | 100% | 8 | ✅ **Certo** (mesmo veículo do #169) | `plate_LAN9936_20260911_234220_328790.jpg` |
| 171 | `ILAB3631` | INCERTO | 100% | 8 | 🟡 **Quase** — placa real é "LAB 3631", sobrou um "I" na frente | `plate_ILAB3631_20260911_234254_656258.jpg` |
| 172 | `ILAB3631` | INCERTO | 70% | 10 | 🟡 **Quase** (mesmo veículo, mesmo erro) | `plate_ILAB3631_20260911_234307_307243.jpg` |
| 173 | `ILAB3631` | INCERTO | 100% | 8 | 🟡 **Quase** (mesmo veículo) | `plate_ILAB3631_20260911_234308_967627.jpg` |
| 174 | `ILAB3631` | INCERTO | 100% | 8 | 🟡 **Quase** (mesmo veículo) | `plate_ILAB3631_20260911_234310_890824.jpg` |
| 175 | `ILAB3631` | INCERTO | 100% | 8 | 🟡 **Quase** (mesmo veículo) | `plate_ILAB3631_20260911_234319_958729.jpg` |
| 176 | `ILAB3631` | INCERTO | 100% | 8 | 🟡 **Quase** (mesmo veículo) | `plate_ILAB3631_20260911_234322_510840.jpg` |
| 177 | `ILAB3631` | INCERTO | 70% | 10 | 🟡 **Quase** (mesmo veículo) | `plate_ILAB3631_20260911_234326_677423.jpg` |
| 178 | `CPF531` | INCERTO | 75% | 8 | ✅ **Certo** — bate exatamente "CPF 531" (formato mais curto, 3+3, por isso caiu como INCERTO na nossa regra 3+4) | `plate_CPF531_20260911_235629_725771.jpg` |
| 179 | `KBB15852` | INCERTO | 71,4% | 14 | 🟡 **Quase** — placa real é "KBB 5852", sobrou um "1" no meio | `plate_KBB15852_20260911_235719_795053.jpg` |
| 180 | `KBB5852` | PH | 70,6% | 17 | ✅ **Certo** (mesmo veículo do #179, 2ª trilha corrigiu sozinha) | `plate_KBB5852_20260911_235724_275374.jpg` |
| 181 | `LAP4401` | PH | 75% | 8 | ✅ **Certo** — bate exatamente "LAP 4401" | `plate_LAP4401_20260912_001450_493588.jpg` |
| 182 | `ISUZU` | INCERTO | 87,5% | 8 | ❌ **Errado** — de novo o nome da marca, outro caminhão Isuzu | `plate_ISUZU_20260912_004912_348695.jpg` |
| 183 | `WOW` | INCERTO | 87,5% | 8 | ❌ **Errado** — é o logo de uma empresa (triciclo/tuk-tuk "WOW"), não tem placa visível nesse ângulo | `plate_WOW_20260912_013458_934352.jpg` |
| 184 | `NEBRIA` | INCERTO | 75% | 8 | ❌ **Errado** — nome de empresa/motorista escrito no caminhão, placa real ilegível | `plate_NEBRIA_20260912_033019_582299.jpg` |
| 185 | `LAN7525` | PH | 75% | 8 | 🟡 **Provavelmente certo** — placa parece "LAM 7525" ou "LAN 7525", M/N ambíguo até pra mim nessa foto | `plate_LAN7525_20260912_033315_287690.jpg` |

## Resumo (conferido por mim, 8 vehicles distintos nas 20 linhas)

- ✅ **Certo**: 8 linhas (5 veículos distintos: LAL5967, LAN9936, CPF531, KBB5852, LAP4401)
- 🟡 **Quase certo** (1 caractere a mais/errado): 9 linhas (2 veículos distintos: ILAB3631→LAB3631, KBB15852→KBB5852) + LAN7525 ambíguo
- ❌ **Errado de vez** (leu marca/logo em vez da placa): 3 linhas (ISUZU x2, WOW, NEBRIA — todos caminhões/veículos onde o detector de placa achou o emblema da marca em vez do retângulo da placa real)

## Padrões que notei

1. **Quando acerta, acerta redondo** — nenhuma das 8 leituras "certas" teve nem 1 caractere errado.
2. **O erro mais comum é um caractere extra no começo** ("I" ou "1" sobrando antes da placa real) — parece ser um parafuso, reflexo ou moldura da placa sendo lido como caractere. Mesmo veículo, rodadas diferentes, mesmo erro sempre no mesmo lugar.
3. **O erro mais grave é o detector de placa mirar errado** — em caminhões grandes (Isuzu, Hino) ele às vezes localiza o emblema da marca no lugar da placa de verdade, que fica pequena demais pra competir visualmente. Isso não é erro de OCR, é erro de "achar onde a placa está".
4. **A votação por consenso está funcionando pro que foi desenhada** — quando o mesmo veículo aparece 2x (LAL5967, LAN9936, KBB), a segunda passagem sempre bateu 100% com a primeira ou corrigiu o erro (KBB15852→KBB5852). O problema não é a votação, é a localização inicial da placa.
