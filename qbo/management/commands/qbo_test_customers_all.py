from django.core.management.base import BaseCommand
from qbo.qbo_sync.query_api import qbo_query_all


class Command(BaseCommand):
    help = "Test QBO pagination by pulling ALL Customers and printing count"

    def handle(self, *args, **options):
        customers, last = qbo_query_all("select Id, DisplayName, Active from Customer", page_size=100)

        self.stdout.write(self.style.SUCCESS(f"Pulled {len(customers)} customers total"))

        # Print first 5 so it's obvious it worked
        for c in customers[:5]:
            self.stdout.write(f'- Id={c.get("Id")}  Name="{c.get("DisplayName")}"  Active={c.get("Active")}')
