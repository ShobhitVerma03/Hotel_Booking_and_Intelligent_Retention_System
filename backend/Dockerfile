# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    HF_HOME=/opt/huggingface \
    HF_HUB_DISABLE_XET=1

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
# Sentence Transformers requires Torch.  Install the official CPU wheel before
# resolving the rest so Docker does not pull CUDA libraries for a local CPU
# deployment.
# BuildKit's cache survives an interrupted image build, but is not copied into
# the final layer.  This is particularly important for the real CPU Torch
# wheel, which sentence-transformers requires for RAG embeddings.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --cache-dir=/root/.cache/pip --upgrade pip \
    && pip install --cache-dir=/root/.cache/pip --index-url https://download.pytorch.org/whl/cpu torch==2.7.1+cpu

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --cache-dir=/root/.cache/pip -r /tmp/requirements.txt

# Bake the approved real embedding model into the image. Xet transport is
# disabled above for environments that allow ordinary HTTPS but block Xet.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# The Docker context is the repository root so that the trusted policy PDF can
# be copied without exposing it through an HTTP route.
COPY backend /app/backend
COPY data/policy /app/data/policy
COPY docker/backend-entrypoint.sh /app/docker/backend-entrypoint.sh
RUN sed -i 's/\r$//' /app/docker/backend-entrypoint.sh \
    && chmod +x /app/docker/backend-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker/backend-entrypoint.sh"]
CMD []
