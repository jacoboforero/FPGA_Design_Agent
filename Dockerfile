FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG VERILATOR_VERSION=5.044

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf \
    bison \
    build-essential \
    ca-certificates \
    curl \
    flex \
    gperf \
    help2man \
    iverilog \
    libfl-dev \
    nano \
    perl \
    pkg-config \
    python3 \
    python3-pip \
    python3-venv \
    pipx \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://github.com/verilator/verilator/archive/refs/tags/v${VERILATOR_VERSION}.tar.gz" \
    | tar -xz -C /tmp \
    && cd "/tmp/verilator-${VERILATOR_VERSION}" \
    && autoconf \
    && ./configure --prefix=/opt/verilator \
    && make -j"$(nproc)" \
    && make install \
    && rm -rf "/tmp/verilator-${VERILATOR_VERSION}"

ENV VERILATOR_ROOT=/opt/verilator
ENV PATH="/opt/verilator/bin:/root/.local/bin:${PATH}"

RUN pipx install poetry==1.8.3

WORKDIR /workspace
