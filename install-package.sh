#! /usr/bin/env sh
set -ex


eval "$(mamba shell hook --shell bash)"


SETUPTOOLS_SCM_PRETEND_VERSION=$(cat "${TAGBIO_PY}"/VERSION.txt)
export SETUPTOOLS_SCM_PRETEND_VERSION

# Using pip to install this package only. For other dependencies, use mamba.
mamba run -n "$(echo $CONDA_DEFAULT_ENV)" pip install -e "${TAGBIO_PY}"
