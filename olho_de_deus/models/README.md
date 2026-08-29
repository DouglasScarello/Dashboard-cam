# Pesos de modelo (não versionados no git)

Os arquivos `.pt`/`.onnx` desta pasta são grandes demais pra git e ficam de
fora do repositório (`.gitignore`). Pra rodar `forensic_sr_engine.py` de
verdade (ALPR, super-resolução, restauração facial), baixe:

| Arquivo | Fonte | Licença | Tamanho |
|:--------|:------|:-------:|:--------|
| `best.pt` | [Koushim/yolov8-license-plate-detection](https://huggingface.co/Koushim/yolov8-license-plate-detection) | MIT | ~6,2 MB |
| `realesr-general-x4v3.onnx` | [Heliosoph/realesrgan-onnx](https://huggingface.co/Heliosoph/realesrgan-onnx) | BSD-3-Clause | ~4,9 MB |
| `codeformer.onnx` | [bluefoxcreation/Codeformer-ONNX](https://huggingface.co/bluefoxcreation/Codeformer-ONNX) | **S-Lab 1.0 — não-comercial** | ~377 MB |

Download rápido (Python, `huggingface_hub` já é dependência transitiva do projeto):

```python
from huggingface_hub import hf_hub_download

hf_hub_download("Koushim/yolov8-license-plate-detection", "best.pt", local_dir=".")
hf_hub_download("Heliosoph/realesrgan-onnx", "realesr-general-x4v3.onnx", local_dir=".")
hf_hub_download("bluefoxcreation/Codeformer-ONNX", "codeformer.onnx", local_dir=".")
```

> [!CAUTION]
> `codeformer.onnx` é licenciado **S-Lab License 1.0 — uso não-comercial
> apenas**. Ok pra portfólio pessoal; não pode ser usado se este projeto
> virar produto comercial sem licenciar separadamente.

Contexto de por que ONNX e não os pacotes Python "oficiais"
(`realesrgan`/`codeformer`/`paddleocr`): ver `PLANO_CONTINUACAO.md` Seção
5.2/5.3 — `basicsr`/`paddlepaddle` não instalam em Python ≥3.13.
