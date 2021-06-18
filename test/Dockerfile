FROM jupyter/datascience-notebook:lab-2.2.9

ENV DEBIAN_FRONTEND noninteractive

USER root

# update apt & conda base packages
RUN apt-get update -y && apt-get upgrade -y
RUN conda update --all -y

# Installing R component
ENV TAGBIO_PY /tagbiopy
COPY . /tagbiopy
RUN /tagbiopy/install-package.sh

# run test script
SHELL ["/opt/conda/condabin/conda", "run", "-n", "base", "/bin/bash", "-c"]
RUN sh -c 'which connect_tagbio_py'
RUN python /tagbiopy/test/test-in-docker.py

USER jovyan

