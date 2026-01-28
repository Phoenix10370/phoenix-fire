from django.core.management.base import BaseCommand, CommandError

from qbo.qbo_sync.customer_sync import sync_customers


class Command(BaseCommand):
    help = "Sync Customers with QuickBooks: pull (link) and push (create missing)."

    def add_arguments(self, parser):
        parser.add_argument("--pull", action="store_true", help="Pull customers from QBO and link locally.")
        parser.add_argument("--push", action="store_true", help="Push local customers missing accounting_id to QBO.")
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing anything.")
        parser.add_argument("--max-results", type=int, default=1000, help="Max customers to pull from QBO (default 1000).")

    def handle(self, *args, **options):
        pull = options["pull"]
        push = options["push"]
        dry_run = options["dry_run"]
        max_results = options["max_results"]

        # If no flags provided, do both
        if not pull and not push:
            pull = True
            push = True

        try:
            result = sync_customers(pull=pull, push=push, dry_run=dry_run, max_results=max_results)
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS("QBO Customer Sync Complete"))
        self.stdout.write(f"dry_run: {dry_run}")
        self.stdout.write(f"pull: {pull} | push: {push}")
        self.stdout.write("")
        self.stdout.write("PULL:")
        self.stdout.write(f"  pulled_total: {result.pulled_total}")
        self.stdout.write(f"  matched_local: {result.matched_local}")
        self.stdout.write(f"  linked_local_updated: {result.linked_local_updated}")
        self.stdout.write(f"  pulled_unmatched: {result.pulled_unmatched}")
        self.stdout.write("")
        self.stdout.write("PUSH:")
        self.stdout.write(f"  push_candidates (local missing accounting_id): {result.push_candidates}")
        self.stdout.write(f"  pushed_created: {result.pushed_created}")
        self.stdout.write(f"  pushed_failed: {result.pushed_failed}")
