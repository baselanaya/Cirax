.PHONY: install test doctor npm clean

install:      ## create the venv and install cirax (uv)
	uv sync

test:         ## run the smoke suite
	uv run bash tests/smoke.sh

doctor:       ## report engine capability matrix
	uv run cirax doctor --show-missing

npm:          ## test the npm wrapper from a git checkout
	cd npm && npm install --no-fund --no-audit && ./node_modules/.bin/cirax --version

publish-npm:  ## bundle python source and publish the npm wrapper
	cd npm && npm run build:python && npm publish

clean:
	rm -rf .venv dist npm/python npm/.venv npm/node_modules
