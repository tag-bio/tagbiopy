# tagbiopy: Python SDK and API wrapper for tag.bio integration #

## What is this repository for? ###

The purpose of this project is to provide a python interface for exploratory analyses of data 
on tag.bio platform from the comfort of a jupyter notebook.

## Set up ###

The recommended way of installing the package is in a 
[python virtual environment](https://realpython.com/python-virtual-environments-a-primer/).
This document provides details of how the development environment was set up in which
this code and the examples in the `ipy` directory work.

To avoid dependence on a particular version of python3, [pyenv](https://github.com/pyenv/pyenv)
has been used as the preferred way of setting it once and forgetting it. 
In addition, a dedicated jupyter kernel was also prepared using the same virtual
environment.

### pyenv setup

1. On macOS, install [pyenv](https://github.com/pyenv/pyenv#installation) with [brew](https://brew.sh).

```bash
brew update
brew install pyenv
```

2. Add the following to your `.bashrc` or `.bash_profile`:

```bash
eval "$(pyenv init -)"
if command -v pyenv 1>/dev/null 2>&1; then
  eval "$(pyenv init -)"
fi
```
The purpose of the `if` block is to graciously avoid the eval initialization
in case *pyenv* is not already available in your path.  

Please make sure this command is placed toward the end of the shell configuration file since 
it manipulates PATH during the initialization. Your very last line in `.bashrc`  may as well be
a command that manipulates or sets the PATH as in

```bash
export PATH=${HOME}/bin:${PATH}
```

3. Install your preferred python version with pyenv. Building from source is straightforward 
   provided your mac has already been prepared as a development machine with Xcode Command Line Tools 
   (i.e. `xcode-select --install`). To be on the 
   [safe side](https://github.com/pyenv/pyenv/wiki#suggested-build-environment), you can also execute
   
```bash
brew install openssl readline sqlite3 xz zlib
```
   
You can list the available versions of python with the following command:

```bash
pyenv install --list
Available versions:
  ...
  3.4.10
  3.5.10
  3.6.12
  3.7.9
  3.8.6
  3.9.0
  ...
```

Note that we show 

* Summary of set up
* Configuration
* Dependencies
* Database configuration
* How to run tests
* Deployment instructions

### Contribution guidelines ###

* Writing tests
* Code review
* Other guidelines

### Who do I talk to? ###

* Repo owner or admin
* Other community or team contact

