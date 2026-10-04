FROM debian:bookworm-slim AS extract
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/extract-quartus.py /usr/local/bin/extract-quartus
# Ordinary COPY works with both the legacy builder and BuildKit.
# The installer is cached in this stage, but is not copied to the final image.
COPY 90sp2_quartus_free.exe /installer.exe
RUN python3 /usr/local/bin/extract-quartus /installer.exe /opt/altera/90sp2 \
    && rm /installer.exe

FROM debian:bookworm-slim
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        wine wine32:i386 wine64 xvfb xauth fonts-liberation tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 builder \
    && mkdir /build && chown builder:builder /build
COPY --from=extract /opt/altera/90sp2 /opt/altera/90sp2
COPY scripts/run-quartus.sh /usr/local/bin/run-quartus
RUN chmod 755 /usr/local/bin/run-quartus
ENV QUARTUS_INSTALL_DIR=/opt/altera/90sp2 \
    WINEARCH=win32 \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES="mscoree,mshtml,winemenubuilder.exe="
WORKDIR /build
USER builder
# Check both ACEX1K densities before accepting the image.
RUN timeout 180s /usr/local/bin/run-quartus quartus_sh --version
COPY --chown=builder:builder tests/smoke/ /tmp/quartus-smoke/
RUN set -eu; \
    cd /tmp/quartus-smoke; \
    for project in smoke smoke_ep1k100; do \
        timeout 600s /usr/local/bin/run-quartus quartus_sh --flow compile "$project.qpf"; \
        test -s "output_files/$project.sof"; \
    done; \
    rm -rf /tmp/quartus-smoke
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/run-quartus"]
CMD ["quartus_sh", "--version"]
