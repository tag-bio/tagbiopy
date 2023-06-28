#! /usr/bin/env sh
set -ex


echo "*** Building tagbio python library in dev mode in ${TAGBIO_PY}"

# Use pip to install this SDK only. For dependencies use conda install
conda run -n base pip install -e "${TAGBIO_PY}"

apt-get clean -y
apt-get autoremove -y
