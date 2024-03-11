# syntax=docker/dockerfile:1
ARG JUPYTER_IMAGE_VERSION=lab-3.4.3

FROM jupyter/datascience-notebook:${JUPYTER_IMAGE_VERSION}

ENV TAGBIO_PY /tagbiopy
ENV DEBIAN_FRONTEND noninteractive

COPY . /$TAGBIO_PY

USER root
SHELL ["/usr/bin/bash", "-c"]

# Install system-level packages
# Install Tag.bio SDK \
RUN install-system-packages.sh && \
  install-tagbiopy-sdk.sh

USER jovyan

# Run test script
RUN python $TAGBIO_PY/test/test-in-docker.py
