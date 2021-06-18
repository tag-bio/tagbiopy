#! /usr/bin/env sh
set -ex

conda install -c conda-forge python=3.8 pip
python -V
pip --version

conda clean --all -y
apt-get clean -y
apt-get autoremove -y
