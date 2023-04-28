#! /usr/bin/env sh
set -ex

SCRIPT_DIR="$(dirname $(realpath $0))"
echo "**** 0=$0"
echo "**** realpath=$(realpath $0)"
echo "**** dirname realpath=$(dirname $(realpath $0) )"
echo "**** SCRIPT_DIR=$SCRIPT_DIR"

echo "*** Building tagbio python library in dev mode"
#cd "$SCRIPT_DIR"
#python setup.py sdist
#
#echo "*** Installing tagbio python library to $SCRIPT_DIR"
#pip install -r ./requirements.txt
#pip install $SCRIPT_DIR/dist/*


conda run -n base pip install -e $SCRIPT_DIR

# Use environment to install
# conda env update -f ${SCRIPT_DIR}/environment.yml

conda install -c conda-forge pyyaml 

apt-get clean -y
apt-get autoremove -y
