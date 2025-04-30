.PHONY: test lint coverage clean

test:
	pytest -v tests/

lint:
	flake8 src tests
	black --check src tests
	isort --check-only src tests

coverage:
	pytest --cov=src --cov-report=html --cov-report=term tests/

format:
	black src tests
	isort src tests

clean:
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf coverage_html
	rm -rf .tox
	rm -rf *.egg-info
	rm -rf build
	rm -rf dist
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

install:
	pip install -r requirements.txt
	pip install -r requirements-test.txt

install-dev: install
	pip install -e . 