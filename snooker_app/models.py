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
    is_public = models.BooleanField(default=False)
    is_temporary = models.BooleanField(default=False)

    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    nickname = models.CharField(max_length=30, blank=True, null=True)

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
    # --- NOWE POLA WŁASNOŚCI ---
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='venues')
    is_public = models.BooleanField(default=False)
    # ---------------------------

    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True, null=True)
    capacity = models.PositiveIntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    tables_count = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(0)],
        help_text="Number of tables (optional)"
    )

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

    matches = models.ManyToManyField('Match', blank=True)

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
    referees = models.ManyToManyField('Referee', blank=True)

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

    # --- 3. KONFIGURACJA GRY ---
    # Turniej narzuca wariant gry wszystkim meczom (np. cały turniej to 6-Red)
    game_variant = models.CharField(
        max_length=20,
        choices=Match.VARIANT_CHOICES,
        default='STANDARD',
        help_text="Domyślny wariant gry dla wszystkich meczów w turnieju"
    )

    # --- 4. UCZESTNICY ---
    players = models.ManyToManyField('Player', related_name='competitions', blank=True)
    # Relacja do meczów jest w drugą stronę (Mecz wskazuje na Stage),
    # ale możemy dodać helper, żeby łatwo pobrać wszystkie mecze turnieju.

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def is_active(self):
        return self.start_date <= timezone.now().date() <= self.end_date

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date cannot be earlier than start date.')

    def get_stages(self):
        """Zwraca wszystkie etapy turnieju w kolejności (Grupy, potem Puchar itd.)"""
        stages = []
        stages.extend(list(self.group_stages.all()))
        stages.extend(list(self.knockout_stages.all()))
        # Sortujemy po polu 'order'
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

    # --- ZASADY PUNKTACJI (TABELA) ---
    points_for_win = models.IntegerField(default=3)
    points_for_draw = models.IntegerField(default=1)
    points_for_loss = models.IntegerField(default=0)

    # Czy w grupie można remisować? (Zazwyczaj TAK)
    allow_draws = models.BooleanField(default=True)

    def create_groups_and_matches(self, default_frames):
        """Generuje mecze systemem każdy z każdym w grupach"""
        players = list(self.competition.players.all())
        random.shuffle(players)

        comp_owner = self.competition.owner

        # Obliczamy ile osób weszło
        total_players = len(players)

        # Proste dzielenie na grupy (można ulepszyć, jeśli liczba nie jest podzielna)
        for i in range(self.num_groups):
            group_letter = chr(65 + i)  # A, B, C...

            # Wyciągamy wycinek listy graczy dla tej grupy
            start_idx = i * self.players_per_group
            end_idx = start_idx + self.players_per_group
            # Zabezpieczenie przed wyjściem poza listę
            group_players = players[start_idx:end_idx] if start_idx < total_players else []

            if len(group_players) < 2:
                continue  # Pomijamy puste grupy lub z 1 graczem

            # Algorytm każdy z każdym (Round Robin)
            for j, player1 in enumerate(group_players):
                for player2 in group_players[j + 1:]:
                    for _ in range(self.matches_per_pair):
                        match = Match.objects.create(
                            owner=comp_owner,
                            is_public=self.competition.is_public,

                            # Czas i Miejsce
                            date=self.competition.start_date,
                            time=timezone.now().time(),  # Domyślnie teraz, do edycji później
                            venue=self.competition.venue,

                            # Zasady
                            number_of_frames=default_frames,
                            game_variant=self.competition.game_variant,  # Dziedziczy z turnieju
                            allow_draws=self.allow_draws,  # Z konfiguracji etapu

                            # Powiązanie z Etapem
                            group_stage=self,
                            group_name=group_letter,

                            status='SCHEDULED'
                        )
                        # Dodajemy graczy (nazwy uzupełnią się same w match.save())
                        match.players.add(player1, player2)
                        match.save()


class KnockoutStage(Stage):
    # --- KONFIGURACJA DRABINKI ---
    num_rounds = models.IntegerField(validators=[MinValueValidator(1)],
                                     help_text="Liczba rund (np. 3 dla ćwierćfinałów: 1/4 -> 1/2 -> Finał)")
    frames_per_match = models.IntegerField(validators=[MinValueValidator(1)])

    # Opcjonalnie: Mecz o 3 miejsce?
    has_third_place_match = models.BooleanField(default=False)

    def create_knockout_matches(self):
        """Tworzy pustą drabinkę turniejową"""
        players = list(self.competition.players.all())
        # Tutaj można dodać logikę rozstawienia (seeding), na razie losowo
        random.shuffle(players)

        comp_owner = self.competition.owner

        # Liczba meczów w pierwszej rundzie: 2^(n-1)
        # Np. dla 3 rund (ćwierćfinał): 2^2 = 4 mecze
        initial_matches_count = 2 ** (self.num_rounds - 1)

        for round_num in range(self.num_rounds):
            round_name = self._get_round_name(round_num, self.num_rounds)

            # W każdej kolejnej rundzie jest połowa meczów z poprzedniej
            matches_in_current_round = initial_matches_count // (2 ** round_num)

            for i in range(matches_in_current_round):
                # Tylko w pierwszej rundzie od razu obsadzamy graczy (jeśli są dostępni)
                p1 = None
                p2 = None

                if round_num == 0:
                    idx1 = 2 * i
                    idx2 = 2 * i + 1
                    if idx1 < len(players): p1 = players[idx1]
                    if idx2 < len(players): p2 = players[idx2]

                match = Match.objects.create(
                    owner=comp_owner,
                    is_public=self.competition.is_public,

                    # Daty przesuwamy o liczbę rund (np. 1 runda w poniedziałek, 2 we wtorek)
                    date=self.competition.start_date + timedelta(days=round_num),
                    time=timezone.now().time(),
                    venue=self.competition.venue,

                    # Zasady
                    number_of_frames=self.frames_per_match,
                    game_variant=self.competition.game_variant,
                    allow_draws=False,  # W pucharze NIE MA remisów

                    # Powiązanie
                    knockout_stage=self,
                    knockout_name=round_name,

                    status='SCHEDULED'
                )

                if p1: match.players.add(p1)
                if p2: match.players.add(p2)
                match.save()

    def _get_round_name(self, round_index, total_rounds):
        """Pomocnicza nazwa rundy (np. Półfinał)"""
        diff = total_rounds - 1 - round_index
        if diff == 0: return "Final"
        if diff == 1: return "Semi-Final"
        if diff == 2: return "Quarter-Final"
        return f"Round {round_index + 1}"

    def clean(self):
        super().clean()
        if self.num_rounds is not None and self.num_rounds < 1:
            raise ValidationError('Number of rounds must be at least 1.')

    class Meta(Stage.Meta):
        verbose_name = 'Knockout Stage'
        verbose_name_plural = 'Knockout Stages'