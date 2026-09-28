# Laya served over the same API as Jev (POST /v1/systemone), on an NVIDIA GPU.
#
# `laya-serve` ships in the `serve` extra of the `laya` package (Apache 2.0). The arena sends
# it exactly the same body it sends to the TypeSafe API; only the URL changes.
ARG PYTHON_IMAGE=python:3.11-slim-bookworm
FROM ${PYTHON_IMAGE}

# cu130 = CUDA 13: any Turing-or-newer GPU with driver >= 580. For CPU: --build-arg TORCH_INDEX=cpu
ARG TORCH_INDEX=cu130
ARG TORCH_VERSION=2.14.0
ARG LAYA_VERSION=0.3.21

# TORCH_DISABLE_NATIVE_JIT: torch 2.14 compiles Triton kernels on the first inference and the
# slim image has no C compiler (laya issue #365). The stock kernels give the same answers.
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TORCH_DISABLE_NATIVE_JIT=1 \
    USE_TF=0 \
    USE_TORCH=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HOME=/models/huggingface \
    LAYA_HOST=0.0.0.0 \
    LAYA_PORT=8000

RUN pip install "torch==${TORCH_VERSION}" --index-url "https://download.pytorch.org/whl/${TORCH_INDEX}" \
 && pip install "laya[serve]==${LAYA_VERSION}" \
 && pip check

RUN useradd --uid 10001 --create-home laya \
 && mkdir -p /models/huggingface \
 && chown -R laya:laya /models
USER laya
WORKDIR /home/laya

EXPOSE 8000
# The first start downloads the checkpoints (~0.8-2.3 GB), hence the long start period.
HEALTHCHECK --interval=5s --timeout=5s --start-period=20m --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["laya-serve"]
