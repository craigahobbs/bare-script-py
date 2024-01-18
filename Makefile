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

# Loosen coverage requirements for initial porting work
COVERAGE_REPORT_ARGS ?= --fail-under 90

# Include python-build
include Makefile.base

clean:
	rm -rf Makefile.base pylintrc

doc:
    # Copy statics
	cp -R static/* build/doc/html

    # Generate the library documentation
	if ! $(DEFAULT_VENV_CMD)/baredoc src/bare_script/library.py > build/doc/html/library/library.json; \
		then cat build/doc/html/library/library.json; exit 1; \
	fi

    # Generate the expression library documentation
	cat build/doc/html/library/library.json | \
		$(DEFAULT_VENV_CMD)/python3 -c "$$DOC_EXPR_PY" > build/doc/html/library/expression.json

    # Generate the library model documentation
	$(DEFAULT_VENV_CMD)/python3 -c "$$DOC_LIBRARY_MODEL_PY" > build/doc/html/library/model.json

    # Generate the runtime model documentation
	$(DEFAULT_VENV_CMD)/python3 \
		-c "import json; from bare_script.model import BARE_SCRIPT_TYPES; print(json.dumps(BARE_SCRIPT_TYPES))" \
		> build/doc/html/model/model.json


# Python to generate the expression library documentation
define DOC_EXPR_PY
import json
import sys
from bare_script.library import EXPRESSION_FUNCTION_MAP

# Read the script library documentation JSON from stdin
library = json.load(sys.stdin)
library_function_map = dict((func['name'], func) for func in library['functions'])

# Output the expression library documentation
library_expr = {'functions': []}
for expr_fn_name, script_fn_name in EXPRESSION_FUNCTION_MAP.items():
	library_expr['functions'].append(dict(library_function_map[script_fn_name], name=expr_fn_name))

print(json.dumps(library_expr, indent=4))
endef
export DOC_EXPR_PY


# Python to generate the library model documentation
define DOC_LIBRARY_MODEL_PY
import json
from bare_script.library import FETCH_TYPES
print(json.dumps(FETCH_TYPES, indent=4))
endef
export DOC_LIBRARY_MODEL_PY
