#!/bin/bash

# The following works only if you used pyenv to create a virtualenv in which this package
# is installed

export PYENV_VERSION=fcpy

fc_packet=$1
user_function=$2
output_file=$3
extension=$4

while getopts d:f:o:t: flag
do
    case "${flag}" in
        d) fc_packet=${OPTARG};;
        f) user_function=${OPTARG};;
        o) output_file=${OPTARG};;
        t) extension=${OPTARG};;
    esac
done

#if $debug; then
#  echo "fc_packet: ${fc_packet}";
#  echo "user_function: ${user_function}";
#  echo "output_file: ${output_file}";
#  echo "extension: ${extension}";
#  echo environment: $(env)
#fi

connect_tagbio_py -d ${fc_packet} -f ${user_function} -o ${output_file} -t ${extension}

unset PYENV_VERSION