#! /usr/bin/env sh
set -ex

mamba install -y -c conda-forge python=3.8 pip
python -V
pip --version

mamba clean --all -y
apt-get clean -y
apt-get autoremove -y
