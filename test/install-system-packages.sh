#!/usr/bin/env bash
set -ex

apt-get update && apt-get upgrade -y

echo "
*********************************
Install Compiler and System Stuff
*********************************
"
# Taken from original install-conda.sh,
#  the Dockerfile of this repo,
#  Tag.bio Dev containers,
#  and individual FCs
apt-get install --yes \
  apt-utils \
  bash-completion \
  build-essential \
  curl \
  gcc-multilib \
  git \
  gpg \
  iputils-ping \
  nano \
  openjdk-11-jdk \
  pandoc \
  procps \
  rsync \
  vim \
  wget \
  zlib1g-dev


# Taken from Tagbio.R install.sh
apt-get install --yes \
  libcairo2-dev \
  libcurl4-openssl-dev \
  libfontconfig1-dev \
  libssl-dev \
  libxml2-dev \
  libxt-dev
