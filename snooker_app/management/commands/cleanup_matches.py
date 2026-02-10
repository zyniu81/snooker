from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from snooker_app.models import Match, Player


class Command(BaseCommand):
    help = 'Removes temporary matches (without an owner) older than 12 hours.'

    def handle(self, *args, **kwargs):
        #1. We set the time limit: Now minus 12 hours
        cutoff_time = timezone.now() - timedelta(hours=12)

        # 2. Find matches to delete
        # Conditions:
        # - owner is NULL (no owner/account)
        # - is_temporary is True (safety check)
        # - created_at is older than 12 hours
        matches_to_delete = Match.objects.filter(
            is_temporary=True,
            created_at__lt=cutoff_time
        )

        count = matches_to_delete.count()

        if count > 0:
            self.stdout.write(self.style.WARNING(f'{count} expired matches found (older than 12 hours)...'))

            # --- Temporary players cleanup ---
            # Before deleting matches, collect IDs of temporary players to remove
            player_ids_to_delete = []
            for match in matches_to_delete:
                if match.temp_player1:
                    player_ids_to_delete.append(match.temp_player1.id)
                if match.temp_player2:
                    player_ids_to_delete.append(match.temp_player2.id)

            # Delete matches
            matches_to_delete.delete()

            # Delete players associated with these matches
            if player_ids_to_delete:
                deleted_players = Player.objects.filter(id__in=player_ids_to_delete).delete()
                self.stdout.write(f'Also removed associated temporary players.')

            self.stdout.write(self.style.SUCCESS(f'SUCCESS: Deleted {count} old matches.'))
        else:
            self.stdout.write(self.style.SUCCESS('Clean. No matches older than 12h to delete.'))