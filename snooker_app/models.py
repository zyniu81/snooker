from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import User

from datetime import timedelta
import random


# Create your models here.

class Player(models.Model):
    # --- 1. DANE OSOBOWE I KONFIGURACJA ---
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='players', null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='player_profile')
    is_public = models.BooleanField(default=False)
    is_temporary = models.BooleanField(default=False)

    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    nickname = models.CharField(max_length=30, blank=True, null=True)

    photo = models.ImageField(upload_to='players_photos/', blank=True, null=True)

    # --- 2. STATYSTYKI MECZOWE (Kariera) ---
    matches_played = models.IntegerField(default=0)
    matches_won = models.IntegerField(default=0)
    matches_drawn = models.IntegerField(default=0)  # Nowość
    matches_lost = models.IntegerField(default=0)

    # --- 3. STATYSTYKI FRAME'ÓW (Kariera) ---
    # To jest kluczowe do tabel ligowych (bilans małych punktów/framów)
    frames_played = models.IntegerField(default=0)
    frames_won = models.IntegerField(default=0)
    frames_lost = models.IntegerField(default=0)

    # --- 4. PUNKTY I TECHNIKA ---
    total_career_points = models.BigIntegerField(default=0, help_text="Suma wszystkich wbitych punktów")

    # Średnie statystyki (aktualizowane po każdym meczu)
    global_pot_success = models.FloatField(default=0.0, help_text="Średnia skuteczność wbić z kariery (%)")
    global_safety_success = models.FloatField(default=0.0, help_text="Średnia skuteczność odstawnych z kariery (%)")
    avg_shot_time = models.DurationField(blank=True, null=True, help_text="Średni czas na uderzenie")

    # --- 5. BREAKI (Prestiż) ---
    highest_break = models.IntegerField(default=0)
    centuries_count = models.IntegerField(default=0, help_text="Liczba breaków 100+")
    fifties_count = models.IntegerField(default=0, help_text="Liczba breaków 50+")

    # Histogram breaków kariery (np. {"10-19": 150, "20-29": 40...})
    career_break_stats = models.JSONField(default=dict, blank=True)

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

        # Automatyczne nadawanie nazwy jeśli pusta
        if is_new and not (self.first_name or self.last_name or self.nickname):
            self.first_name = f'Player {self.id}'
            super().save(update_fields=['first_name'])

    def formatted_avg_shot_time(self):
        if self.avg_shot_time:
            total_seconds = int(self.avg_shot_time.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            return f'{minutes}:{seconds:02}'
        return "N/A"


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

    number_of_frames = models.PositiveIntegerField()
    allow_draws = models.BooleanField(default=False)

    # --- 2. GRACZE I SĘDZIOWIE ---
    players = models.ManyToManyField('Player')
    referees = models.ManyToManyField('Referee', blank=True, related_name='matches')

    # Cache nazw (tekstowe)
    player_names = models.TextField(blank=True, null=True)
    referee_names = models.TextField(blank=True, null=True)
    player_ids = models.TextField(blank=True, null=True)
    referee_ids = models.TextField(blank=True, null=True)

    # --- 3. STRUKTURA TURNIEJOWA ---
    group_stage = models.ForeignKey('GroupStage', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='matches')
    knockout_stage = models.ForeignKey('KnockoutStage', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='matches')
    group_name = models.CharField(max_length=1, blank=True, null=True)
    knockout_name = models.CharField(max_length=100, blank=True, null=True)

    # --- 4. WYNIKI KOŃCOWE (Podsumowanie) ---
    winner = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_matches')

    final_score_player1 = models.IntegerField(default=0, help_text="Wygrane frame'y P1")
    final_score_player2 = models.IntegerField(default=0, help_text="Wygrane frame'y P2")

    total_points_player1 = models.IntegerField(default=0, help_text="Suma małych punktów P1")
    total_points_player2 = models.IntegerField(default=0, help_text="Suma małych punktów P2")

    # --- 5. STATYSTYKI CZASOWE ---
    total_duration = models.DurationField(blank=True, null=True, help_text="Suma czasu gry netto")
    avg_frame_time = models.DurationField(blank=True, null=True)
    min_frame_time = models.DurationField(blank=True, null=True)
    max_frame_time = models.DurationField(blank=True, null=True)

    # --- 6. STATYSTYKI TECHNICZNE (Średnie/Sumy) ---
    pot_success_p1 = models.FloatField(default=0.0)
    pot_success_p2 = models.FloatField(default=0.0)

    safety_success_p1 = models.FloatField(default=0.0)
    safety_success_p2 = models.FloatField(default=0.0)

    total_fouls_p1 = models.IntegerField(default=0)
    total_fouls_p2 = models.IntegerField(default=0)
    foul_points_conceded_p1 = models.IntegerField(default=0)
    foul_points_conceded_p2 = models.IntegerField(default=0)

    # --- 7. BREAKI I SERIE ---
    highest_break_p1 = models.IntegerField(default=0)
    highest_break_p2 = models.IntegerField(default=0)

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

    class Meta:
        indexes = [
            models.Index(fields=['date', 'time']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.player_names} - {self.date}'

    def get_game_status(self):
        # Pobieramy listę graczy
        players = list(self.players.all())

        # Zabezpieczenie: jeśli nie ma 2 graczy, nie ma gry
        if len(players) < 2:
            return {'is_finished': False, 'winner': None}

        p1 = players[0]
        p2 = players[1]

        # LICZYMY ZWYCIĘSTWA WPROST Z TABELI FRAME (To naprawia błędy zliczania)
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
        players = list(self.players.all())
        if len(players) < 2:
            return 0, 0

        p1 = players[0]
        p2 = players[1]

        # Liczymy wygrane framy
        p1_score = Frame.objects.filter(match_player__match=self, winner=p1).count()
        p2_score = Frame.objects.filter(match_player__match=self, winner=p2).count()

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
        # 1. Sprawdzamy liczbę framów TYLKO jeśli została podana (nie jest None)
        if self.number_of_frames is not None and self.number_of_frames <= 0:
            raise ValidationError('The number of frames must be greater than zero.')

        # 2. Walidacja liczby graczy (tylko dla istniejących obiektów)
        if self.pk:
            if self.players.count() < 2:
                # Opcjonalnie można rzucić błąd, ale przy tworzeniu (create)
                # gracze dodawani są PO zapisie, więc tu często bywa pusto.
                pass

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
        super().save(*args, **kwargs)

        # Aktualizacja nazw graczy w polach tekstowych (dla szybszego odczytu)
        if not is_new:
            self.player_names = ', '.join([str(player) for player in self.players.all()])
            self.player_ids = ', '.join([str(player.id) for player in self.players.all()])
            self.referee_names = ', '.join([str(referee) for referee in self.referees.all()])
            self.referee_ids = ', '.join([str(referee.id) for referee in self.referees.all()])
            # Zapisujemy tylko zaktualizowane pola, żeby nie robić pętli
            super().save(update_fields=['player_names', 'player_ids', 'referee_names', 'referee_ids'])

    def is_expired(self):
        return self.is_temporary and self.created_at < timezone.now() - timedelta(days=30)

    def delete_if_expired(self):
        if self.is_expired():
            self.delete()

    def delete(self, *args, **kwargs):
        # 1. Znajdujemy graczy tymczasowych powiązanych z TYM meczem
        # Używamy list(), aby pobrać ich do pamięci przed usunięciem meczu
        temp_players_to_check = list(self.players.filter(is_temporary=True))

        # 2. Wykonujemy standardowe usuwanie meczu
        super().delete(*args, **kwargs)

        # 3. Sprzątanie sierot (Orphan Cleanup)
        for player in temp_players_to_check:
            # Sprawdzamy, czy ten gracz jest przypisany do jakichkolwiek innych meczów.
            # Ponieważ właśnie usunęliśmy bieżący mecz, jeśli był to jego jedyny mecz,
            # licznik wyniesie 0.
            if player.match_set.count() == 0:
                player.delete()


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
        ('ACTIVE', 'Active'),
        ('FINISHED', 'Finished'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')

    # --- 3. KONFIGURACJA GRY ---
    game_variant = models.CharField(
        max_length=20,
        choices=Match.VARIANT_CHOICES,
        default='STANDARD',
        help_text="Domyślny wariant gry dla wszystkich meczów w turnieju"
    )

    # --- 4. UCZESTNICY ---
    players = models.ManyToManyField('Player', related_name='competitions', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def is_active(self):
        # Turniej jest aktywny jeśli daty pasują I status nie jest FINISHED
        return (self.start_date <= timezone.now().date() <= self.end_date) and self.status != 'FINISHED'

    @property
    def is_finished(self):
        return self.status == 'FINISHED'

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date cannot be earlier than start date.')

    def get_stages(self):
        stages = []
        stages.extend(list(self.group_stages.all()))
        stages.extend(list(self.knockout_stages.all()))
        return sorted(stages, key=lambda x: x.order)


class Stage(models.Model):
    """Abstrakcyjny model etapu (wspólny dla Grup i Pucharu)"""
    name = models.CharField(max_length=100, help_text="Np. 'Faza Grupowa' lub 'Finały'")
    competition = models.ForeignKey('Competition', related_name='%(class)s_stages', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1, help_text="Kolejność etapu w turnieju (1, 2, 3...)")
    is_finished = models.BooleanField(default=False)

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

    # --- ZASADY PUNKTACJI ---
    points_for_win = models.IntegerField(default=3)
    points_for_draw = models.IntegerField(default=1)
    points_for_loss = models.IntegerField(default=0)
    allow_draws = models.BooleanField(default=True)

    def create_groups_and_matches(self, default_frames, selected_players=None):
        """Generuje mecze systemem każdy z każdym w grupach dla WYBRANYCH graczy"""

        # 1. Sprawdzamy czy wybrano konkretnych graczy
        if selected_players:
            players = list(selected_players)
        else:
            players = list(self.competition.players.all())

        random.shuffle(players)
        comp_owner = self.competition.owner
        total_players = len(players)

        for i in range(self.num_groups):
            group_letter = chr(65 + i)
            start_idx = i * self.players_per_group
            end_idx = start_idx + self.players_per_group
            group_players = players[start_idx:end_idx] if start_idx < total_players else []

            if len(group_players) < 2:
                continue

            for j, player1 in enumerate(group_players):
                for player2 in group_players[j + 1:]:
                    for _ in range(self.matches_per_pair):
                        match = Match.objects.create(
                            owner=comp_owner,
                            is_public=self.competition.is_public,
                            date=self.competition.start_date,
                            time=timezone.now().time(),
                            venue=self.competition.venue,
                            number_of_frames=default_frames,
                            game_variant=self.competition.game_variant,
                            allow_draws=self.allow_draws,
                            group_stage=self,
                            group_name=group_letter,
                            status='SCHEDULED'
                        )
                        match.players.add(player1, player2)
                        match.save()


class KnockoutStage(Stage):
    # --- KONFIGURACJA DRABINKI ---
    num_rounds = models.IntegerField(validators=[MinValueValidator(1)],
                                     help_text="Liczba rund (np. 3 dla ćwierćfinałów: 1/4 -> 1/2 -> Finał)")
    frames_per_match = models.IntegerField(validators=[MinValueValidator(1)])

    # Opcjonalnie: Mecz o 3 miejsce?
    has_third_place_match = models.BooleanField(default=False)

    def create_knockout_matches(self, selected_players=None):
        """Tworzy drabinkę BAZUJĄC NA LICZBIE GRACZY, a nie tylko na liczbie rund."""

        # 1. Pobieramy graczy
        if selected_players:
            players = list(selected_players)
        else:
            players = list(self.competition.players.all())

        # Mieszamy ich
        random.shuffle(players)
        comp_owner = self.competition.owner

        # 2. Obliczamy startową liczbę meczów na podstawie liczby graczy
        # Np. 8 graczy = 4 mecze. 5 graczy = 2 mecze (jeden ma wolny los).
        current_round_matches = len(players) // 2

        if current_round_matches < 1:
            return  # Zabezpieczenie: za mało graczy na cokolwiek

        # 3. Pętla po rundach, o które prosił użytkownik
        for round_num in range(self.num_rounds):

            # Jeśli w wyniku dzielenia zeszliśmy do 0 meczów, przerywamy (np. użytkownik chciał 5 rund dla 4 graczy)
            if current_round_matches < 1:
                break

            # Ustalamy nazwę rundy
            # Przekazujemy aktualną liczbę meczów, żeby funkcja wiedziała czy to Finał (1 mecz) czy Ćwierćfinał (4 mecze)
            round_name = self._get_round_name(current_round_matches)

            for i in range(current_round_matches):
                p1 = None
                p2 = None

                # Tylko w pierwszej rundzie (round_num == 0) obsadzamy graczy
                if round_num == 0:
                    # Wyciągamy parę graczy z listy
                    idx1 = 2 * i
                    idx2 = 2 * i + 1
                    # Sprawdzamy czy nie wyszliśmy poza listę (safety check)
                    if idx1 < len(players): p1 = players[idx1]
                    if idx2 < len(players): p2 = players[idx2]

                match = Match.objects.create(
                    owner=comp_owner,
                    is_public=self.competition.is_public,
                    date=self.competition.start_date + timedelta(days=round_num),
                    time=timezone.now().time(),
                    venue=self.competition.venue,
                    number_of_frames=self.frames_per_match,
                    game_variant=self.competition.game_variant,
                    allow_draws=False,
                    knockout_stage=self,
                    knockout_name=round_name,
                    status='SCHEDULED'
                )

                if p1: match.players.add(p1)
                if p2: match.players.add(p2)
                match.save()

            # --- PRZYGOTOWANIE DO KOLEJNEJ RUNDY ---
            # W następnej rundzie będzie połowa meczów (zwycięzcy par)
            current_round_matches = current_round_matches // 2

        # --- Mecz o 3. miejsce (opcjonalny) ---
        if self.has_third_place_match and self.num_rounds > 1:
            # Tworzymy go tylko, jeśli turniej ma sensowną długość
            match_3rd = Match.objects.create(
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
                status='SCHEDULED'
            )
            match_3rd.save()

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


# --- 4. EQUIPMENT (Historia Sprzętu) ---
class Equipment(models.Model):
    TYPE_CHOICES = [
        ('CUE', 'Snooker Cue'),
        ('TIP', 'Cue Tip'),
        ('CHALK', 'Chalk'),
        ('CASE', 'Cue Case'),
        ('OTHER', 'Other'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='equipment')

    name = models.CharField(max_length=100, help_text="e.g. Parris Cues Ultimate")
    item_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='CUE')

    start_date = models.DateField(help_text="When did you start using this?")
    end_date = models.DateField(null=True, blank=True, help_text="Leave empty if currently in use")

    notes = models.TextField(blank=True, null=True)

    def is_active(self):
        return self.end_date is None

    def __str__(self):
        return f"{self.name} ({self.get_item_type_display()})"


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