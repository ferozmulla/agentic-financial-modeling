.PHONY: lint-brazil test-brazil check-brazil lint-eulr test-eulr check-eulr lint-assessment test-assessment assess-portfolio lint-onboarding test-onboarding check-onboarding lint-all test-all

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

lint-onboarding:
	$(MAKE) -C model-onboarding lint

test-onboarding:
	$(MAKE) -C model-onboarding test

check-onboarding: lint-onboarding test-onboarding

lint-all: lint-brazil lint-eulr lint-assessment lint-onboarding

test-all: test-brazil test-eulr test-assessment test-onboarding
