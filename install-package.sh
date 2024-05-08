#! /usr/bin/env sh
set -ex


export SETUPTOOLS_SCM_PRETEND_VERSION=$(git describe --abbrev=0 --tags --always)

echo "*** Building tagbio python library in dev mode in ${TAGBIO_PY}"

# Use pip to install this SDK only. For dependencies use conda install
mamba run -n base pip install -e "${TAGBIO_PY}"
