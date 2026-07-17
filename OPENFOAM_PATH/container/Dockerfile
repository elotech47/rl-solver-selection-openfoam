# ESI OpenFOAM v2312 + SUNDIALS (CVODE). LibTorch optional later.
# Build from OPENFOAM_PATH:
#   docker build --platform=linux/amd64 -t of-rl-chem:2312 -f container/Dockerfile .

FROM --platform=linux/amd64 opencfd/openfoam-default:2312

USER root
ENV DEBIAN_FRONTEND=noninteractive

# Avoid flaky SourceForge OpenFOAM apt mirror certs during package install
RUN rm -f /etc/apt/sources.list.d/*openfoam* 2>/dev/null; true

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        wget \
        ca-certificates \
        libopenblas-dev \
        unzip \
    && rm -rf /var/lib/apt/lists/*

ARG SUNDIALS_VERSION=6.7.0
RUN cd /tmp \
 && wget -q https://github.com/LLNL/sundials/releases/download/v${SUNDIALS_VERSION}/sundials-${SUNDIALS_VERSION}.tar.gz \
 && tar xf sundials-${SUNDIALS_VERSION}.tar.gz \
 && cmake -S sundials-${SUNDIALS_VERSION} -B build-sundials \
      -DCMAKE_INSTALL_PREFIX=/opt/sundials \
      -DBUILD_SHARED_LIBS=ON \
      -DENABLE_OPENMP=OFF \
      -DEXAMPLES_ENABLE_C=OFF \
 && cmake --build build-sundials -j"$(nproc)" \
 && cmake --install build-sundials \
 && rm -rf /tmp/sundials-* /tmp/build-sundials

ENV SUNDIALS_DIR=/opt/sundials
ENV LD_LIBRARY_PATH=/opt/sundials/lib:/opt/sundials/lib64:${LD_LIBRARY_PATH}

WORKDIR /work
ENV WM_PROJECT_USER_DIR=/home/openfoam/OpenFOAM

CMD ["/bin/bash"]
