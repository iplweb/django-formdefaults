from formdefaults import core

NO_TITLE_FORM = "Formularz domyślny"


class FormDefaultsMixin:
    def get_form_title(self):
        if hasattr(self, "title"):
            return self.title
        if hasattr(self, "label"):
            return self.label
        return NO_TITLE_FORM

    def get_initial(self):
        user = None
        request = getattr(self, "request", None)
        if request is not None and getattr(request, "user", None) is not None:
            if getattr(request.user, "is_authenticated", False):
                user = request.user
        return core.get_form_defaults(
            self.form_class(),
            self.get_form_title(),
            user=user,
        )
