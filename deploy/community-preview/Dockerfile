# Independent community image; never changes or runs a P2 container.
# linux/amd64 digest from Docker Official Images repo-info (2026-10-22).
FROM python@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/community
WORKDIR /app
COPY deploy/community-preview/requirements-runtime.lock /build/requirements-runtime.lock
COPY wheels/ /build/wheels/
RUN python -m pip install --no-index --no-deps --no-cache-dir --no-compile --require-hashes --find-links=/build/wheels -r /build/requirements-runtime.lock && rm -rf /build
COPY ocr-runtime/ /build/ocr/
RUN dpkg -i /build/ocr/system-debs/*.deb && python -m pip install --no-index --no-deps --no-cache-dir --no-compile --require-hashes --find-links=/build/ocr/wheelhouse -r /build/ocr/requirements-community-ocr.lock && mkdir -p /opt/ocr-bundle && cp -a /build/ocr/models /opt/ocr-bundle/models && cp -a /build/ocr/services /app/services && cp /build/ocr/LICENSE-2.0.txt /build/ocr/NOTICE.md /opt/ocr-bundle/ && rm -rf /build
ENV OCR_DET_MODEL_PATH=/opt/ocr-bundle/models/PP-OCRv6_det_small.onnx OCR_REC_MODEL_PATH=/opt/ocr-bundle/models/PP-OCRv6_rec_small.onnx OCR_CLS_MODEL_PATH=/opt/ocr-bundle/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx
ENV OCR_MODEL_SHA256='{"det":"090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f","rec":"6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884","cls":"e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c"}'
COPY scripts/ /app/scripts/
COPY demos/community-stage/ /app/demos/community-stage/
ARG SOURCE_SHA
ENV COMMUNITY_SOURCE_SHA=$SOURCE_SHA
RUN python -c "import re; assert re.fullmatch('[0-9a-f]{40}', '$SOURCE_SHA')" && printf '%s\n' "$SOURCE_SHA" > /app/COMMUNITY_SOURCE_SHA && chmod 0444 /app/COMMUNITY_SOURCE_SHA && mkdir -p /home/community && chown 10001:1008 /home/community && chmod 0700 /home/community
LABEL org.opencontainers.image.revision=$SOURCE_SHA
USER 10001:1008

# Only CI runs this target; no real identities, secrets, network or UK host.
FROM runtime AS verify
COPY tests/ /app/tests/
RUN python -B -m scripts.community_ocr_smoke
RUN python -B -m unittest discover -s tests -p 'test_community_first_install.py' -v && python -B -m unittest discover -s tests -p 'test_community_platform_host.py' -v && python -B -m unittest discover -s tests -p 'test_community_wechat_registration.py' -v

FROM runtime AS release
ENTRYPOINT ["python", "-B", "-m", "scripts.community_platform_host"]
