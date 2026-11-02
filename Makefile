.PHONY: lint-brazil test-brazil check-brazil lint-all test-all

lint-brazil:
	$(MAKE) -C brazil-power-v13 lint

test-brazil:
	$(MAKE) -C brazil-power-v13 test

check-brazil: lint-brazil test-brazil

lint-all: lint-brazil

test-all: test-brazil
