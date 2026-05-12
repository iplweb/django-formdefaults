.PHONY: messages messages-pkg messages-example compilemessages compilemessages-pkg compilemessages-example

# Two separate translation catalogs live in this repo:
#   src/formdefaults/locale/        -> shipped in the wheel/sdist
#   example_project/demo/locale/    -> demo-only, NEVER shipped
#
# They MUST stay separated. Each target below runs makemessages from the right
# cwd so xgettext only sees that scope's source files. Never run
# `django-admin makemessages` from the repo root — it would harvest demo
# strings into the published catalog.

# LOCALE (not LANG — that name clashes with the shell's $LANG env var, which
# Make inherits and would silently override a default of `pl`).
LOCALE ?= pl

messages: messages-pkg messages-example

messages-pkg:
	cd src/formdefaults && django-admin makemessages -l $(LOCALE) --no-obsolete

messages-example:
	cd example_project && python manage.py makemessages -l $(LOCALE) --no-obsolete

compilemessages: compilemessages-pkg compilemessages-example

compilemessages-pkg:
	cd src/formdefaults && django-admin compilemessages

compilemessages-example:
	cd example_project && python manage.py compilemessages
