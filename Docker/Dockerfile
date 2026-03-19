FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && \
    apt-get install -y \
    git \
    perl \
    python3 \
    make \
    autoconf \
    g++ \
    flex \
    bison \
    ccache \
    libgoogle-perftools-dev \
    numactl \
    perl-doc \
    help2man && \
    rm -rf /var/lib/apt/lists/*

# Build Verilator from source
ARG VERILATOR_VERSION=v5.024
RUN git clone https://github.com/verilator/verilator.git /tmp/verilator && \
    cd /tmp/verilator && \
    git checkout ${VERILATOR_VERSION} && \
    autoconf && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    cd / && \
    rm -rf /tmp/verilator

# Verify installation
RUN verilator --version

WORKDIR /workspace

CMD ["verilator", "--version"]