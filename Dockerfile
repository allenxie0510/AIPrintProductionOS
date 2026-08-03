# syntax=docker/dockerfile:1.7
FROM debian:bookworm-slim AS ghostscript-builder

ARG GHOSTSCRIPT_VERSION=10.07.1
ARG GHOSTSCRIPT_SHA512=7b38ca10fa7ab648924f7db3e2e4933c3d18e04c8db1346fca4d4f7b85dfbd7888d5fc46f413613b46429fb47b675a593994c25e50e9de4dcdbee3bdd8a5e449

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libfontconfig1-dev \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN curl --fail --location --retry 3 \
        "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10071/ghostscript-${GHOSTSCRIPT_VERSION}.tar.xz" \
        --output ghostscript.tar.xz \
    && echo "${GHOSTSCRIPT_SHA512}  ghostscript.tar.xz" | sha512sum --check - \
    && tar --extract --file ghostscript.tar.xz \
    && cd "ghostscript-${GHOSTSCRIPT_VERSION}" \
    && ./configure --prefix=/usr/local --without-x --disable-gtk \
    && make -j2 \
    && make install \
    && install -d /usr/local/share/ghostscript/iccprofiles \
    && install -m 644 iccprofiles/*.icc /usr/local/share/ghostscript/iccprofiles/

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    PRINT_MVP_DATA_DIR=/var/lib/printready \
    PRINT_MVP_ENGINE_MEMORY_BYTES=335544320 \
    PRINT_MVP_ENGINE_CPU_SECONDS=90 \
    PRINT_MVP_ENGINE_TIMEOUT_SECONDS=120 \
    PRINT_POC_CMYK_PROFILE=/usr/local/share/ghostscript/iccprofiles/default_cmyk.icc

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-dejavu-core \
        libfontconfig1 \
        poppler-utils \
        qpdf \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghostscript-builder /usr/local /usr/local
RUN ldconfig \
    && test "$(gs --version)" = "10.07.1" \
    && test -f "${PRINT_POC_CMYK_PROFILE}" \
    && qpdf --version

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY print_preflight ./print_preflight
COPY LICENSE THIRD_PARTY_NOTICES.md ./

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /var/lib/printready \
    && chown -R app:app /var/lib/printready

USER app
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10000/health', timeout=3)" || exit 1

CMD ["uvicorn", "print_preflight.api:app", "--host", "0.0.0.0", "--port", "10000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
