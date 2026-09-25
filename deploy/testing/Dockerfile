# Test tooling derives from the already-built release backend image.
# No pip install here: the tested Python dependencies are those of the release.
ARG RELEASE_BACKEND_IMAGE
FROM ${RELEASE_BACKEND_IMAGE}

# Entrypoint-execution tests need controllable command stubs. The runtime test
# service uses a read-only rootfs and tmpfs may be mounted noexec, so create the
# stubs at image-build time on the executable image filesystem.
USER root
RUN install -d -m 0755 /opt/release-entrypoint-test-bin \
    && printf '%s\n' '#!/bin/sh' 'printf "%s\\n" "${TEST_UID:-10001}"' > /opt/release-entrypoint-test-bin/id \
    && printf '%s\n' '#!/bin/sh' 'echo "python $*" >> "$TRACE"' 'exit "${TEST_PYTHON_CODE:-0}"' > /opt/release-entrypoint-test-bin/python \
    && printf '%s\n' '#!/bin/sh' 'echo "alembic $*" >> "$TRACE"' 'exit "${TEST_ALEMBIC_CODE:-0}"' > /opt/release-entrypoint-test-bin/alembic \
    && printf '%s\n' '#!/bin/sh' 'echo "uvicorn $*" >> "$TRACE"' 'exit 0' > /opt/release-entrypoint-test-bin/uvicorn \
    && chmod 0755 /opt/release-entrypoint-test-bin/*
COPY . /suite
USER 10001:10001
WORKDIR /app
ENTRYPOINT ["python", "-m", "pytest"]
