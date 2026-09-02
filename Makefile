.PHONY: install test doctor serve npm srcinfo publish-pypi publish-npm clean

install:      ## create the venv and install cirax (uv)
	uv sync

test:         ## run the smoke suite
	uv run bash tests/smoke.sh

doctor:       ## report engine capability matrix
	uv run cirax doctor --show-missing

serve:        ## local web UI on http://127.0.0.1:8400
	uv run cirax serve

npm:          ## test the npm wrapper from a git checkout
	cd npm && npm install --no-fund --no-audit && ./node_modules/.bin/cirax --version

srcinfo:      ## regenerate AUR .SRCINFO
	cd packaging && makepkg --printsrcinfo > .SRCINFO

publish-pypi: ## build and publish to PyPI (needs UV_PUBLISH_TOKEN)
	uv build && uv publish

publish-npm:  ## bundle python source and publish the npm wrapper (needs npm login)
	cd npm && npm run build:python && npm publish

clean:
	rm -rf .venv dist build npm/python npm/.venv npm/node_modules
