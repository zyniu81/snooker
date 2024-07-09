from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField

from datetime import timedelta

import random

# Create your models here.


class Player(models.Model):
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    nickname = models.CharField(max_length=30, blank=True, null=True)
    highest_break = models.IntegerField(blank=True, null=True)
    avg_shot_time = models.DurationField(blank=True, null=True)
    pot_success_percentage = models.FloatField(blank=True, null=True)
    avg_shots_per_match = models.FloatField(blank=True, null=True)
    avg_fouls_per_match = models.FloatField(blank=True, null=True)
    avg_foul_points_per_match = models.FloatField(blank=True, null=True)

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
        if not self.first_name and not self.last_name and not self.nickname:
            if not self.id:
                super().save(*args, **kwargs)
                self.first_name = f'Player {self.id}'
        super().save(*args, **kwargs)

    def formatted_avg_shot_time(self):
        if self.avg_shot_time:
            total_seconds = int(self.avg_shot_time.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            return f'{minutes}:{seconds:02}'
        return "N/A"


class TemporaryPlayer(models.Model):
    name = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Match(models.Model):
    date = models.DateField()
    time = models.TimeField()
    venue = models.ForeignKey('Venue', on_delete=models.SET_NULL, blank=True, null=True)
    number_of_frames = models.PositiveIntegerField()
    players = models.ManyToManyField('Player')
    referees = models.ManyToManyField('Referee', blank=True)
    player_names = models.TextField(blank=True, null=True)
    referee_names = models.TextField(blank=True, null=True)
    player_ids = models.TextField(blank=True, null=True)
    referee_ids = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    group_stage = models.ForeignKey('GroupStage', on_delete=models.SET_NULL, null=True, blank=True, related_name='matches')
    knockout_stage = models.ForeignKey('KnockoutStage', on_delete=models.SET_NULL, null=True, blank=True, related_name='matches')
    temp_player1 = models.ForeignKey('TemporaryPlayer', null=True, blank=True, related_name='temp_player1_matches', on_delete=models.CASCADE)
    temp_player2 = models.ForeignKey('TemporaryPlayer', null=True, blank=True, related_name='temp_player2_matches', on_delete=models.CASCADE)
    is_temporary = models.BooleanField(default=False)
    group_name = models.CharField(max_length=1, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['date', 'time']),
        ]

    def __str__(self):
        return f'Match on {self.date} at {self.time}'

    def clean(self):
        if self.pk:
            if self.players.count() < 2:
                raise ValidationError('A match must have at least two players.')
        if self.number_of_frames <= 0:
            raise ValidationError('The number of frames must be greater than zero.')

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

        if not is_new:
            self.player_names = ', '.join([str(player) for player in self.players.all()])
            self.player_ids = ', '.join([str(player.id) for player in self.players.all()])
            self.referee_names = ', '.join([str(referee) for referee in self.referees.all()])
            self.referee_ids = ', '.join([str(referee.id) for referee in self.referees.all()])
            super().save(update_fields=['player_names', 'player_ids', 'referee_names', 'referee_ids'])

    def is_expired(self):
        return self.is_temporary and self.created_at < timezone.now() - timedelta(days=30)

    def delete_if_expired(self):
        if self.is_expired():
            self.delete()


class MatchPlayer(models.Model):
    match = models.ForeignKey('Match', on_delete=models.CASCADE)
    player = models.ForeignKey('Player', on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField(choices=[(1, 'First'), (2, 'Second')])
    points_scored = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    max_break = models.IntegerField(blank=True, null=True)
    fouls = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    foul_points = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    avg_shot_time = models.DurationField(blank=True, null=True)
    attempts = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    successful_pots = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ('match', 'player')
        indexes = [
            models.Index(fields=['match']),
            models.Index(fields=['player']),
        ]

    def __str__(self):
        return f'{self.player} in {self.match} (Position: {self.get_position_display()})'

    @property
    def pot_success_percentage(self):
        return (self.successful_pots / self.attempts) * 100 if self.attempts > 0 else 0.0

    @property
    def total_points(self):
        return self.points_scored + self.foul_points

    def calculate_points_scored(self):
        opponent_foul_points = \
        self.match.matchplayer_set.exclude(player=self.player).aggregate(models.Sum('foul_points'))['foul_points__sum'] or 0
        self.points_scored += opponent_foul_points

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Frame(models.Model):
    match_player = models.ForeignKey('MatchPlayer', on_delete=models.CASCADE)
    frame_number = models.PositiveIntegerField()
    points_scored_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    points_scored_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    max_break_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    max_break_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    player1_fouls = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    player2_fouls = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    foul_points_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    foul_points_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    winner = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True, related_name='frames_won')
    time_duration = models.DurationField(blank=True, null=True)
    pot_success_percentage_player1 = models.FloatField(default=0.0)
    pot_success_percentage_player2 = models.FloatField(default=0.0)
    safety_shot_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    safety_shot_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    misses_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    misses_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_shots_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_shots_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    break_points_player1 = ArrayField(
        models.IntegerField(validators=[MinValueValidator(10), MaxValueValidator(155)]),
        default=list,
        blank=True
    )
    break_points_player2 = ArrayField(
        models.IntegerField(validators=[MinValueValidator(10), MaxValueValidator(155)]),
        default=list,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('match_player', 'frame_number')


class Referee(models.Model):
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


class Venue(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True, null=True)
    capacity = models.PositiveIntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name


class Competition(models.Model):
    players = models.ManyToManyField('Player', related_name='competitions', blank=True)
    matches = models.ManyToManyField('Match', related_name='competitions', blank=True)
    group_stages = models.ManyToManyField('GroupStage', related_name='competitions', blank=True)
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    venue = models.ForeignKey('Venue', on_delete=models.SET_NULL, blank=True, null=True)
    competition_type = models.CharField(max_length=50, choices=[('Qualifiers', 'Qualifiers'), ('Finals', 'Finals')])
    is_group_stage = models.BooleanField(default=False)
    is_knockout = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def is_active(self):
        return self.start_date <= timezone.now().date() <= self.end_date

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date cannot be earlier than start date.')


class Stage(models.Model):
    name = models.CharField(max_length=100)
    competition = models.ForeignKey('Competition', related_name='%(class)s_stages', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ['order']

    def __str__(self):
        return self.name


class GroupStage(Stage):
    num_groups = models.IntegerField(validators=[MinValueValidator(1)])
    players_per_group = models.IntegerField(validators=[MinValueValidator(2)])
    matches_per_pair = models.IntegerField(default=1, validators=[MinValueValidator(1)])

    def create_groups_and_matches(self, default_frames):
        players = list(self.competition.players.all())
        random.shuffle(players)

        for i in range(self.num_groups):
            group_name = chr(65 + i)
            group_players = players[i*self.players_per_group:(i+1)*self.players_per_group]

            for j, player1 in enumerate(group_players):
                for player2 in group_players[j+1:]:
                    for _ in range(self.matches_per_pair):
                        match = Match.objects.create(
                            date=self.competition.start_date,
                            time=timezone.now().time(),
                            venue=self.competition.venue,
                            number_of_frames=default_frames,
                            group_stage=self,
                            player_names=f"{player1}, {player2}",
                            player_ids=f"{player1.id},{player2.id}",
                            referee_names="",
                            referee_ids="",
                            group_name=group_name
                        )
                        match.players.add(player1, player2)
                        match.save()


class KnockoutStage(Stage):
    num_rounds = models.IntegerField(validators=[MinValueValidator(1)])
    frames_per_match = models.IntegerField(validators=[MinValueValidator(1)])

    def create_knockout_matches(self):
        players = list(self.competition.players.all())
        random.shuffle(players)
        num_matches = 2 ** (self.num_rounds - 1)

        for round_num in range(self.num_rounds):
            round_name = f'Round {round_num + 1}'
            matches_in_round = num_matches // (2 ** round_num)

            for i in range(matches_in_round):
                if round_num == 0:
                    player1 = players[2*i] if 2*i < len(players) else None
                    player2 = players[2*i+1] if 2*i+1 < len(players) else None
                else:
                    player1 = player2 = None

                match = Match.objects.create(
                    date=self.competition.start_date + timedelta(days=round_num),
                    time=timezone.now().time(),
                    venue=self.competition.venue,
                    number_of_frames=self.frames_per_match,
                    knockout_stage=self,
                    player_names="" if not player1 and not player2 else f'{player1},{player2}',
                    player_ids="" if not player1 and not player2 else f"{player1.id},{player2.id}" if player1 and player2 else "",
                    referee_names="",
                    referee_ids="",
                    group_name=round_name
                )
                if player1:
                    match.players.add(player1)
                if player2:
                    match.players.add(player2)
                match.save()

    class Meta(Stage.Meta):
        verbose_name = 'Knockout Stage'
        verbose_name_plural = 'Knockout Stages'

    def clean(self):
        super().clean()
        if self.num_rounds < 1:
            raise ValidationError('Number of rounds must be at least 1.')


class MatchResult(models.Model):
    match = models.ForeignKey('Match', on_delete=models.CASCADE)
    match_score = models.CharField(max_length=10, blank=True, null=True)
    frames = models.JSONField(default=list, blank=True)
    total_fouls = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    player1_fouls = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    player2_fouls = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    player1_breaks = models.JSONField(default=dict)
    player2_breaks = models.JSONField(default=dict)
    match_end_time = models.DateTimeField(blank=True, null=True)
    match_duration = models.DurationField(blank=True, null=True)

    def calculate_match_duration(self):
        if self.match_end_time:
            self.match_duration = self.match_end_time - timezone.datetime.combine(self.match.date, self.match.time)

    def save(self, *args, **kwargs):
        self.calculate_match_duration()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Result for match {self.match}'


class Achievement(models.Model):
    player = models.OneToOneField('Player', on_delete=models.CASCADE)
    breaks = models.JSONField(default=dict)
    matches_won = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    frames_won = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    frames_lost = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    tournaments_won = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    fastest_frame_won = models.DurationField(blank=True, null=True)
    longest_frame_won = models.DurationField(blank=True, null=True)
    consecutive_frames_won = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    consecutive_matches_won = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return f'Achievements for {self.player}'
