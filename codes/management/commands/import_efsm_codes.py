# codes/management/commands/import_efsm_codes.py
import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from codes.models import Code  # EFSM Code model


class Command(BaseCommand):
    help = "Import EFSM Codes from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to CSV file")
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing rows if code already exists",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        do_update = options["update"]

        if not csv_path.exists():
            raise CommandError(f"File not found: {csv_path}")

        # Expected headers: code, fire_safety_measure, visits_per_year
        created = 0
        updated = 0
        skipped = 0

        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            required = {"code", "fire_safety_measure", "visits_per_year"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise CommandError(
                    f"CSV must contain headers: {', '.join(sorted(required))}. "
                    f"Found: {reader.fieldnames}"
                )

            for i, row in enumerate(reader, start=2):
                code_val = (row.get("code") or "").strip()
                fsm = (row.get("fire_safety_measure") or "").strip()
                vpy_raw = (row.get("visits_per_year") or "").strip()

                if not code_val or not fsm:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(f"Row {i}: missing code or fire_safety_measure; skipped"))
                    continue

                try:
                    vpy = int(vpy_raw) if vpy_raw else 1
                except ValueError:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(f"Row {i}: invalid visits_per_year '{vpy_raw}'; skipped"))
                    continue

                obj = Code.objects.filter(code=code_val).first()
                if obj:
                    if do_update:
                        obj.fire_safety_measure = fsm
                        obj.visits_per_year = vpy
                        obj.save()
                        updated += 1
                    else:
                        skipped += 1
                else:
                    Code.objects.create(code=code_val, fire_safety_measure=fsm, visits_per_year=vpy)
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Done. created={created}, updated={updated}, skipped={skipped}"))
