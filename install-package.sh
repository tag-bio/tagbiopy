#! /usr/bin/env sh
set -ex

SCRIPT_DIR="$(dirname $(realpath $0))"
echo "**** 0=$0"
echo "**** realpath=$(realpath $0)"
echo "**** dirname realpath=$(dirname $(realpath $0) )"
echo "**** SCRIPT_DIR=$SCRIPT_DIR"

echo "*** Building tagbio python library in dev mode"

conda env update -f ${SCRIPT_DIR}/environment.yml

# Tue Jun 27 11:08:42 PDT 2023
# To use tagbiopy as a package under pip, no dependencies in setup.cfg
conda run -n base pip install -e $SCRIPT_DIR

apt-get clean -y
apt-get autoremove -y
