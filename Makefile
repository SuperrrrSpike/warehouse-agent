PYTHON := .venv/bin/python
PIP := .venv/bin/pip
MIRROR := https://pypi.tuna.tsinghua.edu.cn/simple

.PHONY: setup download prepare train score dashboard ml test validate validate-model

setup:
	python3 -m venv .venv
	$(PIP) install -i $(MIRROR) -r requirements.txt

download:
	$(PYTHON) scripts/download_real_dataset.py

prepare:
	$(PYTHON) main.py prepare-real-data

train:
	$(PYTHON) main.py train-model

score:
	$(PYTHON) main.py score-waves

dashboard:
	$(PYTHON) main.py ml-dashboard

ml:
	$(PYTHON) main.py ml-pipeline

test:
	$(PYTHON) -m unittest discover -v
	$(PYTHON) -m compileall -q main.py warehouse_agent tests

validate:
	$(PYTHON) main.py validate

validate-model:
	$(PYTHON) main.py validate-model
