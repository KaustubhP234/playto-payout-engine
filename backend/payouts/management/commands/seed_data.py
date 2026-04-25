from django.core.management.base import BaseCommand
from django.db import transaction
from payouts.models import Merchant, LedgerEntry


MERCHANTS = [
    {
        'name': 'Arjun Mehta Designs',
        'email': 'arjun@mehtagfx.in',
        'bank_account_id': 'HDFC_ARJUN_0042',
        'credits': [
            (180000, 'Client payment — Acme Corp logo project'),
            (95000,  'Client payment — TechStart brand identity'),
            (220000, 'Client payment — Zomato social media pack'),
            (60000,  'Client payment — Freelance UI kit delivery'),
            (145000, 'Client payment — Nova Fintech pitch deck'),
        ],
    },
    {
        'name': 'Priya Software Exports',
        'email': 'priya@psexports.io',
        'bank_account_id': 'ICICI_PRIYA_1187',
        'credits': [
            (500000, 'Invoice #1042 — SaaS backend development'),
            (375000, 'Invoice #1043 — API integration — US client'),
            (250000, 'Invoice #1044 — DevOps setup — Singapore client'),
            (180000, 'Invoice #1045 — Code review retainer Q1'),
            (420000, 'Invoice #1046 — Mobile app MVP delivery'),
        ],
    },
    {
        'name': 'Rohan Creative Studio',
        'email': 'rohan@creativestudio.co',
        'bank_account_id': 'AXIS_ROHAN_3301',
        'credits': [
            (75000,  'Project — Product photography session'),
            (130000, 'Project — Video production — startup reel'),
            (88000,  'Project — Motion graphics — ad campaign'),
            (200000, 'Project — Brand film — Bengaluru client'),
            (55000,  'Project — Social content batch — Q1'),
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed the database with merchants and credit history'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing seed data before re-seeding',
        )

    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Resetting existing data...')
            LedgerEntry.objects.all().delete()
            Merchant.objects.all().delete()
            self.stdout.write(self.style.WARNING('Existing data deleted.'))

        for data in MERCHANTS:
            with transaction.atomic():
                merchant, created = Merchant.objects.get_or_create(
                    email=data['email'],
                    defaults={
                        'name': data['name'],
                        'bank_account_id': data['bank_account_id'],
                    }
                )

                if created:
                    self.stdout.write(f"Created merchant: {merchant.name}")
                else:
                    self.stdout.write(
                        self.style.WARNING(f"Merchant already exists: {merchant.name}")
                    )
                    continue

                # Create credit ledger entries
                for amount_paise, description in data['credits']:
                    LedgerEntry.objects.create(
                        merchant=merchant,
                        entry_type=LedgerEntry.CREDIT,
                        amount_paise=amount_paise,
                        description=description,
                        reference_id=f"SEED_{merchant.bank_account_id}",
                    )

                balance = merchant.get_balance()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {len(data['credits'])} credits seeded. "
                        f"Available balance: {balance['available_paise']} paise "
                        f"({balance['available_paise'] / 100:.2f} INR)"
                    )
                )

        self.stdout.write(self.style.SUCCESS('\nSeed complete.'))