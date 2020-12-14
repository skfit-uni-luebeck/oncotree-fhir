#!/bin/bash

output="./output"
venvs_dir="$HOME/.venvs"
venv_dir="$venvs_dir/oncotree-fhir"

if [ ! $(uname) == "Darwin" -a ! $(uname) == "Linux" ]
then
  echo "This script is only supported on Linux and MacOS"
  exit 1
fi

if [ ! -d $output ]
then
  mkdir $output
  echo "created directory '$output' in working directory $(pwd)"
fi

if [ ! -d $venvs_dir ]
then
  mkdir $venvs_dir
  echo "created virtual environment parent directory in $venvs_dir"
fi

if [ ! $(which python3) ]
then
  echo "the program python3 could not be found!"
  exit 1
fi

if [ ! -d $venv_dir ]
then
  python3 -m venv $venv_dir
  echo "virtual environment created in $venv_dir"
fi

source "$venv_dir/bin/activate"
echo "virtual environment activated"
echo "installing dependencies, this may take a while..."
pip -q --log "pip-log.txt" install -r "requirements.txt"
echo "dependencies installed"

echo ""
echo "running convert-all process"

cmdline="python oncotree-fhir.py --output=output/\$version.json --write-tsv --tsv-output=./output/\$version.tsv convert-all"
echo "command line: $cmdline"
$cmdline
