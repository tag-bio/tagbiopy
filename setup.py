#!/usr/bin/env python

import os
import setuptools


BASE_URL = 'https://bitbucket.org/protocolbuilders'
NAME = 'tagbiopy'


def install_requirements():
    ret = []
    with open('./requirements.txt') as fh:
        for line in fh:
            ret.append(line.strip())
    return ret


setuptools.setup(
    name=NAME,
    version='0.0.6',
    description='Provides tag.bio python SDK.',
    url=os.path.join(BASE_URL, NAME),
    author='D',
    author_email='info@tag.bio',
    license='Proprietary',
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: Proprietary",
        "Programming Language :: Python :: 3.6",
    ],
    keywords='utilities',
    test_suite='nose.collector',
    tests_require=['nose'],
    scripts=[
        os.path.join(NAME, 'bin/connect_tagbio_py')
    ],
    install_requires=install_requirements(),
    packages=setuptools.find_packages()
)
