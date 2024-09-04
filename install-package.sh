#! /usr/bin/env sh
set -ex


# Using pip to install this package only. For other dependencies, use mamba.
export SETUPTOOLS_SCM_PRETEND_VERSION=$(cat ${TAGBIO_PY}/VERSION.txt) && mamba run -n $(echo $CONDA_DEFAULT_ENV) pip install -e "${TAGBIO_PY}"
