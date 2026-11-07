.PHONY: lint-brazil test-brazil check-brazil lint-eulr test-eulr check-eulr lint-assessment test-assessment assess-portfolio lint-all test-all

lint-brazil:
	$(MAKE) -C brazil-power-v13 lint

test-brazil:
	$(MAKE) -C brazil-power-v13 test

check-brazil: lint-brazil test-brazil

lint-eulr:
	$(MAKE) -C Eulr lint

test-eulr:
	$(MAKE) -C Eulr test

check-eulr: lint-eulr test-eulr

lint-assessment:
	$(MAKE) -C portfolio-assessment lint

test-assessment:
	$(MAKE) -C portfolio-assessment test

assess-portfolio:
	$(MAKE) -C portfolio-assessment run

lint-all: lint-brazil lint-eulr lint-assessment

test-all: test-brazil test-eulr test-assessment
