from django.core.management.base import BaseCommand
from django.db.models import Count, Max

from formdefaults.models import FormFieldDefaultValue


class Command(BaseCommand):
    help = (
        "Remove duplicate FormFieldDefaultValue rows. Keeps the row with the "
        "highest id per (field, user) tuple. Run before applying migration "
        "0004 if your existing DB has duplicates."
    )

    def handle(self, *args, **options):
        groups = (
            FormFieldDefaultValue.objects.values("field_id", "user_id")
            .annotate(n=Count("id"), keeper=Max("id"))
            .filter(n__gt=1)
        )
        deleted_total = 0
        for g in groups:
            qs = FormFieldDefaultValue.objects.filter(
                field_id=g["field_id"], user_id=g["user_id"]
            ).exclude(id=g["keeper"])
            count = qs.count()
            qs.delete()
            deleted_total += count
            self.stdout.write(
                f"  field={g['field_id']} user={g['user_id']}: removed {count}"
            )
        self.stdout.write(self.style.SUCCESS(f"Total removed: {deleted_total}"))
