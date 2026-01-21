from django.core.management.base import BaseCommand
from django.utils.text import slugify

from codes.models import DropdownList, DropdownOption


class Command(BaseCommand):
    help = "Seed default dropdown lists and options (Asset Categories & Asset Equipment)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing options in these lists and re-seed them.",
        )

    def handle(self, *args, **options):
        reset = options["reset"]

        categories = [
            "Emergency Lighting",
            "Exit Sign",
            "Portable Fire Extinguishers",
            "Fire Hydrants",
            "Fire Hose Reels",
            "Access",
            "Detection",
            "Mechanical Air",
            "Fire Dampers",
            "Chutes",
            "Fire Doors",
            "Pumps",
            "Windows",
            "Sliding Doors",
            "Shutters",
            "Solid Core Doors",
            "RCD",
        ]

        # Create/get lists (slugs will auto-generate on save if blank)
        cat_list, _ = DropdownList.objects.get_or_create(
            name="Asset Categories",
            defaults={"is_active": True},
        )
        eq_list, _ = DropdownList.objects.get_or_create(
            name="Asset Equipment",
            defaults={"is_active": True},
        )

        # Ensure slugs are set (in case lists existed before slug logic)
        if not cat_list.slug:
            cat_list.slug = slugify(cat_list.name)
            cat_list.save(update_fields=["slug"])

        if not eq_list.slug:
            eq_list.slug = slugify(eq_list.name)
            eq_list.save(update_fields=["slug"])

        if reset:
            DropdownOption.objects.filter(dropdown_list=cat_list).delete()
            DropdownOption.objects.filter(dropdown_list=eq_list).delete()
            self.stdout.write(self.style.WARNING("Reset enabled: existing options deleted."))

        # Seed categories (top-level: parent=None)
        category_options_by_label = {}
        for idx, label in enumerate(categories):
            opt, _ = DropdownOption.objects.get_or_create(
                dropdown_list=cat_list,
                label=label,
                defaults={
                    "sort_order": idx,
                    "is_active": True,
                },
            )
            # keep sort_order consistent if it already existed
            if opt.sort_order != idx:
                opt.sort_order = idx
                opt.save(update_fields=["sort_order"])
            if not opt.is_active:
                opt.is_active = True
                opt.save(update_fields=["is_active"])

            category_options_by_label[label] = opt

        # Seed equipment options, parented to matching category option.
        # (Today it’s 1:1. Later you can add multiple equipment under one category.)
        for idx, label in enumerate(categories):
            parent_opt = category_options_by_label[label]
            opt, _ = DropdownOption.objects.get_or_create(
                dropdown_list=eq_list,
                label=label,
                defaults={
                    "parent": parent_opt,
                    "sort_order": idx,
                    "is_active": True,
                },
            )

            # If it existed without parent, fix it
            changed = False
            if opt.parent_id != parent_opt.id:
                opt.parent = parent_opt
                changed = True
            if opt.sort_order != idx:
                opt.sort_order = idx
                changed = True
            if not opt.is_active:
                opt.is_active = True
                changed = True

            if changed:
                opt.save()

        self.stdout.write(self.style.SUCCESS("Seeded Dropdown Lists: Asset Categories, Asset Equipment"))
        self.stdout.write(self.style.SUCCESS(f" - {cat_list.name} ({cat_list.slug}): {len(categories)} options"))
        self.stdout.write(self.style.SUCCESS(f" - {eq_list.name} ({eq_list.slug}): {len(categories)} options (parented)"))
