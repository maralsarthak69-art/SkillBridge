"""
Management command: check_roadmap_links

Usage:
    python manage.py check_roadmap_links
    python manage.py check_roadmap_links --roadmap_id 5
    python manage.py check_roadmap_links --verbose
"""
from django.core.management.base import BaseCommand
from core_engine.services_v1.health_check import scan_roadmap_links


class Command(BaseCommand):
    help = "Scan all roadmap resource URLs for broken links (404s)"

    def add_arguments(self, parser):
        parser.add_argument("--roadmap_id", type=int, default=None,
                            help="Scan a specific roadmap only")
        parser.add_argument("--verbose", action="store_true",
                            help="Print all results including OK links")

    def handle(self, *args, **options):
        roadmap_id = options.get("roadmap_id")
        verbose    = options.get("verbose")

        self.stdout.write("Scanning roadmap links...")
        results = scan_roadmap_links(roadmap_id)

        self.stdout.write(f"\nScanned:  {results['scanned']}")
        self.stdout.write(self.style.SUCCESS(f"OK:       {results['ok']}"))
        self.stdout.write(f"Skipped:  {results['skipped']}")

        if results["broken"]:
            self.stdout.write(self.style.ERROR(f"Broken:   {len(results['broken'])}"))
            for item in results["broken"]:
                self.stdout.write(
                    self.style.ERROR(
                        f"  [{item['status']} {item['code']}] "
                        f"{item['skill_name']} — {item['url']}"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS("No broken links found."))

        self.stdout.write(f"\nChecked at: {results['checked_at']}")
