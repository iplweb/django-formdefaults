"""Backfill is_auto_snapshot for existing rows by comparing stored value
with current code-level Form.initial. If they match, the row looks like
an untouched auto-snapshot — set True. Otherwise (or if we can't decide)
leave the field as False so the row is treated as 'sticky'."""

from django.db import migrations

from formdefaults._autosnap_backfill import resolve_initial


def forwards(apps, schema_editor):
    FormFieldDefaultValue = apps.get_model("formdefaults", "FormFieldDefaultValue")
    qs = FormFieldDefaultValue.objects.select_related("field", "parent").all()
    for row in qs:
        found, initial = resolve_initial(row.parent.full_name, row.field.name)
        if not found:
            row.is_auto_snapshot = False
            row.save(update_fields=["is_auto_snapshot"])
            continue
        row.is_auto_snapshot = row.value == initial
        row.save(update_fields=["is_auto_snapshot"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("formdefaults", "0006_formfielddefaultvalue_is_auto_snapshot"),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
