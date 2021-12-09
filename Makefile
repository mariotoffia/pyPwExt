clean:
	@find . -name __pycache__ -exec rm -rf {} \;
	@rm noodlemagazine.spec
lint:
	@python -m flake8 pypwext
	@python -m mypy pypwext
test:
# --doctest-modules 
	@pip install pytest-cov
	@python -m pytest tests --junitxml=junit/test-results.xml --cov=pypwext --cov-report=xml --cov-report=html
dependencies:
	@python -m pip install --upgrade pip setuptools wheel
	@pip install -r requirements/requirements.txt
build:
	@python -m build
publish:
	@python -m twine upload dist/* --config-file ./.pypirc
freeze:
	@mkdir -p requirements
	@pip freeze > requirements/requirements.txt
update:
	@pip install -U pip
stats:
	@scc . --cocomo-project-type=organic --include-ext=py,adoc,md \
		--exclude-dir=.git,_output,node_modules,.venv,.pytest_cahce,.mypy_cache,.tox,__pycache__,.vscode,__pycache__