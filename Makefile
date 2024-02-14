# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE


# Download python-build
define WGET
ifeq '$$(wildcard $(notdir $(1)))' ''
$$(info Downloading $(notdir $(1)))
_WGET := $$(shell $(call WGET_CMD, $(1)))
endif
endef
WGET_CMD = if which wget; then wget -q -c $(1); else curl -f -Os $(1); fi
$(eval $(call WGET, https://raw.githubusercontent.com/craigahobbs/python-build/main/Makefile.base))
$(eval $(call WGET, https://raw.githubusercontent.com/craigahobbs/python-build/main/pylintrc))


# Sphinx documentation directory
SPHINX_DOC := doc


# Include python-build
include Makefile.base


help:
	@echo "            [perf]"


clean:
	rm -rf Makefile.base pylintrc


doc:
    # Copy statics
	cp -R static/* build/doc/html

    # Generate the library documentation
	$(DEFAULT_VENV_CMD)/baredoc src/bare_script/library.py -o build/doc/html/library/library.json

    # Generate the expression library documentation
	$(DEFAULT_VENV_PYTHON) -c "$$DOC_EXPR_PY" build/doc/html/library/library.json build/doc/html/library/expression.json

    # Generate the library model documentation
	$(DEFAULT_VENV_PYTHON) -c "$$DOC_LIBRARY_MODEL_PY" build/doc/html/library/model.json

    # Generate the runtime model documentation
	$(DEFAULT_VENV_PYTHON) -c "$$DOC_RUNTIME_MODEL_PY" build/doc/html/model/model.json


# Python to generate the expression library documentation
define DOC_EXPR_PY
import json
import sys
from bare_script.library import EXPRESSION_FUNCTION_MAP

# Read the script library documentation model
with open(sys.argv[1], 'r', encoding='utf-8') as fh:
	library = json.load(fh)

# Create the expression documentation model
library_map = dict((func['name'], func) for func in library['functions'])
expression = {'functions': [dict(library_map[lib_name], name=expr_name) for expr_name, lib_name in EXPRESSION_FUNCTION_MAP.items()]}

# Write the expression documentation model
with open(sys.argv[2], 'w', encoding='utf-8') as fh:
	json.dump(expression, fh, separators=(',', ':'), sort_keys=True)
endef
export DOC_EXPR_PY


# Python to generate the library type model
define DOC_LIBRARY_MODEL_PY
import json
import sys
from bare_script.library import REGEX_MATCH_TYPES, SYSTEM_FETCH_TYPES

# Create the library type model
types = {**REGEX_MATCH_TYPES, **SYSTEM_FETCH_TYPES}

# Write the library type model
with open(sys.argv[1], 'w', encoding='utf-8') as fh:
	json.dump(types, fh, separators=(',', ':'), sort_keys=True)
endef
export DOC_LIBRARY_MODEL_PY


# Python to generate the runtime type model
define DOC_RUNTIME_MODEL_PY
import json
import sys
from bare_script.model import BARE_SCRIPT_TYPES

# Write the runtime type model
with open(sys.argv[1], 'w', encoding='utf-8') as fh:
	json.dump(BARE_SCRIPT_TYPES, fh, separators=(',', ':'), sort_keys=True)
endef
export DOC_RUNTIME_MODEL_PY


# Run performance tests
.PHONY: perf
perf: $(DEFAULT_VENV_BUILD)
	mkdir -p $(dir $(PERF_JSON))
	echo "[" > $(PERF_JSON)
	for X in $$(seq 1 $(PERF_RUNS)); do echo '{"language": "BareScript", "timeMs": '$$($(DEFAULT_VENV_CMD)/bare perf/test.bare)'},' >> $(PERF_JSON); done
	for X in $$(seq 1 $(PERF_RUNS)); do echo '{"language": "Python", "timeMs": '$$($(DEFAULT_VENV_PYTHON) perf/test.py)'},' >> $(PERF_JSON); done
	echo '{}' >> $(PERF_JSON)
	echo "]" >> $(PERF_JSON)
	$(DEFAULT_VENV_PYTHON) -c "$$PERF_PY"


# Performance test constants
PERF_JSON := build/perf.json
PERF_RUNS := 3


# Python to report on performance test data
define PERF_PY
import json

# Read the performance test data
with open('$(PERF_JSON)', 'r', encoding='utf-8') as fh:
	timings = json.load(fh)

# Compute the best time for each language
best_timings = {}
for language, time_ms in ((timing.get('language'), timing.get('timeMs')) for timing in timings):
	if language is not None and (language not in best_timings or time_ms < best_timings[language]):
		best_timings[language] = time_ms

# Report the timing multiples
for language, time_ms in sorted(best_timings.items(), key=lambda val: val[1]):
	report = f'{language} - {time_ms:.1f} milliseconds'
	print(report if language == 'BareScript' else f'{report} ({best_timings["BareScript"] / time_ms:.1f}x)')
endef
export PERF_PY
