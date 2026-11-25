# Deskville API image (layer 5.2, D36). Built natively on an ARM runner for
# Graviton (Fargate ARM64). Base from ECR Public's mirror of the official image.
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Amazon RDS certificate bundle: the API verifies the database's certificate
# (sslmode=verify-full), so a man-in-the-middle can't stand in for RDS.
ADD https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /app/rds-global-bundle.pem

# Operating-system security fixes published since the base image was built
# (the first scan found HIGH findings only in Debian packages: glibc, pam,
# sqlite3, util-linux, zlib).
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
 && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin deskville \
 && chmod 0444 /app/rds-global-bundle.pem

COPY app/ ./app/

# Never run as root inside the container.
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--no-server-header"]
