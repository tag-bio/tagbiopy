#! /usr/bin/env sh
set -ex


export SETUPTOOLS_SCM_PRETEND_VERSION=$(cat ${TAGBIO_PY}/VERSION.txt)

echo "*** Building tagbio python library in dev mode in ${TAGBIO_PY}"

# Use pip to install this SDK only. For dependencies use conda install
mamba run -n base pip install -e "${TAGBIO_PY}"
