from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import JSONField, TextField

from formdefaults.models import (
    FormFieldDefaultValue,
    FormFieldRepresentation,
    FormRepresentation,
)

WideTextInput = {"widget": forms.TextInput(attrs={"style": "width: 100%"})}


class FormFieldRepresentationInline(admin.TabularInline):
    model = FormFieldRepresentation
    fields = ["name", "label"]
    readonly_fields = ["name", "label"]
    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj):
        return False

    formfield_overrides = {
        TextField: WideTextInput,
    }


class FormFieldDefaultValueForm(forms.ModelForm):
    user = forms.ModelChoiceField(
        queryset=get_user_model().objects.all(), empty_label="każdy", required=False
    )

    class Meta:
        fields = ["user", "field", "value"]
        model = FormFieldDefaultValue


class FormFieldDefaultValueInline(admin.TabularInline):
    model = FormFieldDefaultValue
    form = FormFieldDefaultValueForm
    formfield_overrides = {
        JSONField: WideTextInput,
    }
    extra = 0


@admin.register(FormRepresentation)
class FormRepresentationAdmin(admin.ModelAdmin):
    list_display = ["label", "full_name", "pre_registered"]
    list_filter = ["pre_registered"]
    inlines = [FormFieldDefaultValueInline]
    readonly_fields = ["full_name", "pre_registered"]
    fields = ["label", "full_name", "pre_registered", "html_before", "html_after"]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, FormFieldDefaultValue):
                instance.is_auto_snapshot = False
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()
