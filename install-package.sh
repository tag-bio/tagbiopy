#! /usr/bin/env sh
set -ex


echo "*** Building tagbio python library in dev mode in ${TAGBIO_PY}"

#conda env update -f ${SCRIPT_DIR}/environment.yml

# Tue Jun 27 11:08:42 PDT 2023
# To use tagbiopy as a package under pip, no dependencies in setup.cfg
conda run -n base pip install -e "${TAGBIO_PY}"
#pip install -e "${TAGBIO_PY}"

apt-get clean -y
apt-get autoremove -y
