# Independent community image; never changes or runs a P2 container.
# linux/amd64 digest from Docker Official Images repo-info (2026-10-22).
FROM python@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/community
WORKDIR /app
COPY deploy/community-preview/requirements-runtime.lock /build/requirements-runtime.lock
COPY wheels/ /build/wheels/
RUN python -m pip install --no-index --no-deps --no-cache-dir --no-compile --require-hashes --find-links=/build/wheels -r /build/requirements-runtime.lock && rm -rf /build
COPY scripts/ /app/scripts/
COPY demos/community-stage/ /app/demos/community-stage/
ARG SOURCE_SHA
RUN python -c "import re; assert re.fullmatch('[0-9a-f]{40}', '$SOURCE_SHA')" && mkdir -p /home/community && chown 10001:1008 /home/community && chmod 0700 /home/community
LABEL org.opencontainers.image.revision=$SOURCE_SHA
USER 10001:1008

# Only CI runs this target; no real identities, secrets, network or UK host.
FROM runtime AS verify
COPY tests/ /app/tests/
RUN python -B -m unittest discover -s tests -p 'test_community_first_install.py' -v && python -B -m unittest discover -s tests -p 'test_community_platform_host.py' -v && python -B -m unittest discover -s tests -p 'test_community_wechat_registration.py' -v

FROM runtime AS release
ENTRYPOINT ["python", "-B", "-m", "scripts.community_platform_host"]
