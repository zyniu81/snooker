from django.core.validators import MinValueValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

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

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if not is_new:
            self.player_names = ', '.join([player.__str__() for player in self.players.all()])
            self.player_ids = ', '.join([str(player.id) for player in self.players.all()])
            self.referee_names = ', '.join([referee.__str__() for referee in self.referees.all()])
            self.referee_ids = ', '.join([str(referee.id) for referee in self.referees.all()])
            self.full_clean()
            super().save(update_fields=['player_names', 'player_ids', 'referee_names', 'referee_ids'])


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
    teams_per_group = models.IntegerField(validators=[MinValueValidator(2)])

    class Meta(Stage.Meta):
        verbose_name = 'Group Stage'
        verbose_name_plural = 'Group Stages'


class KnockoutStage(Stage):
    num_rounds = models.IntegerField(validators=[MinValueValidator(1)])
    num_participants = models.IntegerField(validators=[MinValueValidator(1)])

    class Meta(Stage.Meta):
        verbose_name = 'Knockout Stage'
        verbose_name_plural = 'Knockout Stages'

    def clean(self):
        if self.num_participants != 2 ** self.num_rounds:
            raise ValidationError('Number of participants must be a power of 2 and match the number of rounds.')


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
    fastest_break = models.DurationField(blank=True, null=True)
    longest_frame_won = models.DurationField(blank=True, null=True)
    consecutive_frames_won = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    consecutive_matches_won = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return f'Achievements for {self.player}'
