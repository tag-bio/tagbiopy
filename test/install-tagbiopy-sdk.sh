#!/usr/bin/env bash
set -ex


echo "
*****************************
Installing Tag.bio Python SDK
***     pip is $(which pip)    ***
***     conda is $(which conda)    ***
*****************************
"
mamba env update -f "${TAGBIO_PY}"/environment.yml
mamba run -n base "${TAGBIO_PY}"/install-package.sh