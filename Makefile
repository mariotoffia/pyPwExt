clean:
	@pip freeze | xargs pip uninstall -y
	@rm -f requirements/detected.txt
#	@find . -name __pycache__ -exec rm -rf {} \;
lint:
	@python -m flake8 pypwext --count --show-source --statistics
#	@python -m flake8 pypwext --count --exit-zero --max-complexity=10 --max-line-length=180 --statistics
#	@python -m mypy pypwext
test:
# --doctest-modules 
	@python -m pytest tests --junitxml=junit/test-results.xml --cov=pypwext --cov-report=xml --cov-report=html
dev-dependencies:
	@python -m pip install --upgrade pip
	@pip install -r requirements/dev.txt
build-dependencies:
	@python -m pip install --upgrade pip
	@pip install -r requirements/build.txt
build:
	@rm -rf README.rst
	@cp README.md pypwext
	@python tools/versions.py
	@python -m build
	@rm -rf pypwext/README.md
publish:
	@python -m twine upload dist/* --config-file ./.pypirc
freeze:
	@pip freeze > requirements/detected.txt
update:
	@pip install -U pip
stats:
	@scc . --cocomo-project-type=organic --include-ext=py,adoc,md \
		--exclude-dir=.git,_output,node_modules,.venv,.pytest_cahce,.mypy_cache,.tox,__pycache__,.vscode,__pycache__