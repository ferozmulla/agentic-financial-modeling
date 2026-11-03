.PHONY: lint-brazil test-brazil check-brazil lint-assessment test-assessment assess-portfolio lint-all test-all

lint-brazil:
	$(MAKE) -C brazil-power-v13 lint

test-brazil:
	$(MAKE) -C brazil-power-v13 test

check-brazil: lint-brazil test-brazil

lint-assessment:
	$(MAKE) -C portfolio-assessment lint

test-assessment:
	$(MAKE) -C portfolio-assessment test

assess-portfolio:
	$(MAKE) -C portfolio-assessment run

lint-all: lint-brazil lint-assessment

test-all: test-brazil test-assessment
