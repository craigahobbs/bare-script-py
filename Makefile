# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script/blob/main/LICENSE

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
COVERAGE_REPORT_ARGS ?= --fail-under 89

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
