#!/bin/bash
set -e

MUPEN_VERSION="${MUPEN_VERSION:-master}"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"
CROSS=aarch64-linux-gnu

export CC=${CROSS}-gcc
export CXX=${CROSS}-g++
export AR=${CROSS}-ar
export STRIP=${CROSS}-strip
export PKG_CONFIG_PATH=/usr/lib/aarch64-linux-gnu/pkgconfig
export PKG_CONFIG_LIBDIR=/usr/lib/aarch64-linux-gnu/pkgconfig

export OPTFLAGS="-O3 -flto=auto"

APIDIR=/build/core/src/api
export SDL_CFLAGS="$(pkg-config --cflags sdl2)"
export SDL_LDLIBS="$(pkg-config --libs sdl2)"

m64p_make() {
    make -C "$1" CROSS_COMPILE=${CROSS}- HOST_CPU=aarch64 USE_GLES=1 NEW_DYNAREC=1 VULKAN=0 \
        APIDIR="$APIDIR" SDL_CFLAGS="$SDL_CFLAGS" SDL_LDLIBS="$SDL_LDLIBS" \
        OPTFLAGS="$OPTFLAGS" PREFIX="" V=1 -j$(nproc) all
}

echo "=== Building Mupen64Plus for aarch64 ==="

# Clone all components
clone() {
    local repo=$1 dir=$2 ref=${3:-$MUPEN_VERSION}
    if [ ! -d "$dir" ]; then
        git clone --depth 1 --branch "$ref" "https://github.com/$repo.git" "$dir"
    fi
}

clone mupen64plus/mupen64plus-core          core
clone mupen64plus/mupen64plus-ui-console    ui-console
clone mupen64plus/mupen64plus-audio-sdl     audio-sdl
clone mupen64plus/mupen64plus-input-sdl     input-sdl
clone mupen64plus/mupen64plus-rsp-hle       rsp-hle
clone mupen64plus/mupen64plus-video-rice    video-rice
clone mupen64plus/mupen64plus-video-glide64mk2 video-glide64mk2
clone gonetz/GLideN64                       video-gliden64 master

# Apply patches
echo "=== Applying patches ==="
for patch in /patches/common/*.py; do
    [ -f "$patch" ] && python3 "$patch" && echo "Applied: $(basename $patch)"
done

# Build core
echo "=== Building core ==="
m64p_make core/projects/unix

# Build plugins
echo "=== Building plugins ==="
m64p_make audio-sdl/projects/unix
m64p_make input-sdl/projects/unix
m64p_make rsp-hle/projects/unix
m64p_make video-rice/projects/unix
m64p_make video-glide64mk2/projects/unix

# Build GLideN64 (cmake-based)
echo "=== Building GLideN64 ==="
mkdir -p video-gliden64/src/build
cd video-gliden64/src/build
cmake .. \
    -DCMAKE_C_COMPILER=${CROSS}-gcc \
    -DCMAKE_CXX_COMPILER=${CROSS}-g++ \
    -DCMAKE_SYSTEM_NAME=Linux \
    -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
    -DCMAKE_BUILD_TYPE=Release \
    -DMUPENPLUSAPI=ON \
    -DEGL=ON \
    -DUSE_SYSTEM_LIBS=ON \
    -DCMAKE_C_FLAGS="${OPTFLAGS}" \
    -DCMAKE_CXX_FLAGS="${OPTFLAGS}"
make -j$(nproc)
cd /build

# Build frontend
echo "=== Building frontend ==="
m64p_make ui-console/projects/unix

# Collect output
echo "=== Collecting output ==="
mkdir -p "$OUTPUT_DIR"

# Frontend binary
cp ui-console/projects/unix/mupen64plus "$OUTPUT_DIR/"
${STRIP} "$OUTPUT_DIR/mupen64plus"

# Core library
cp core/projects/unix/libmupen64plus.so.2.0.0 "$OUTPUT_DIR/libmupen64plus.so.2"
${STRIP} "$OUTPUT_DIR/libmupen64plus.so.2"

# Plugins
cp audio-sdl/projects/unix/mupen64plus-audio-sdl.so "$OUTPUT_DIR/"
cp input-sdl/projects/unix/mupen64plus-input-sdl.so "$OUTPUT_DIR/"
cp rsp-hle/projects/unix/mupen64plus-rsp-hle.so "$OUTPUT_DIR/"
cp video-rice/projects/unix/mupen64plus-video-rice.so "$OUTPUT_DIR/"
cp video-glide64mk2/projects/unix/mupen64plus-video-glide64mk2.so "$OUTPUT_DIR/"
cp video-gliden64/src/build/plugin/Release/mupen64plus-video-GLideN64.so "$OUTPUT_DIR/"
for so in "$OUTPUT_DIR"/mupen64plus-*.so; do
    ${STRIP} "$so"
done

# Data files
mkdir -p "$OUTPUT_DIR/data"
cp core/data/* "$OUTPUT_DIR/data/"
cp video-rice/data/* "$OUTPUT_DIR/data/"
cp video-glide64mk2/data/* "$OUTPUT_DIR/data/"
cp video-gliden64/ini/* "$OUTPUT_DIR/data/" 2>/dev/null || true

echo "=== Build complete ==="
ls -la "$OUTPUT_DIR/"
