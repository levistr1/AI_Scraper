#! /bin/bash


set -e


# Create virtual environment if it doesn't exist
if [ ! -d "env" ]; then
    python3 -m venv env
else
    echo "Virtual environment already exists"
fi

# Activate
source env/bin/activate

# Install requirements
pip install -r requirements.txt

# Install playwright
python -m playwright install