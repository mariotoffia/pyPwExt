clean:
	@find . -name __pycache__ -exec rm -rf {} \;
	@rm noodlemagazine.spec
lint:
	@python -m flake8 pypwext
	@python -m mypy pypwext
dependencies:
	@pip install -r requirements/requirements.txt
freeze:
	@mkdir -p requirements
	@pip freeze > requirements/requirements.txt
update:
	@pip install -U pip
import:
	@python fetch.py -b bm.html -p "Bookmarks bar/nm"