# OCR model attribution and redistribution notice

This notice accompanies the pinned ONNX model files listed in `../model_manifest.json`.

## Covered artifacts and upstream attribution

The following artifacts are covered by RapidOCR's fixed model notice at:
https://github.com/RapidAI/RapidOCR/blob/4a3070f304467e6d426e78a82afea5cb1181f305/python/MODEL_LICENSES.md
Git blob ID: `3f66af490abe83df801bfb8d1ea80eed7b0048ae`.

- `PP-OCRv6_det_small.onnx` — derived from PaddlePaddle `PP-OCRv6_small_det`; SHA-256 `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`.
- `PP-OCRv6_rec_small.onnx` — derived from PaddlePaddle `PP-OCRv6_small_rec`; SHA-256 `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`.
- `ch_ppocr_mobile_v2.0_cls_mobile.onnx` — derived from PaddleOCR legacy text angle classifier; SHA-256 `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`.

Upstream model weights are copyrighted by Baidu and/or the applicable PaddleOCR rights holders. RapidOCR does not claim ownership of those weights. The fixed notice states the covered Section 6 artifacts are distributed under Apache License 2.0, including commercial use, subject to its terms.

Official model cards:
- https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det_onnx
- https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx

## Required accompanying materials

When distributing the covered models, include:
1. A copy of Apache License 2.0 as `LICENSE-2.0.txt` in this directory.
2. This attribution/NOTICE file.
3. The applicable upstream copyright and attribution notices.
4. A prominent notice for any modified or converted model files, identifying the modifications.
5. Any applicable upstream NOTICE contents if supplied by an upstream distribution. The cited RapidOCR notice states no additional model-specific NOTICE was identified for the Section 6 artifacts at its publication time.

Suggested conversion notice (use only if these files are converted/repackaged by this project):
> Converted from an official PaddleOCR model to ONNX for use with RapidOCR. The upstream model weights are copyright Baidu and/or the applicable PaddleOCR rights holders and are licensed under the Apache License, Version 2.0.

Do not imply endorsement by Baidu, PaddlePaddle, PaddleOCR, or RapidOCR. Trademarks are not granted by Apache-2.0.

## Verification status

- Fixed source notice and exact revision verified.
- Three pinned SHA-256 values match Section 6 of that notice and the project manifest.
- GitHub-hosted Run 40007712096 successfully downloaded and rehashed all three model files.
- Release packaging check remains pending: before a redistributable artifact is published, verify the archive actually includes this notice, LICENSE-2.0.txt, manifest and any applicable NOTICE files. Do not describe the OCR model bundle as released until that check passes.
