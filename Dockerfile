FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Configure multiarch for arm64 cross-compilation
RUN dpkg --add-architecture arm64 && \
    sed -i 's/^deb http/deb [arch=amd64] http/g' /etc/apt/sources.list && \
    echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal-updates main restricted universe multiverse" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    gcc-10-aarch64-linux-gnu \
    g++-10-aarch64-linux-gnu \
    pkg-config \
    git \
    ca-certificates \
    python3 \
    nasm \
    ccache \
    libsdl2-dev:arm64 \
    libsdl2-ttf-dev:arm64 \
    libasound2-dev:arm64 \
    libfreetype6-dev:arm64 \
    libgles2-mesa-dev:arm64 \
    libegl1-mesa-dev:arm64 \
    libpng-dev:arm64 \
    zlib1g-dev:arm64 \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install \
    /usr/bin/aarch64-linux-gnu-gcc aarch64-linux-gnu-gcc \
    /usr/bin/aarch64-linux-gnu-gcc-10 10 \
    --slave \
    /usr/bin/aarch64-linux-gnu-g++ aarch64-linux-gnu-g++ \
    /usr/bin/aarch64-linux-gnu-g++-10 \
    --slave \
    /usr/bin/aarch64-linux-gnu-gcc-ar aarch64-linux-gnu-gcc-ar \
    /usr/bin/aarch64-linux-gnu-gcc-ar-10 \
    --slave \
    /usr/bin/aarch64-linux-gnu-gcc-nm aarch64-linux-gnu-gcc-nm \
    /usr/bin/aarch64-linux-gnu-gcc-nm-10 \
    --slave \
    /usr/bin/aarch64-linux-gnu-gcc-ranlib aarch64-linux-gnu-gcc-ranlib \
    /usr/bin/aarch64-linux-gnu-gcc-ranlib-10

COPY build.sh /build.sh
RUN chmod +x /build.sh
COPY patches/ /patches/
COPY overlay/ /overlay/

WORKDIR /build
ENTRYPOINT ["/build.sh"]
