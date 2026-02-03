from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from datetime import timedelta
import random


# Create your models here.

class Player(models.Model):
    # --- 1. DANE OSOBOWE I KONFIGURACJA ---
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='players', null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='player_profile')
    is_public = models.BooleanField(default=False)
    is_temporary = models.BooleanField(default=False)
    is_guest = models.BooleanField(default=False,
                                   help_text="Is this a player imported only for the tournament (not visible in the library)?")

    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    nickname = models.CharField(max_length=30, blank=True, null=True)
    photo = models.ImageField(upload_to='players_photos/', blank=True, null=True)

    # --- 2. STATYSTYKI MECZOWE (Kariera) ---
    matches_played = models.IntegerField(default=0)
    matches_won = models.IntegerField(default=0)
    matches_drawn = models.IntegerField(default=0)
    matches_lost = models.IntegerField(default=0)

    # --- 3. STATYSTYKI FRAME'ÓW (Kariera) ---
    frames_played = models.IntegerField(default=0)
    frames_won = models.IntegerField(default=0)
    frames_lost = models.IntegerField(default=0)
    fastest_frame_time = models.DurationField(blank=True, null=True, help_text="Najkrótsza rozegrana partia")
    longest_frame_time = models.DurationField(blank=True, null=True, help_text="Najdłuższa rozegrana partia")
    avg_frame_time = models.DurationField(blank=True, null=True, help_text="Średni czas trwania partii")

    # --- 4. PUNKTY I TECHNIKA ---
    total_career_points = models.BigIntegerField(default=0, help_text="Suma wszystkich wbitych punktów")
    global_pot_success = models.FloatField(default=0.0, help_text="Średnia skuteczność wbić z kariery (%)")
    global_safety_success = models.FloatField(default=0.0, help_text="Średnia skuteczność odstawnych z kariery (%)")
    avg_shot_time = models.DurationField(blank=True, null=True, help_text="Średni czas na uderzenie")

    # --- 5. BREAKI (Prestiż) ---
    highest_break = models.IntegerField(default=0)
    centuries_count = models.IntegerField(default=0, help_text="Liczba breaków 100+")
    fifties_count = models.IntegerField(default=0, help_text="Liczba breaków 50+")
    max_breaks_count = models.IntegerField(default=0, help_text="Liczba breaków maksymalnych (147, 155, 167)")

    # Histogram breaków kariery (np. {"10-19": 150, "20-29": 40...})
    career_break_stats = models.JSONField(default=dict, blank=True)

    # --- 6. SPECJALNE OSIĄGNIĘCIA (Nowość) ---
    deciders_played = models.IntegerField(default=0, help_text="Liczba rozegranych partii rozstrzygających")
    deciders_won = models.IntegerField(default=0, help_text="Liczba wygranych partii rozstrzygających")
    whitewashes_count = models.IntegerField(default=0, help_text="Liczba meczów wygranych do zera")

    # --- 7. SERIE (Streaks) ---
    consecutive_matches_won = models.IntegerField(default=0, help_text="Rekordowa seria wygranych meczów z rzędu")
    current_match_streak = models.IntegerField(default=0, help_text="Aktualna seria wygranych meczów (robocze)")

    consecutive_frames_won = models.IntegerField(default=0, help_text="Rekordowa seria wygranych frame'ów z rzędu")
    current_frame_streak = models.IntegerField(default=0, help_text="Aktualna seria wygranych frame'ów (robocze)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.nickname:
            if self.first_name and self.last_name:
                return f'{self.first_name} "{self.nickname}" {self.last_name}'
            elif self.first_name:
                return f'{self.first_name} "{self.nickname}"'
            elif self.last_name:
                return f'"{self.nickname}" {self.last_name}'
            else:
                return f'"{self.nickname}"'
        elif self.first_name and self.last_name:
            return f'{self.first_name} {self.last_name}'
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        else:
            return f'Player {self.id}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not (self.first_name or self.last_name or self.nickname):
            self.first_name = f'Player {self.id}'
            super().save(update_fields=['first_name'])

    def formatted_avg_shot_time(self):
        if self.avg_shot_time:
            total_seconds = int(self.avg_shot_time.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            return f'{minutes}:{seconds:02}'
        return "-"

    def formatted_fastest_frame(self):
        return self._format_duration(self.fastest_frame_time)

    def formatted_longest_frame(self):
        return self._format_duration(self.longest_frame_time)

    def formatted_avg_frame(self):
        return self._format_duration(self.avg_frame_time)

    def _format_duration(self, duration):
        """Pomocnicza funkcja do formatowania czasu MM:SS"""
        if duration:
            total_seconds = int(duration.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            # Jeśli gra trwała ponad godzinę, dodaj godziny (opcjonalnie)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                return f'{hours}:{minutes:02}:{seconds:02}'
            return f'{minutes}:{seconds:02}'
        return "-"


class Venue(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='venues')
    is_public = models.BooleanField(default=False)

    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True, null=True)

    # Image
    image = models.ImageField(upload_to='venue_images/', blank=True, null=True)

    # Kontakt
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    # Szczegóły techniczne
    tables_count = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(0)],
        help_text="Liczba stołów"
    )
    table_info = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Np. Star Tables, Strachan Cloth"
    )
    price_per_hour = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True,
        help_text="Cena za godzinę (PLN)"
    )

    capacity = models.PositiveIntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name


class Referee(models.Model):
    # --- NOWE POLA WŁASNOŚCI ---
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referees')
    is_public = models.BooleanField(default=False)
    # ---------------------------

    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    license_number = models.CharField(max_length=20, blank=True)

    photo = models.ImageField(upload_to='referee_photos/', blank=True, null=True)

    def __str__(self):
        if self.first_name and self.last_name:
            return f'{self.first_name} {self.last_name}'
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        elif self.license_number:
            return f'Referee (License: {self.license_number})'
        else:
            return f'Referee {self.id}'


class Group(models.Model):
    """Reprezentuje konkretną grupę (np. Grupa 1) w ramach etapu grupowego"""
    stage = models.ForeignKey('GroupStage', on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=10, help_text="Group number, e.g. '1', '2'")

    # Status zakończenia konkretnej grupy
    is_finished = models.BooleanField(default=False)

    def __str__(self):
        return f"Group {self.name} - {self.stage.competition.name}"

    class Meta:
        ordering = ['name']


class GroupStanding(models.Model):
    """
    Tabela wyników dla konkretnego gracza w grupie.

    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='standings')
    player = models.ForeignKey('Player', on_delete=models.CASCADE)

    # 1. MECZE
    matches_played = models.IntegerField(default=0)
    matches_won = models.IntegerField(default=0)
    matches_drawn = models.IntegerField(default=0)
    matches_lost = models.IntegerField(default=0)

    # 2. FRAMY (Kluczowe dla tabeli)
    frames_won = models.IntegerField(default=0)
    frames_lost = models.IntegerField(default=0)

    # 3. MAŁE PUNKTY (Suma punktów wbitych w meczach)
    small_points_scored = models.IntegerField(default=0, help_text="Total of all points scored")
    small_points_conceded = models.IntegerField(default=0, help_text="Total of all points lost")

    # 4. DODATKI
    highest_break = models.IntegerField(default=0, help_text="The highest break in this group")

    # Status awansu (do kolorowania tabeli)
    is_qualified = models.BooleanField(default=False, help_text="Has the player advanced further?")
    final_rank = models.PositiveIntegerField(null=True, blank=True, help_text="Place taken (after group end)")

    # 5. GŁÓWNA PUNKTACJA
    points = models.IntegerField(default=0, help_text="Points in the table")

    class Meta:
        # Sortowanie: Punkty > Różnica Frame'ów > Wygrane Frame'y > Różnica Małych Punktów
        ordering = ['-points', '-frames_won', 'frames_lost', '-small_points_scored']
        unique_together = ['group', 'player']

    def __str__(self):
        return f"{self.player} in {self.group} (Pts: {self.points})"

    @property
    def frame_difference(self):
        return self.frames_won - self.frames_lost

    @property
    def small_points_difference(self):
        return self.small_points_scored - self.small_points_conceded


class Match(models.Model):
    # --- 1. KONFIGURACJA PODSTAWOWA ---
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('IN_PROGRESS', 'In Progress'),
        ('FINISHED', 'Finished'),
        ('ABORTED', 'Aborted'),
    ]

    VARIANT_CHOICES = [
        ('STANDARD', 'Standard (15 Reds)'),
        ('SIX_RED', '6-Red Snooker'),
        ('SHOOTOUT', 'Shoot Out'),
        ('TRAINING', 'Training/Sparing'),
        ('OTHER', 'Other'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='matches', null=True, blank=True)
    is_public = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    game_variant = models.CharField(max_length=20, choices=VARIANT_CHOICES, default='STANDARD')

    date = models.DateField()
    time = models.TimeField()
    venue = models.ForeignKey('Venue', on_delete=models.SET_NULL, blank=True, null=True)
    table_number = models.CharField(max_length=10, blank=True, null=True, help_text="e.g. 1, 12, A1, other")
    round_number = models.PositiveIntegerField(default=1, help_text="Numer kolejki (Grupy) lub Rundy (Puchar)")

    number_of_frames = models.PositiveIntegerField()
    allow_draws = models.BooleanField(default=False)

    # --- 2. GRACZE I SĘDZIOWIE ---
    player1 = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='matches_as_p1')
    player2 = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='matches_as_p2')
    referees = models.ManyToManyField('Referee', blank=True, related_name='matches')

    # Cache nazw (tekstowe)
    player_names = models.TextField(blank=True, null=True)
    referee_names = models.TextField(blank=True, null=True)
    player_ids = models.TextField(blank=True, null=True)
    referee_ids = models.TextField(blank=True, null=True)

    # --- 3. STRUKTURA TURNIEJOWA ---
    group_stage = models.ForeignKey('GroupStage', on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='matches')
    knockout_stage = models.ForeignKey('KnockoutStage', on_delete=models.CASCADE, null=True, blank=True,
                                       related_name='matches')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True, related_name='matches')
    group_name = models.CharField(max_length=10, blank=True, null=True)
    knockout_name = models.CharField(max_length=100, blank=True, null=True)

    # --- 4. WYNIKI KOŃCOWE (Podsumowanie) ---
    winner = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_matches')

    final_score_player1 = models.IntegerField(default=0, help_text="Wygrane frame'y P1")
    final_score_player2 = models.IntegerField(default=0, help_text="Wygrane frame'y P2")

    # --- 5. STATYSTYKI CZASOWE ---
    total_duration = models.DurationField(blank=True, null=True, help_text="Suma czasu gry netto")
    avg_frame_time = models.DurationField(blank=True, null=True)
    min_frame_time = models.DurationField(blank=True, null=True)
    max_frame_time = models.DurationField(blank=True, null=True)

    # --- 7. BREAKI I SERIE ---

    highest_break_frame_p1 = models.ForeignKey('Frame', on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name='hb_match_p1')
    highest_break_frame_p2 = models.ForeignKey('Frame', on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name='hb_match_p2')

    # JSON Histogram: {"10-19": 5, "20-29": 2, ...}
    break_stats_p1 = models.JSONField(default=dict, blank=True)
    break_stats_p2 = models.JSONField(default=dict, blank=True)

    longest_pot_streak_p1 = models.IntegerField(default=0)
    longest_pot_streak_p2 = models.IntegerField(default=0)

    # --- 8. DANE TYMCZASOWE ---
    temp_player1 = models.ForeignKey('Player', null=True, blank=True, related_name='temp_player1_matches',
                                     on_delete=models.CASCADE)
    temp_player2 = models.ForeignKey('Player', null=True, blank=True, related_name='temp_player2_matches',
                                     on_delete=models.CASCADE)
    is_temporary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_ordered_players(self):
        """
        Zwraca listę graczy zawsze w kolejności: [Gospodarz, Gość].
        Teraz to jest sztywne, wynikające z modelu.
        """
        # Zwracamy listę [p1, p2], filtrując None (gdyby kogoś brakowało)
        return [p for p in [self.player1, self.player2] if p]

    @property
    def sort_key(self):
        """
        Zwraca klucz do sortowania listy meczów.
        Kolejność: Data -> Czas -> ID (kolejność tworzenia)
        """
        # Formatujemy tak, aby sortowanie tekstowe działało chronologicznie
        # Np. "2023-10-20 14:00:00 125"
        return f"{self.date} {self.time} {self.id}"

    def formatted_duration(self):
        if self.total_duration:
            total_seconds = int(self.total_duration.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                return f'{hours}:{minutes:02}:{seconds:02}'
            return f'{minutes}:{seconds:02}'
        return "-"

    class Meta:
        indexes = [
            models.Index(fields=['date', 'time']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.player_names} - {self.date}'

    def get_game_status(self):
        # Sprawdzamy czy mamy obu graczy na fotelach
        if not self.player1 or not self.player2:
            return {'is_finished': False, 'winner': None}

        p1 = self.player1
        p2 = self.player2

        # LICZYMY ZWYCIĘSTWA
        p1_wins = Frame.objects.filter(match_player__match=self, winner=p1).count()
        p2_wins = Frame.objects.filter(match_player__match=self, winner=p2).count()

        total_played = p1_wins + p2_wins
        is_finished = False
        winner = None

        # --- SCENARIUSZ A: REMISY DOZWOLONE ---
        if self.allow_draws:
            if total_played >= self.number_of_frames:
                is_finished = True
                if p1_wins > p2_wins:
                    winner = p1
                elif p2_wins > p1_wins:
                    winner = p2
                else:
                    winner = None  # REMIS

        # --- SCENARIUSZ B: STANDARDOWY ---
        else:
            threshold = (self.number_of_frames // 2) + 1
            if p1_wins >= threshold:
                is_finished = True
                winner = p1
            elif p2_wins >= threshold:
                is_finished = True
                winner = p2

            if not is_finished and total_played >= self.number_of_frames:
                is_finished = True
                winner = None

        return {'is_finished': is_finished, 'winner': winner}

    def get_real_score(self):
        """Zwraca krotkę (wynik_p1, wynik_p2) liczoną z frame'ów"""
        if not self.player1 or not self.player2:
            return 0, 0

        # Liczymy wygrane framy, sprawdzając pole 'winner' we Frame
        p1_score = Frame.objects.filter(match_player__match=self, winner=self.player1).count()
        p2_score = Frame.objects.filter(match_player__match=self, winner=self.player2).count()

        return p1_score, p2_score

    def update_status_from_frames(self):
        """Aktualizuje status meczu i zwycięzcę na podstawie rozegranych frame'ów"""
        status_data = self.get_game_status()  # Ta metoda już liczy kto wygrał

        # Aktualizujemy pola w bazie
        self.winner = status_data['winner']

        if status_data['is_finished']:
            self.status = 'FINISHED'
        else:
            self.status = 'IN_PROGRESS'

        # Opcjonalnie: Zapisz też wynik punktowy do pól final_score
        scores = self.get_real_score()
        self.final_score_player1 = scores[0]
        self.final_score_player2 = scores[1]

        self.save()

    @property
    def is_finished(self):
        return self.status == 'FINISHED'

    def is_match_finished(self):
        return self.get_game_status()['is_finished']

    def clean(self):
        if self.number_of_frames is not None and self.number_of_frames <= 0:
            raise ValidationError('The number of frames must be greater than zero.')

        # Walidacja: Gracz nie może grać sam ze sobą
        if self.player1 and self.player2 and self.player1 == self.player2:
            raise ValidationError('Player 1 and Player 2 cannot be the same person.')

    def get_stage(self):
        return self.group_stage or self.knockout_stage

    def set_stage(self, stage):
        if isinstance(stage, GroupStage):
            self.group_stage = stage
            self.knockout_stage = None
        elif isinstance(stage, KnockoutStage):
            self.knockout_stage = stage
            self.group_stage = None

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # 1. Aktualizacja cache nazw
        names = []
        ids = []
        if self.player1:
            names.append(str(self.player1))
            ids.append(str(self.player1.id))
        if self.player2:
            names.append(str(self.player2))
            ids.append(str(self.player2.id))
        self.player_names = ', '.join(names)
        self.player_ids = ', '.join(ids)

        # 2. Zapisz Mecz (żeby mieć ID)
        super().save(*args, **kwargs)

        # 3. Cache Sędziów (To już mieliśmy)
        if not is_new:
            self.referee_names = ', '.join([str(referee) for referee in self.referees.all()])
            self.referee_ids = ', '.join([str(referee.id) for referee in self.referees.all()])
            super().save(update_fields=['referee_names', 'referee_ids', 'player_names', 'player_ids'])

        # --- NOWOŚĆ: MOST DO STAREGO SYSTEMU (MatchPlayer Sync) - POPRAWKA 2 ---
        from .models import MatchPlayer
        from django.db import transaction

        with transaction.atomic():
            # 1. Lista aktualnych ID
            current_player_ids = []
            if self.player1: current_player_ids.append(self.player1.id)
            if self.player2: current_player_ids.append(self.player2.id)

            # 2. USUWANIE: Usuń wpisy graczy, których już nie ma
            MatchPlayer.objects.filter(match=self).exclude(player_id__in=current_player_ids).delete()

            # 3. ZROBIENIE MIEJSCA (Fix dla SWAP):
            # Zamiast liczb ujemnych (których baza nie lubi), używamy dużych liczb dodatnich.
            # Przesuwamy 1 -> 101, 2 -> 102.
            for mp in MatchPlayer.objects.filter(match=self):
                # Zmieniamy tylko jeśli to są "normalne" pozycje (poniżej 100)
                if mp.position < 50:
                    mp.position = 100 + mp.position
                    mp.save()

            # 4. USTAWIANIE: Przypisz właściwe pozycje
            # System znajdzie gracza na pozycji 101 i zmieni mu na 1.
            # System znajdzie gracza na pozycji 102 i zmieni mu na 2.

            if self.player1:
                MatchPlayer.objects.update_or_create(
                    match=self,
                    player=self.player1,
                    defaults={'position': 1}
                )

            if self.player2:
                MatchPlayer.objects.update_or_create(
                    match=self,
                    player=self.player2,
                    defaults={'position': 2}
                )

    def is_expired(self):
        return self.is_temporary and self.created_at < timezone.now() - timedelta(days=30)

    def delete_if_expired(self):
        if self.is_expired():
            self.delete()

    def delete(self, *args, **kwargs):
        # 1. Znajdujemy graczy tymczasowych powiązanych z TYM meczem
        # Zbieramy ich z foteli player1 i player2
        temp_players_to_check = []

        if self.player1 and self.player1.is_temporary:
            temp_players_to_check.append(self.player1)

        if self.player2 and self.player2.is_temporary:
            temp_players_to_check.append(self.player2)

        # 2. Wykonujemy standardowe usuwanie meczu
        super().delete(*args, **kwargs)

        # 3. Sprzątanie sierot (Orphan Cleanup)
        for player in temp_players_to_check:
            # Sprawdzamy, czy ten gracz jest przypisany do innych meczów.
            # Musimy sprawdzić obie role: jako Gospodarz (matches_as_p1) i jako Gość (matches_as_p2)
            # Te related_name dodaliśmy w definicji ForeignKeys.

            p1_count = player.matches_as_p1.count()
            p2_count = player.matches_as_p2.count()

            if (p1_count + p2_count) == 0:
                player.delete()

    # --- WIRTUALNE STATYSTYKI MECZU (Poprawione: pobieranie przez MatchPlayer) ---

    # 1. SUMA PUNKTÓW
    @property
    def total_points_player1(self):
        # Używamy globalnego obiektu Frame (tak jak w Twoim get_game_status)
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('points_scored_player1'))[
            'total'] or 0

    @property
    def total_points_player2(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('points_scored_player2'))[
            'total'] or 0

    # 2. NAJWYŻSZY BREAK W MECZU
    @property
    def highest_break_p1(self):
        return Frame.objects.filter(match_player__match=self).aggregate(top=models.Max('max_break_player1'))[
            'top'] or 0

    @property
    def highest_break_p2(self):
        return Frame.objects.filter(match_player__match=self).aggregate(top=models.Max('max_break_player2'))[
            'top'] or 0

    # 3. SUMA FAULI
    @property
    def total_fouls_p1(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('player1_fouls'))[
            'total'] or 0

    @property
    def total_fouls_p2(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('player2_fouls'))[
            'total'] or 0

    # 4. PUNKTY ODDAJĄCE (Z FAULI)
    @property
    def foul_points_conceded_p1(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('foul_points_player1'))[
            'total'] or 0

    @property
    def foul_points_conceded_p2(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('foul_points_player2'))[
            'total'] or 0

    # 5. POT SUCCESS
    @property
    def pot_success_p1(self):
        data = Frame.objects.filter(match_player__match=self).aggregate(
            pots=models.Sum('potted_balls_player1'),
            misses=models.Sum('misses_player1')
        )
        pots = data['pots'] or 0
        misses = data['misses'] or 0
        total_shots = pots + misses

        if total_shots == 0:
            return 0
        return (pots / total_shots) * 100

    @property
    def pot_success_p2(self):
        data = Frame.objects.filter(match_player__match=self).aggregate(
            pots=models.Sum('potted_balls_player2'),
            misses=models.Sum('misses_player2')
        )
        pots = data['pots'] or 0
        misses = data['misses'] or 0
        total_shots = pots + misses

        if total_shots == 0:
            return 0
        return (pots / total_shots) * 100

    # 6. AST (Average Shot Time) - Średnia meczowa per gracz
    @property
    def match_ast_p1(self):
        # Pobieramy sumę czasu i sumę uderzeń ze wszystkich framów
        data = Frame.objects.filter(match_player__match=self).aggregate(
            total_time=models.Sum('time_shots_player1'),
            total_shots=models.Sum('total_shots_player1')
        )

        time_sum = data['total_time']
        shots_sum = data['total_shots'] or 0

        # Zabezpieczenie przed dzieleniem przez zero
        if not time_sum or shots_sum == 0:
            return "-"

        # Obliczenie średniej w sekundach
        avg_seconds = time_sum.total_seconds() / shots_sum

        # Zwracamy format np. "24s"
        return f"{int(avg_seconds)}s"

    @property
    def match_ast_p2(self):
        data = Frame.objects.filter(match_player__match=self).aggregate(
            total_time=models.Sum('time_shots_player2'),
            total_shots=models.Sum('total_shots_player2')
        )

        time_sum = data['total_time']
        shots_sum = data['total_shots'] or 0

        if not time_sum or shots_sum == 0:
            return "-"

        avg_seconds = time_sum.total_seconds() / shots_sum
        return f"{int(avg_seconds)}s"

    # --- CZAS MECZU ---

    @property
    def match_total_duration(self):
        # Sumujemy czasy wszystkich framów podpiętych do tego meczu
        total = Frame.objects.filter(match_player__match=self).aggregate(
            t=models.Sum('time_duration')
        )['t']
        return total  # Zwraca obiekt czasu (timedelta) lub None

    @property
    def formatted_match_duration(self):
        # Ta metoda robi ładny napis np. "2h 15m"
        d = self.match_total_duration
        if d:
            total_seconds = int(d.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m {seconds}s"
        return "-"


class MatchPlayer(models.Model):
    match = models.ForeignKey('Match', on_delete=models.CASCADE)
    player = models.ForeignKey('Player', on_delete=models.CASCADE)

    # This is the most important field - it tells whether it is Player 1 or Player 2
    position = models.PositiveSmallIntegerField(choices=[(1, 'First'), (2, 'Second')])

    class Meta:
        unique_together = ('match', 'player')
        indexes = [
            models.Index(fields=['match']),
            models.Index(fields=['player']),
        ]

    def __str__(self):
        return f'{self.player} in match {self.match.id} (Pos: {self.get_position_display()})'


class Frame(models.Model):
    match_player = models.ForeignKey('MatchPlayer', on_delete=models.CASCADE)
    frame_number = models.PositiveIntegerField()

    # Punkty
    points_scored_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    points_scored_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    # Breaki
    max_break_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    max_break_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    break_points_player1 = ArrayField(
        models.IntegerField(validators=[MinValueValidator(10), MaxValueValidator(155)]),
        default=list, blank=True
    )
    break_points_player2 = ArrayField(
        models.IntegerField(validators=[MinValueValidator(10), MaxValueValidator(155)]),
        default=list, blank=True
    )

    # Faule
    player1_fouls = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    player2_fouls = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    foul_points_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    foul_points_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    # Zwycięzca
    winner = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_frames')

    # Czas
    time_duration = models.DurationField(blank=True, null=True)

    # Wbicia (Pot Success)
    # NOWOŚĆ: Ilość wbitych bil (żeby móc łatwo liczyć średnią w meczu)
    potted_balls_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    potted_balls_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    pot_success_percentage_player1 = models.FloatField(default=0.0)
    pot_success_percentage_player2 = models.FloatField(default=0.0)
    total_pot_success_percentage_player1 = models.FloatField(default=0.0)
    total_pot_success_percentage_player2 = models.FloatField(default=0.0)

    # Odstawne (Safety)
    safety_shot_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    safety_shot_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    successful_safety_shots_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    successful_safety_shots_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    # Strzały
    misses_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    misses_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_shots_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_shots_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    time_shots_player1 = models.DurationField(blank=True, null=True)
    time_shots_player2 = models.DurationField(blank=True, null=True)

    active_player = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='active_frames')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('match_player', 'frame_number')

    def average_shot_time_player1(self):
        if self.total_shots_player1 > 0 and self.time_shots_player1:
            return self.time_shots_player1 / self.total_shots_player1
        return None

    def average_shot_time_player2(self):
        if self.total_shots_player2 > 0 and self.time_shots_player2:
            return self.time_shots_player2 / self.total_shots_player2
        return None

    def safety_shot_success_rate_player1(self):
        if self.safety_shot_player1 and self.safety_shot_player1 > 0:
            return (self.successful_safety_shots_player1 / self.safety_shot_player1) * 100
        return 0.0

    def safety_shot_success_rate_player2(self):
        if self.safety_shot_player2 and self.safety_shot_player2 > 0:
            return (self.successful_safety_shots_player2 / self.safety_shot_player2) * 100
        return 0.0


class Competition(models.Model):
    # --- 1. WŁASNOŚĆ I WIDOCZNOŚĆ ---
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='competitions')
    is_public = models.BooleanField(default=False)

    # --- 2. DANE PODSTAWOWE ---
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    venue = models.ForeignKey('Venue', on_delete=models.SET_NULL, blank=True, null=True)

    # --- NOWE: STATUS TURNIEJU ---
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('ACTIVE', 'Active'),
        ('FINISHED', 'Finished'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SCHEDULED')

    # --- 3. KONFIGURACJA GRY ---
    game_variant = models.CharField(
        max_length=20,
        choices=Match.VARIANT_CHOICES,
        default='STANDARD',
        help_text="Default game variant for all matches in the tournament"
    )

    # --- REKORDY TURNIEJU ---
    highest_break_points = models.IntegerField(default=0, help_text="Najwyższy break w całym turnieju")
    highest_break_player = models.ForeignKey(
        'Player', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='competition_high_breaks',
        help_text="Autor najwyższego breaka"
    )

    # --- UCZESTNICY ---
    players = models.ManyToManyField('Player', related_name='competitions', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def is_active(self):
        # Turniej jest aktywny TYLKO gdy ma status ACTIVE
        # Daty są pomocnicze, ale decyduje status nadany przez organizatora
        return self.status == 'ACTIVE'

    @property
    def is_finished(self):
        return self.status == 'FINISHED'

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date cannot be earlier than start date.')

    def get_stages(self):
        stages = []
        if hasattr(self, 'groupstage_stages'):
            stages.extend(list(self.groupstage_stages.all()))

        if hasattr(self, 'knockoutstage_stages'):
            stages.extend(list(self.knockoutstage_stages.all()))

        return sorted(stages, key=lambda x: x.order)

    @property
    def winner(self):
        # Pobieramy wynik z CompetitionResult gdzie result to WINNER
        res = self.results.filter(result='WINNER').first()
        return res.player if res else None


class Stage(models.Model):
    """Abstrakcyjny model etapu (wspólny dla Grup i Pucharu)"""
    name = models.CharField(max_length=100, help_text="E.g. 'Group Stage' or 'Finals'")
    competition = models.ForeignKey('Competition', related_name='%(class)s_stages', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1, help_text="Tournament stage order (1, 2, 3...)")
    is_finished = models.BooleanField(default=False)

    # --- NOWE POLA: REKORD ETAPU ---
    highest_break_points = models.IntegerField(default=0, help_text="The highest break in this stage")
    highest_break_player = models.ForeignKey(
        'Player', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='%(class)s_high_breaks',  # Django stworzy unikalne nazwy dla Group i Knockout
        help_text="Author of the highest break in this stage"
    )

    class Meta:
        abstract = True
        ordering = ['order']

    def __str__(self):
        return f"{self.name} ({self.competition.name})"


class GroupStage(Stage):
    # --- KONFIGURACJA GRUP ---
    num_groups = models.IntegerField(validators=[MinValueValidator(1)])
    players_per_group = models.IntegerField(validators=[MinValueValidator(2)])
    matches_per_pair = models.IntegerField(default=1, validators=[MinValueValidator(1)])

    # --- NOWE POLE: Automatyczny awans ---
    num_qualifiers = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="Ilu graczy automatycznie awansuje z grupy?"
    )

    # --- ZASADY PUNKTACJI ---
    points_for_win = models.IntegerField(default=3)
    points_for_draw = models.IntegerField(default=1)
    points_for_loss = models.IntegerField(default=0)
    allow_draws = models.BooleanField(default=True)

    def create_groups_and_matches(self, default_frames, selected_players=None):
        """Generuje grupy i mecze w systemie Round Robin (każdy z każdym z podziałem na kolejki)."""
        from .models import Group, GroupStanding, Match

        if selected_players:
            players = list(selected_players)
        else:
            players = list(self.competition.players.all())

        random.shuffle(players)
        comp_owner = self.competition.owner
        total_players = len(players)

        # Czyścimy stare grupy
        self.groups.all().delete()

        for i in range(self.num_groups):
            group_name_str = str(i + 1)

            # 1. Tworzymy obiekt GRUPY
            group = Group.objects.create(
                stage=self,
                name=group_name_str
            )

            # Dobieramy graczy do grupy
            start_idx = i * self.players_per_group
            end_idx = start_idx + self.players_per_group
            group_players = players[start_idx:end_idx] if start_idx < total_players else []

            if len(group_players) < 2:
                continue

            # 2. Tworzymy TABELĘ
            for player in group_players:
                GroupStanding.objects.create(
                    group=group, player=player, points=0,
                    matches_played=0, matches_won=0, matches_drawn=0, matches_lost=0,
                    frames_won=0, frames_lost=0,
                    small_points_scored=0, small_points_conceded=0, highest_break=0,
                    is_qualified=False
                )

            # 3. GENEROWANIE MECZY (Algorytm Round Robin / Kołowy)
            # Dzięki temu mamy ładne kolejki (Round 1, Round 2...)

            # Kopia listy graczy do rotacji
            rotation_players = list(group_players)

            # Jeśli nieparzysta liczba graczy, dodajemy "Ducha" (Bye)
            if len(rotation_players) % 2 != 0:
                rotation_players.append(None)

            num_participants = len(rotation_players)
            num_rounds = num_participants - 1
            half = num_participants // 2

            # Pętla rewanżowa (jeśli matches_per_pair > 1)
            for leg in range(self.matches_per_pair):

                # Resetujemy ustawienie graczy dla nowej rundy rewanżowej
                current_rotation = list(rotation_players)

                for round_idx in range(num_rounds):
                    # Obliczamy faktyczny numer kolejki (uwzględniając rewanże)
                    # Np. przy 4 graczach: Rundy 1-3, potem rewanże 4-6
                    actual_round_number = (leg * num_rounds) + round_idx + 1

                    for j in range(half):
                        p1 = current_rotation[j]
                        p2 = current_rotation[num_participants - 1 - j]

                        # Jeśli obaj istnieją (żaden nie jest "Duchem"), tworzymy mecz
                        if p1 and p2:
                            # Zamieniamy gospodarza z gościem w rundach rewanżowych (dla porządku)
                            if leg % 2 == 1:
                                host, guest = p2, p1
                            else:
                                host, guest = p1, p2

                            Match.objects.create(
                                owner=comp_owner,
                                is_public=self.competition.is_public,
                                date=self.competition.start_date,  # Data do edycji później
                                time=timezone.now().time(),
                                venue=self.competition.venue,
                                number_of_frames=default_frames,
                                game_variant=self.competition.game_variant,
                                allow_draws=self.allow_draws,
                                group_stage=self,
                                group=group,
                                group_name=group.name,
                                status='SCHEDULED',
                                player1=host,
                                player2=guest,
                                round_number=actual_round_number  # <--- TU ZAPISUJEMY KOLEJKĘ
                            )

                    # Rotacja zawodników (Algorytm Berger)
                    # Zostawiamy pierwszego (indeks 0) w miejscu, resztę przesuwamy
                    # [0, 1, 2, 3] -> [0, 3, 1, 2]
                    current_rotation.insert(1, current_rotation.pop())

    def regenerate_schedule(self):
        """
        Regeneruje mecze dla aktualnego składu grup (bez usuwania grup).
        Używane po ręcznej edycji (Manage Groups).
        """
        from .models import Match

        # 1. Zabezpieczenie: Jeśli są zakończone mecze, nie dotykamy!
        if self.matches.filter(status='FINISHED').exists():
            return False, "Cannot regenerate schedule because some matches are already finished."

        # 2. Pobieramy ustawienia z istniejących meczów (zanim je usuniemy)
        # Żeby wiedzieć ile frame'ów grać.
        sample_match = self.matches.first()
        frames_count = sample_match.number_of_frames if sample_match else 2  # Domyślnie 2 jakby co

        # 3. Usuwamy tylko mecze (SCHEDULED)
        self.matches.all().delete()

        # 4. Generujemy nowe pary dla każdej grupy (Logika Round Robin)
        comp_owner = self.competition.owner

        for group in self.groups.all():
            # Pobieramy graczy z tabeli tej grupy
            group_players = [standing.player for standing in group.standings.all()]

            if len(group_players) < 2:
                continue

            # --- Algorytm Round Robin (ten sam co przy tworzeniu) ---
            rotation_players = list(group_players)
            if len(rotation_players) % 2 != 0:
                rotation_players.append(None)  # "Duch"

            num_participants = len(rotation_players)
            num_rounds = num_participants - 1
            half = num_participants // 2

            for leg in range(self.matches_per_pair):
                current_rotation = list(rotation_players)

                for round_idx in range(num_rounds):
                    actual_round_number = (leg * num_rounds) + round_idx + 1

                    for j in range(half):
                        p1 = current_rotation[j]
                        p2 = current_rotation[num_participants - 1 - j]

                        if p1 and p2:
                            if leg % 2 == 1:
                                host, guest = p2, p1
                            else:
                                host, guest = p1, p2

                            Match.objects.create(
                                owner=comp_owner,
                                is_public=self.competition.is_public,
                                date=self.competition.start_date,
                                time=timezone.now().time(),
                                venue=self.competition.venue,
                                number_of_frames=frames_count,
                                game_variant=self.competition.game_variant,
                                allow_draws=self.allow_draws,
                                group_stage=self,
                                group=group,
                                group_name=group.name,
                                status='SCHEDULED',
                                player1=host,
                                player2=guest,
                                round_number=actual_round_number
                            )

                    current_rotation.insert(1, current_rotation.pop())

        return True, "Schedule regenerated successfully."


class KnockoutStage(Stage):
    # --- KONFIGURACJA DRABINKI ---
    num_rounds = models.IntegerField(validators=[MinValueValidator(1)],
                                     help_text="Liczba rund (np. 3 dla ćwierćfinałów: 1/4 -> 1/2 -> Finał)")
    frames_per_match = models.IntegerField(validators=[MinValueValidator(1)])

    # Opcjonalnie: Mecz o 3 miejsce?
    has_third_place_match = models.BooleanField(default=False)

    def create_knockout_matches(self, selected_players=None):
        """Tworzy drabinkę."""
        if selected_players:
            players = list(selected_players)
        else:
            players = list(self.competition.players.all())

        random.shuffle(players)
        comp_owner = self.competition.owner
        current_round_matches = len(players) // 2

        if current_round_matches < 1:
            return

        for round_num in range(self.num_rounds):
            if current_round_matches < 1:
                break

            round_name = self._get_round_name(current_round_matches)

            # round_num idzie od 0. Zapiszmy w bazie jako 1, 2, 3...
            db_round_number = round_num + 1

            for i in range(current_round_matches):
                p1 = None
                p2 = None

                if round_num == 0:
                    idx1 = 2 * i
                    idx2 = 2 * i + 1
                    if idx1 < len(players): p1 = players[idx1]
                    if idx2 < len(players): p2 = players[idx2]

                Match.objects.create(
                    owner=comp_owner,
                    is_public=self.competition.is_public,
                    date=self.competition.start_date + timedelta(days=round_num),
                    time=timezone.now().replace(second=0, microsecond=0).time(),
                    venue=self.competition.venue,
                    number_of_frames=self.frames_per_match,
                    game_variant=self.competition.game_variant,
                    allow_draws=False,
                    knockout_stage=self,
                    knockout_name=round_name,
                    status='SCHEDULED',
                    player1=p1,
                    player2=p2,
                    round_number=db_round_number  # <--- ZAPISUJEMY RUNDĘ
                )

            current_round_matches = current_round_matches // 2

        # Mecz o 3. miejsce
        if self.has_third_place_match and self.num_rounds > 1:
            Match.objects.create(
                owner=comp_owner,
                is_public=self.competition.is_public,
                date=self.competition.start_date + timedelta(days=self.num_rounds - 1),
                time=timezone.now().time(),
                venue=self.competition.venue,
                number_of_frames=self.frames_per_match,
                game_variant=self.competition.game_variant,
                allow_draws=False,
                knockout_stage=self,
                knockout_name="3rd Place Match",
                status='SCHEDULED',
                round_number=99  # Specjalny numer dla meczu o 3 miejsce
            )

    def _get_round_name(self, matches_count):
        """
        Zwraca nazwę rundy na podstawie liczby meczów w tej rundzie.
        4 mecze -> Ćwierćfinał
        2 mecze -> Półfinał
        1 mecz  -> Finał
        """
        if matches_count == 1:
            return "Final"
        elif matches_count == 2:
            return "Semi-Final"
        elif matches_count == 4:
            return "Quarter-Final"
        elif matches_count == 8:
            return "Last 16"
        else:
            return f"Round of {matches_count * 2}"

    def clean(self):
        super().clean()
        if self.num_rounds is not None and self.num_rounds < 1:
            raise ValidationError('Number of rounds must be at least 1.')

    class Meta(Stage.Meta):
        verbose_name = 'Knockout Stage'
        verbose_name_plural = 'Knockout Stages'


# --- 4. EQUIPMENT (Historia Sprzętu - Wersja PRO) ---
class Equipment(models.Model):
    # Typy sprzętu
    TYPE_CHOICES = [
        ('CUE', 'Snooker Cue'),
        ('TIP', 'Cue Tip'),
        ('CHALK', 'Chalk'),
        ('CASE', 'Cue Case'),
        ('OTHER', 'Other'),
    ]

    # Jednostki i Opcje
    WEIGHT_UNITS = [('OZ', 'oz'), ('G', 'g')]
    LENGTH_UNITS = [('INCH', 'inch'), ('CM', 'cm')]
    JOINT_CHOICES = [('1PC', '1-piece'), ('3/4', '3/4'), ('2PC', '1/2 (Center)'), ('4/4', '4/4')]
    HARDNESS_CHOICES = [
        ('SS', 'Super Soft'), ('S', 'Soft'), ('M', 'Medium'),
        ('H', 'Hard'), ('XH', 'Extra Hard')
    ]
    SHAFT_MATERIALS = [('ASH', 'Ash (Jesion)'), ('MAPLE', 'Maple (Klon)'), ('CARBON', 'Carbon'), ('OTHER', 'Other')]

    # Relacje
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='equipment')

    # Podstawowe
    item_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='CUE')
    brand = models.CharField(max_length=50, blank=True, null=True, verbose_name="Manufacturer/Brand")
    name = models.CharField(max_length=100, help_text="Model name or custom name")

    # --- SPECYFIKACJA (Detale) ---
    # Kij
    shaft_material = models.CharField(max_length=10, choices=SHAFT_MATERIALS, blank=True, null=True)
    joint_type = models.CharField(max_length=5, choices=JOINT_CHOICES, blank=True, null=True)

    # Waga
    weight_value = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Weight")
    weight_unit = models.CharField(max_length=4, choices=WEIGHT_UNITS, default='OZ', blank=True, null=True)

    # Długość
    length_value = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Length")
    length_unit = models.CharField(max_length=4, choices=LENGTH_UNITS, default='INCH', blank=True, null=True)

    # Ferula
    ferrule_material = models.CharField(max_length=30, blank=True, null=True, help_text="e.g. Brass, Titanium")
    ferrule_size = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=True,
                                       help_text="Diameter in mm")

    # Tip
    tip_hardness = models.CharField(max_length=3, choices=HARDNESS_CHOICES, blank=True, null=True)
    tip_diameter = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=True,
                                       verbose_name="Tip Size (mm)")

    # Logika i Historia
    start_date = models.DateField(help_text="Start date of usage")
    end_date = models.DateField(null=True, blank=True, help_text="Leave empty if currently in use")
    notes = models.TextField(blank=True, null=True)

    def is_active(self):
        return self.end_date is None

    def __str__(self):
        brand_str = f"{self.brand} " if self.brand else ""
        return f"{brand_str}{self.name} ({self.get_item_type_display()})"


class EquipmentPhoto(models.Model):
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='equipment_photos/')
    is_main = models.BooleanField(default=False, help_text="Is this the main photo for the list?")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Jeśli to zdjęcie jest główne, odznacz inne główne dla tego sprzętu
        if self.is_main:
            EquipmentPhoto.objects.filter(equipment=self.equipment).update(is_main=False)
        super().save(*args, **kwargs)


# --- 5. TRAINING SESSION (Dziennik Treningowy) ---
class TrainingSession(models.Model):
    TYPE_CHOICES = [
        ('SOLO', 'Solo Practice'),
        ('LINEUP', 'Line-up / Drills'),
        ('SPARING', 'Sparing (No Match)'),
        ('COACHING', 'Coaching Session'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, blank=True)

    date = models.DateField(default=timezone.now)
    duration_minutes = models.PositiveIntegerField(help_text="Duration in minutes", default=60)
    session_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='SOLO')

    notes = models.TextField(blank=True, null=True, help_text="What did you practice? How did it go?")
    rating = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Self-rating (1-10)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Training {self.date} - {self.get_session_type_display()}"


# --- 6. COMPETITION RESULT (Osiągnięcia Turniejowe) ---
class CompetitionResult(models.Model):
    RESULT_CHOICES = [
        # --- PODIUM ---
        ('WINNER', 'Winner 🏆'),
        ('RUNNER_UP', 'Runner-up 🥈'),
        ('THIRD_PLACE', '3rd Place 🥉'),
        ('FOURTH_PLACE', '4th Place'),

        # --- ETAPY DYNAMICZNE ---
        ('KNOCKOUT_ROUND', 'Knockout Round (Last X)'),  # Np. Last 16, Last 128
        ('GROUP_STAGE', 'Group Stage'),  # Np. Grupy I, Grupy II
        ('QUALIFIER', 'Qualifier'),  # Kwalifikacje
    ]

    competition = models.ForeignKey('Competition', on_delete=models.CASCADE, related_name='results')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='competition_results')

    result = models.CharField(max_length=20, choices=RESULT_CHOICES)

    # --- NOWE MAGICZNE POLE ---
    detail_number = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Dla Knockout: wpisz liczbę (np. 32 dla Last 32). Dla Group: numer etapu (np. 2 dla Group Stage II)."
    )

    rank = models.PositiveIntegerField(
        default=0,
        help_text="Miejsce liczbowo do sortowania (1=Winner, 2=Runner-up, 3=3rd Place, 4=4th Place, 5-8=Quarter...)"
    )

    prize_money = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        # Jeden gracz może mieć tylko jeden wynik końcowy w danym turnieju
        unique_together = ('competition', 'player')
        ordering = ['rank', 'detail_number']  # Sortujemy po randze, a przy remisach po szczegółach

    def __str__(self):
        # Logika inteligentnego wyświetlania nazwy
        if self.result == 'KNOCKOUT_ROUND' and self.detail_number:
            status = f"Last {self.detail_number}"
        elif self.result == 'GROUP_STAGE':
            if self.detail_number and self.detail_number > 1:
                # Zamiana cyfry na rzymską (opcjonalnie) lub po prostu "Stage 2"
                status = f"Group Stage {self.detail_number}"
            else:
                status = "Group Stage"
        else:
            status = self.get_result_display()

        return f"{self.player} - {status} in {self.competition}"


# --- MODEL PROFILU UŻYTKOWNIKA (Avatar, Dane Klubu/Organizatora) ---

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # 1. WIZUALNE
    image = models.ImageField(default='default_profile.jpg', upload_to='profile_pics', blank=True, null=True)

    # 2. DANE ORGANIZATORA / KLUBU
    club_name = models.CharField(max_length=150, blank=True, null=True, help_text="Name of club")
    founded_date = models.DateField(blank=True, null=True, help_text="Date of club foundation")

    # 3. LOKALIZACJA
    address = models.CharField(max_length=255, blank=True, null=True, help_text="Street and number")
    city = models.CharField(max_length=100, blank=True, null=True, help_text="City")

    # 4. INNE
    bio = models.TextField(max_length=500, blank=True, null=True, help_text="A short description about you or the club")

    def __str__(self):
        return f'{self.user.username} Profile'


# --- SYGNAŁY (Bez zmian - niezbędne do automatyzacji) ---

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    instance.profile.save()


# --- SYSTEM RANKINGOWY (Foundation) ---

class Ranking(models.Model):
    """
    Definicja rankingu (np. 'Sezon 2026', 'Liga Wtorkowa', 'Ranking Wszechczasów').
    To jest kontener na punkty graczy.
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rankings')
    name = models.CharField(max_length=100, help_text="Nazwa rankingu, np. 'Sezon 2025/2026'")
    description = models.TextField(blank=True, null=True)

    # Czy ranking jest aktywny (czy pokazywać go na głównej liście)
    is_active = models.BooleanField(default=True)

    # Daty obowiązywania (opcjonalne, do archiwizacji)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class RankingPosition(models.Model):
    """
    Pojedynczy wiersz w rankingu. Przypisuje gracza do rankingu i przechowuje jego statystyki.
    """
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE, related_name='positions')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='ranking_positions')

    # --- GŁÓWNE KRYTERIA ---
    points = models.IntegerField(default=0, help_text="Główne punkty rankingowe")
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                         help_text="Suma wygranych nagród pieniężnych")

    # --- HISTORIA POZYCJI (Do strzałek w górę/w dół) ---
    current_rank = models.IntegerField(default=0, help_text="Aktualna pozycja (obliczana przy aktualizacji)")
    previous_rank = models.IntegerField(default=0, help_text="Poprzednia pozycja (do pokazywania awansów/spadków)")

    # --- STATYSTYKI TURNIEJOWE ---
    tournaments_played = models.IntegerField(default=0, help_text="Liczba rozegranych turniejów w tym cyklu")
    titles_won = models.IntegerField(default=0, help_text="Liczba wygranych turniejów")
    finals_reached = models.IntegerField(default=0, help_text="Liczba finałów")

    # --- STATYSTYKI MECZOWE ---
    matches_played = models.IntegerField(default=0)
    matches_won = models.IntegerField(default=0)
    matches_lost = models.IntegerField(default=0)
    matches_drawn = models.IntegerField(default=0)  # Dla lig z remisami

    # --- STATYSTYKI FREJMOWE (SNOOKER SPECIFIC) ---
    frames_won = models.IntegerField(default=0)
    frames_lost = models.IntegerField(default=0)

    # --- MAŁE PUNKTY (Small Points) ---
    small_points_scored = models.IntegerField(default=0)
    small_points_conceded = models.IntegerField(default=0)

    # --- BREAKI (SNOOKER SPECIFIC) ---
    highest_break = models.IntegerField(default=0)
    centuries_count = models.IntegerField(default=0, help_text="Liczba breaków 100+")
    fifties_count = models.IntegerField(default=0, help_text="Liczba breaków 50+")

    class Meta:
        # Jeden gracz może być tylko raz w danym rankingu
        unique_together = ('ranking', 'player')
        # Domyślne sortowanie: najpierw punkty, potem wygrane turnieje, potem mniej porażek
        ordering = ['-points', '-titles_won', '-matches_won']

    def __str__(self):
        return f"{self.player.last_name} in {self.ranking.name}: {self.points} pts"

    @property
    def frame_difference(self):
        return self.frames_won - self.frames_lost

    @property
    def win_percentage(self):
        if self.matches_played == 0:
            return 0
        return round((self.matches_won / self.matches_played) * 100, 1)


class SharingToken(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sharing_tokens')
    code = models.CharField(max_length=6, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Opcjonalnie: Jeśli kod ma dotyczyć tylko jednego konkretnego gracza
    # Jeśli puste -> oznacza udostępnienie CAŁEJ stajni
    specific_player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, blank=True)

    def is_valid(self):
        # Kod ważny tylko 90 sekund
        return timezone.now() < self.created_at + timedelta(seconds=90)

    def __str__(self):
        return f"Token {self.code} ({self.owner.username})"


# Ten dekorator mówi: "Uruchom mnie, gdy usunięto obiekt Match"
@receiver(post_delete, sender='snooker_app.Match')
def update_stats_on_delete(sender, instance, **kwargs):
    """
    Automatycznie aktualizuje statystyki graczy po usunięciu meczu.
    """
    # Importujemy tutaj, żeby uniknąć błędu "circular import" (pętli importów)
    from .services import update_career_stats

    print(f"--- USUNIĘTO MECZ! Aktualizuję graczy: {instance.player1} i {instance.player2} ---")

    if instance.player1:
        update_career_stats(instance.player1)

    if instance.player2:
        update_career_stats(instance.player2)