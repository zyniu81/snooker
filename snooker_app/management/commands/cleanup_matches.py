from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from snooker_app.models import Match, Player


class Command(BaseCommand):
    help = 'Usuwa mecze tymczasowe (bez właściciela) starsze niż 12 godzin.'

    def handle(self, *args, **kwargs):
        # 1. Ustawiamy granicę czasu: Teraz minus 12 godzin
        cutoff_time = timezone.now() - timedelta(hours=12)

        # 2. Szukamy meczów do usunięcia
        # Warunki:
        # - owner jest NULL (brak właściciela/konta)
        # - is_temporary jest True (dla pewności)
        # - created_at jest starsze niż 12h temu
        matches_to_delete = Match.objects.filter(
            is_temporary=True,
            created_at__lt=cutoff_time
        )

        count = matches_to_delete.count()

        if count > 0:
            self.stdout.write(self.style.WARNING(f'Znaleziono {count} przeterminowanych meczów (starszych niż 12h)...'))

            # --- Sprzątanie graczy tymczasowych ---
            # Zanim usuniemy mecze, zbieramy ID graczy tymczasowych do usunięcia
            player_ids_to_delete = []
            for match in matches_to_delete:
                if match.temp_player1:
                    player_ids_to_delete.append(match.temp_player1.id)
                if match.temp_player2:
                    player_ids_to_delete.append(match.temp_player2.id)

            # Usuwamy mecze
            matches_to_delete.delete()

            # Usuwamy graczy, którzy należeli do tych meczów
            if player_ids_to_delete:
                deleted_players = Player.objects.filter(id__in=player_ids_to_delete).delete()
                self.stdout.write(f'Usunięto również powiązanych graczy tymczasowych.')

            self.stdout.write(self.style.SUCCESS(f'SUKCES: Usunięto {count} starych meczów.'))
        else:
            self.stdout.write(self.style.SUCCESS('Czysto. Brak meczów starszych niż 12h do usunięcia.'))