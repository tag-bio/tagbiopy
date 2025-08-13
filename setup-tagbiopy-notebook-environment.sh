#!/usr/bin/env bash
set -ex


eval "$(mamba shell hook --shell bash)"

# CREATE TAGBIOPY NOTEBOOK ENVIRONMENT
mamba create -n tagbiopy-notebook

# ADD PYTHON DEPENDENCIES
mamba env update -n tagbiopy-notebook -f "${TAGBIO_PY}"/environment.yml

# INSTALL TAGBIO PYTHON SDK
SETUPTOOLS_SCM_PRETEND_VERSION=$(cat "${TAGBIO_PY}"/VERSION.txt)
export SETUPTOOLS_SCM_PRETEND_VERSION

mamba run -n tagbiopy-notebook pip install -e "${TAGBIO_PY}" --root-user-action=ignore

mamba activate tagbiopy-notebook
