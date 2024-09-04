#!/usr/bin/env bash
set -ex

mamba init bash
source /root/.bashrc

# CREATE TAGBIOPY-SPECIFIC NOTEBOOK
mamba create -n tagbiopy-notebook
mamba activate tagbiopy-notebook

# ADD PYTHON DEPENDENCIES
mamba env update -n $(echo $CONDA_DEFAULT_ENV) -f ${TAGBIO_PY}/environment.yml

# INSTALL PYTHON SDK
export SETUPTOOLS_SCM_PRETEND_VERSION=$(cat ${TAGBIO_PY}/VERSION.txt) && mamba run -n $(echo $CONDA_DEFAULT_ENV) pip install -e "${TAGBIO_PY}" --root-user-action=ignore
