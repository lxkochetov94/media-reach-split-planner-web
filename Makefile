PYTHON ?= python3
PORT ?= 8000

.PHONY: check check-legacy check-reach syntax-python syntax-js test-legacy test-reach \
        verify-embedded rebuild-embedded guard-reach-surface docs-check serve

check: syntax-python syntax-js test-legacy test-reach verify-embedded docs-check

check-legacy: syntax-python test-legacy verify-embedded

check-reach: syntax-python syntax-js test-reach docs-check

syntax-python:
	PYTHONPATH=.debug_sources:. $(PYTHON) -m py_compile \
		.debug_sources/engine.py \
		.debug_sources/web_api.py \
		.debug_sources/xlsx_reader.py \
		.debug_sources/splits.py \
		reach_v16_math.py \
		reach_v16.py \
		test_reach_v16_math.py \
		test_reach_v16.py \
		test_reach_v16_final_ux.py \
		test_reach_v16_lab_fixture.py \
		test_reach_v16_persil_battle.py \
		test_reach_v16_template_battle.py

syntax-js:
	node --check reach_v16.js

test-legacy:
	PYTHONPATH=.debug_sources:. $(PYTHON) -m unittest -v \
		test_reach_engine \
		test_web_api \
		test_splits_core \
		test_xlsx_reader

test-reach:
	PYTHONPATH=.debug_sources:. $(PYTHON) -m unittest -v \
		test_reach_v16_math \
		test_reach_v16 \
		test_reach_v16_final_ux \
		test_reach_v16_lab_fixture \
		test_reach_v16_persil_battle \
		test_reach_v16_template_battle

verify-embedded:
	$(PYTHON) scripts/verify_embedded.py

rebuild-embedded:
	$(PYTHON) scripts/rebuild_embedded.py

guard-reach-surface:
	$(PYTHON) scripts/guard_reach_surface.py --base origin/main --head HEAD

docs-check:
	$(PYTHON) scripts/docs_check.py

serve:
	$(PYTHON) -m http.server $(PORT)
