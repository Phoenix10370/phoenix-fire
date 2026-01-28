# qbo/management/commands/qbo_test_customers.py
from django.core.management.base import BaseCommand
from qbo.qbo_sync.query_api import qbo_query


class Command(BaseCommand):
    help = "Test QBO Query by printing 5 Customers"

    def handle(self, *args, **options):
        data = qbo_query("select Id, DisplayName, Active from Customer maxresults 5")
        customers = data.get("QueryResponse", {}).get("Customer", [])

        self.stdout.write(self.style.SUCCESS(f"Returned {len(customers)} customers"))
        for c in customers:
            self.stdout.write(f'- Id={c.get("Id")}  Name="{c.get("DisplayName")}"  Active={c.get("Active")}')
