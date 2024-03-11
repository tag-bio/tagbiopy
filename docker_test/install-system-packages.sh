#!/usr/bin/env bash
set -ex

apt-get update > /dev/null
apt-get upgrade --yes

echo "
*********************************
Install Compiler and System Stuff
*********************************
"
apt-get install --yes --no-install-recommends \
  apt-transport-https \
  apt-utils \
  awscli \
  bash-completion \
  ca-certificates \
  git \
  gpg \
  less \
  libcairo2-dev \
  libcurl4-openssl-dev \
  libfontconfig1-dev \
  libssl-dev \
  libxml2-dev \
  libxt-dev \
  nano \
  openssh-client \
  pandoc \
  procps \
  rsync \
  screen \
  vim \
  wget \
  zlib1g-dev \
  > /dev/null
