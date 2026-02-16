from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import User
from django.dispatch import receiver

from datetime import timedelta
import random


# Create your models here.

class Player(models.Model):
    # --- 1. PERSONAL DATA AND CONFIGURATION ---
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='players', null=True, blank=True)

    # For Sub-Admin:
    managed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='managed_players',
        null=True,
        blank=True,
        help_text="Designated manager (Sub-Admin) for this player"
    )

    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='player_profile')

    # Link to original:
    cloned_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clones',
        help_text="If it's a clone, it points to the original player."
    )
    is_public = models.BooleanField(default=False)
    is_temporary = models.BooleanField(default=False)
    is_guest = models.BooleanField(default=False,
                                   help_text="Is this a player imported only for the tournament (not visible in the library)?")

    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    nickname = models.CharField(max_length=30, blank=True, null=True)
    photo = models.ImageField(upload_to='players_photos/', blank=True, null=True)

    # --- 2. MATCH STATISTICS (Career) ---
    matches_played = models.IntegerField(default=0)
    matches_won = models.IntegerField(default=0)
    matches_drawn = models.IntegerField(default=0)
    matches_lost = models.IntegerField(default=0)

    # --- 3. FRAME STATISTICS (Career) ---
    frames_played = models.IntegerField(default=0)
    frames_won = models.IntegerField(default=0)
    frames_lost = models.IntegerField(default=0)
    fastest_frame_time = models.DurationField(blank=True, null=True, help_text="Shortest played frame")
    longest_frame_time = models.DurationField(blank=True, null=True, help_text="Longest played frame")
    avg_frame_time = models.DurationField(blank=True, null=True, help_text="Average frame duration")

    # --- 4. POINTS AND TECHNIQUE ---
    total_career_points = models.BigIntegerField(default=0, help_text="Sum of all points scored")
    global_pot_success = models.FloatField(default=0.0, help_text="Average career pot success (%)")
    global_safety_success = models.FloatField(default=0.0, help_text="Average career safety success (%)")
    avg_shot_time = models.DurationField(blank=True, null=True, help_text="Average shot time")

    # --- 5. BREAKS (Prestige) ---
    highest_break = models.IntegerField(default=0)
    centuries_count = models.IntegerField(default=0, help_text="Number of century breaks (100+)")
    fifties_count = models.IntegerField(default=0, help_text="Number of 50+ breaks")
    max_breaks_count = models.IntegerField(default=0, help_text="Number of maximum breaks (147, 155, 167)")

    # Career break histogram (e.g. {"10-19": 150, "20-29": 40...})
    career_break_stats = models.JSONField(default=dict, blank=True)

    # --- 6. SPECIAL ACHIEVEMENTS (New) ---
    deciders_played = models.IntegerField(default=0, help_text="Number of deciders played")
    deciders_won = models.IntegerField(default=0, help_text="Number of deciders won")
    whitewashes_count = models.IntegerField(default=0, help_text="Number of whitewash wins")

    # --- 7. STREAKS ---
    consecutive_matches_won = models.IntegerField(default=0, help_text="Record streak of consecutive match wins")
    current_match_streak = models.IntegerField(default=0, help_text="Current match win streak (working)")

    consecutive_frames_won = models.IntegerField(default=0, help_text="Record streak of consecutive frame wins")
    current_frame_streak = models.IntegerField(default=0, help_text="Current frame win streak (working)")

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
        """Helper function to format time as MM:SS"""
        if duration:
            total_seconds = int(duration.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            # If game lasted over an hour, add hours (optional)
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

    # Contact
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    # Technical details
    tables_count = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(0)],
        help_text="Number of tables"
    )
    table_info = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="E.g. Star Tables, Strachan Cloth"
    )
    price_per_hour = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True,
        help_text="Price per hour ($)"
    )

    capacity = models.PositiveIntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name


class Referee(models.Model):
    # --- NEW OWNERSHIP FIELDS ---
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
    """Represents a specific group (e.g. Group 1) within a group stage"""
    stage = models.ForeignKey('GroupStage', on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=10, help_text="Group number, e.g. '1', '2'")

    # Completion status of specific group
    is_finished = models.BooleanField(default=False)

    def __str__(self):
        return f"Group {self.name} - {self.stage.competition.name}"

    class Meta:
        ordering = ['name']


class GroupStanding(models.Model):
    """
    Results table for a specific player in a group.
    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='standings')
    player = models.ForeignKey('Player', on_delete=models.CASCADE)

    # 1. MATCHES
    matches_played = models.IntegerField(default=0)
    matches_won = models.IntegerField(default=0)
    matches_drawn = models.IntegerField(default=0)
    matches_lost = models.IntegerField(default=0)

    # 2. FRAMES (Key for table)
    frames_won = models.IntegerField(default=0)
    frames_lost = models.IntegerField(default=0)

    # 3. SMALL POINTS (Sum of points scored in matches)
    small_points_scored = models.IntegerField(default=0, help_text="Total of all points scored")
    small_points_conceded = models.IntegerField(default=0, help_text="Total of all points lost")

    # 4. EXTRAS
    highest_break = models.IntegerField(default=0, help_text="The highest break in this group")

    # Qualification status (for table coloring)
    is_qualified = models.BooleanField(default=False, help_text="Has the player advanced further?")
    final_rank = models.PositiveIntegerField(null=True, blank=True, help_text="Place taken (after group end)")

    # 5. MAIN SCORING
    points = models.IntegerField(default=0, help_text="Points in the table")

    class Meta:
        # Sort: Points > Frame Difference > Frames Won > Small Points Difference
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
    # --- 1. BASIC CONFIGURATION ---
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
    round_number = models.PositiveIntegerField(default=1, help_text="Round number (Group) or Round (Cup/Knockout)")

    number_of_frames = models.PositiveIntegerField()
    allow_draws = models.BooleanField(default=False)

    # --- 2. PLAYERS AND REFEREES ---
    player1 = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='matches_as_p1')
    player2 = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='matches_as_p2')
    referees = models.ManyToManyField('Referee', blank=True, related_name='matches')

    # Name cache (text)
    player_names = models.TextField(blank=True, null=True)
    referee_names = models.TextField(blank=True, null=True)
    player_ids = models.TextField(blank=True, null=True)
    referee_ids = models.TextField(blank=True, null=True)

    # --- 3. TOURNAMENT STRUCTURE ---
    group_stage = models.ForeignKey('GroupStage', on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='matches')
    knockout_stage = models.ForeignKey('KnockoutStage', on_delete=models.CASCADE, null=True, blank=True,
                                       related_name='matches')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True, related_name='matches')
    group_name = models.CharField(max_length=10, blank=True, null=True)
    knockout_name = models.CharField(max_length=100, blank=True, null=True)

    # --- 4. FINAL RESULTS (Summary) ---
    winner = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_matches')

    final_score_player1 = models.IntegerField(default=0, help_text="Frames won P1")
    final_score_player2 = models.IntegerField(default=0, help_text="Frames won P2")

    # --- 5. TIME STATISTICS ---
    total_duration = models.DurationField(blank=True, null=True, help_text="Total net game time")
    avg_frame_time = models.DurationField(blank=True, null=True)
    min_frame_time = models.DurationField(blank=True, null=True)
    max_frame_time = models.DurationField(blank=True, null=True)

    # --- 7. BREAKS AND STREAKS ---

    highest_break_frame_p1 = models.ForeignKey('Frame', on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name='hb_match_p1')
    highest_break_frame_p2 = models.ForeignKey('Frame', on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name='hb_match_p2')

    # JSON Histogram: {"10-19": 5, "20-29": 2, ...}
    break_stats_p1 = models.JSONField(default=dict, blank=True)
    break_stats_p2 = models.JSONField(default=dict, blank=True)

    longest_pot_streak_p1 = models.IntegerField(default=0)
    longest_pot_streak_p2 = models.IntegerField(default=0)

    # --- 8. TEMPORARY DATA ---
    temp_player1 = models.ForeignKey('Player', null=True, blank=True, related_name='temp_player1_matches',
                                     on_delete=models.CASCADE)
    temp_player2 = models.ForeignKey('Player', null=True, blank=True, related_name='temp_player2_matches',
                                     on_delete=models.CASCADE)
    is_temporary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_ordered_players(self):
        """
        Returns list of players always in order: [Host, Guest].
        Now this is fixed, derived from the model.
        """
        # Return list [p1, p2], filtering None (in case someone is missing)
        return [p for p in [self.player1, self.player2] if p]

    @property
    def sort_key(self):
        """
        Returns key for sorting match list.
        Order: Date -> Time -> ID (creation order)
        """
        # Format so text sorting works chronologically
        # E.g. "2023-10-20 14:00:00 125"
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
        # Check if we have both players in seats
        if not self.player1 or not self.player2:
            return {'is_finished': False, 'winner': None}

        p1 = self.player1
        p2 = self.player2

        # COUNT WINS
        p1_wins = Frame.objects.filter(match_player__match=self, winner=p1).count()
        p2_wins = Frame.objects.filter(match_player__match=self, winner=p2).count()

        total_played = p1_wins + p2_wins
        is_finished = False
        winner = None

        # --- SCENARIO A: DRAWS ALLOWED ---
        if self.allow_draws:
            if total_played >= self.number_of_frames:
                is_finished = True
                if p1_wins > p2_wins:
                    winner = p1
                elif p2_wins > p1_wins:
                    winner = p2
                else:
                    winner = None  # DRAW

        # --- SCENARIO B: STANDARD ---
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
        """Returns tuple (score_p1, score_p2) calculated from frames"""
        if not self.player1 or not self.player2:
            return 0, 0

        # Count won frames by checking 'winner' field in Frame
        p1_score = Frame.objects.filter(match_player__match=self, winner=self.player1).count()
        p2_score = Frame.objects.filter(match_player__match=self, winner=self.player2).count()

        return p1_score, p2_score

    def update_status_from_frames(self):
        """Updates match status and winner based on played frames"""
        status_data = self.get_game_status()  # This method already calculates who won

        # Update fields in database
        self.winner = status_data['winner']

        if status_data['is_finished']:
            self.status = 'FINISHED'
        else:
            self.status = 'IN_PROGRESS'

        # Optional: Save score to final_score fields
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

        # Validation: Player cannot play against themselves
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

        # 1. Update name cache
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

        # 2. Save Match (to get ID)
        super().save(*args, **kwargs)

        # 3. Referee Cache (We already had this)
        if not is_new:
            self.referee_names = ', '.join([str(referee) for referee in self.referees.all()])
            self.referee_ids = ', '.join([str(referee.id) for referee in self.referees.all()])
            super().save(update_fields=['referee_names', 'referee_ids', 'player_names', 'player_ids'])

        # --- BRIDGE TO OLD SYSTEM (MatchPlayer Sync) - FIX 2 ---
        from .models import MatchPlayer
        from django.db import transaction

        with transaction.atomic():
            # 1. List of current IDs
            current_player_ids = []
            if self.player1: current_player_ids.append(self.player1.id)
            if self.player2: current_player_ids.append(self.player2.id)

            # 2. DELETE: Remove entries of players who are no longer present
            MatchPlayer.objects.filter(match=self).exclude(player_id__in=current_player_ids).delete()

            # 3. MAKE SPACE (Fix for SWAP):
            # Instead of negative numbers (which DB dislikes), we use large positive numbers.
            # Shift 1 -> 101, 2 -> 102.
            for mp in MatchPlayer.objects.filter(match=self):
                # Change only if they are "normal" positions (below 100)
                if mp.position < 50:
                    mp.position = 100 + mp.position
                    mp.save()

            # 4. SETTING: Assign correct positions
            # System will find player at position 101 and change to 1.
            # System will find player at position 102 and change to 2.

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


    # --- VIRTUAL MATCH STATISTICS (Fixed: fetching via MatchPlayer) ---

    # 1. TOTAL POINTS
    @property
    def total_points_player1(self):
        # We use global Frame object (as in your get_game_status)
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('points_scored_player1'))[
            'total'] or 0

    @property
    def total_points_player2(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('points_scored_player2'))[
            'total'] or 0

    # 2. HIGHEST BREAK IN MATCH
    @property
    def highest_break_p1(self):
        return Frame.objects.filter(match_player__match=self).aggregate(top=models.Max('max_break_player1'))[
            'top'] or 0

    @property
    def highest_break_p2(self):
        return Frame.objects.filter(match_player__match=self).aggregate(top=models.Max('max_break_player2'))[
            'top'] or 0

    # 3. TOTAL FOULS
    @property
    def total_fouls_p1(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('player1_fouls'))[
            'total'] or 0

    @property
    def total_fouls_p2(self):
        return Frame.objects.filter(match_player__match=self).aggregate(total=models.Sum('player2_fouls'))[
            'total'] or 0

    # 4. CONCEDED POINTS (FROM FOULS)
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

    # 6. AST (Average Shot Time) - Match average per player
    @property
    def match_ast_p1(self):
        # Get total time and total shots from all frames
        data = Frame.objects.filter(match_player__match=self).aggregate(
            total_time=models.Sum('time_shots_player1'),
            total_shots=models.Sum('total_shots_player1')
        )

        time_sum = data['total_time']
        shots_sum = data['total_shots'] or 0

        # Safeguard against division by zero
        if not time_sum or shots_sum == 0:
            return "-"

        # Calculate average in seconds
        avg_seconds = time_sum.total_seconds() / shots_sum

        # Return format e.g. "24s"
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

    # --- MATCH DURATION ---

    @property
    def match_total_duration(self):
        # Sum times of all frames attached to this match
        total = Frame.objects.filter(match_player__match=self).aggregate(
            t=models.Sum('time_duration')
        )['t']
        return total  # Returns time object (timedelta) or None

    @property
    def formatted_match_duration(self):
        # This method makes a nice string e.g. "2h 15m"
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

    # Points
    points_scored_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    points_scored_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    # Breaks
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

    # Fouls
    player1_fouls = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    player2_fouls = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    foul_points_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    foul_points_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    # Winner
    winner = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_frames')

    # Time
    time_duration = models.DurationField(blank=True, null=True)

    # Pot Success
    # NEW: Number of potted balls (to easily calculate match average)
    potted_balls_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    potted_balls_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    pot_success_percentage_player1 = models.FloatField(default=0.0)
    pot_success_percentage_player2 = models.FloatField(default=0.0)
    total_pot_success_percentage_player1 = models.FloatField(default=0.0)
    total_pot_success_percentage_player2 = models.FloatField(default=0.0)
    ball_counts = models.JSONField(default=dict, blank=True)

    # Safety Shots
    safety_shot_player1 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    safety_shot_player2 = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    successful_safety_shots_player1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    successful_safety_shots_player2 = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    # Shots
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
    # --- 1. OWNERSHIP AND VISIBILITY ---
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='competitions')
    is_public = models.BooleanField(default=False)

    # --- 2. BASIC DATA ---
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    venue = models.ForeignKey('Venue', on_delete=models.SET_NULL, blank=True, null=True)

    # --- NEW: TOURNAMENT STATUS ---
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('ACTIVE', 'Active'),
        ('FINISHED', 'Finished'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SCHEDULED')

    # --- 3. GAME CONFIGURATION ---
    game_variant = models.CharField(
        max_length=20,
        choices=Match.VARIANT_CHOICES,
        default='STANDARD',
        help_text="Default game variant for all matches in the tournament"
    )

    # --- TOURNAMENT RECORDS ---
    highest_break_points = models.IntegerField(default=0, help_text="Highest break in the entire tournament")
    highest_break_player = models.ForeignKey(
        'Player', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='competition_high_breaks',
        help_text="Author of the highest break"
    )

    # --- PARTICIPANTS ---
    players = models.ManyToManyField('Player', related_name='competitions', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def is_active(self):
        # Tournament is active ONLY if status is ACTIVE
        # Dates are auxiliary, status set by organizer decides
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
        # Get result from CompetitionResult where result is WINNER
        res = self.results.filter(result='WINNER').first()
        return res.player if res else None


class Stage(models.Model):
    """Abstract stage model (shared by Groups and Cup/Knockout)"""
    name = models.CharField(max_length=100, help_text="E.g. 'Group Stage' or 'Finals'")
    competition = models.ForeignKey('Competition', related_name='%(class)s_stages', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1, help_text="Tournament stage order (1, 2, 3...)")
    is_finished = models.BooleanField(default=False)

    # --- NEW FIELDS: STAGE RECORD ---
    highest_break_points = models.IntegerField(default=0, help_text="The highest break in this stage")
    highest_break_player = models.ForeignKey(
        'Player', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='%(class)s_high_breaks',  # Django will create unique names for Group and Knockout
        help_text="Author of the highest break in this stage"
    )

    class Meta:
        abstract = True
        ordering = ['order']

    def __str__(self):
        return f"{self.name} ({self.competition.name})"


class GroupStage(Stage):
    # --- GROUP CONFIGURATION ---
    num_groups = models.IntegerField(validators=[MinValueValidator(1)])
    players_per_group = models.IntegerField(validators=[MinValueValidator(2)])
    matches_per_pair = models.IntegerField(default=1, validators=[MinValueValidator(1)])

    # --- NEW FIELD: Automatic qualification ---
    num_qualifiers = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="How many players automatically qualify from the group?"
    )

    # --- SCORING RULES ---
    points_for_win = models.IntegerField(default=3)
    points_for_draw = models.IntegerField(default=1)
    points_for_loss = models.IntegerField(default=0)
    allow_draws = models.BooleanField(default=True)

    def create_groups_and_matches(self, default_frames, selected_players=None):
        """Generates groups and matches in Round Robin system (everyone vs everyone divided into rounds)."""
        from .models import Group, GroupStanding, Match

        if selected_players:
            players = list(selected_players)
        else:
            players = list(self.competition.players.all())

        random.shuffle(players)
        comp_owner = self.competition.owner
        total_players = len(players)

        # Clear old groups
        self.groups.all().delete()

        for i in range(self.num_groups):
            group_name_str = str(i + 1)

            # 1. Create GROUP object
            group = Group.objects.create(
                stage=self,
                name=group_name_str
            )

            # Select players for the group
            start_idx = i * self.players_per_group
            end_idx = start_idx + self.players_per_group
            group_players = players[start_idx:end_idx] if start_idx < total_players else []

            if len(group_players) < 2:
                continue

            # 2. Create TABLE (Standings)
            for player in group_players:
                GroupStanding.objects.create(
                    group=group, player=player, points=0,
                    matches_played=0, matches_won=0, matches_drawn=0, matches_lost=0,
                    frames_won=0, frames_lost=0,
                    small_points_scored=0, small_points_conceded=0, highest_break=0,
                    is_qualified=False
                )

            # 3. GENERATING MATCHES (Round Robin Algorithm)
            # Thanks to this we have nice rounds (Round 1, Round 2...)

            # Copy of player list for rotation
            rotation_players = list(group_players)

            # If odd number of players, add "Ghost" (Bye)
            if len(rotation_players) % 2 != 0:
                rotation_players.append(None)

            num_participants = len(rotation_players)
            num_rounds = num_participants - 1
            half = num_participants // 2

            # Rematch loop (if matches_per_pair > 1)
            for leg in range(self.matches_per_pair):

                # Reset player arrangement for new rematch round
                current_rotation = list(rotation_players)

                for round_idx in range(num_rounds):
                    # Calculate actual round number (considering rematches)
                    # E.g. with 4 players: Rounds 1-3, then rematches 4-6
                    actual_round_number = (leg * num_rounds) + round_idx + 1

                    for j in range(half):
                        p1 = current_rotation[j]
                        p2 = current_rotation[num_participants - 1 - j]

                        # If both exist (neither is a "Ghost"), create match
                        if p1 and p2:
                            # Swap host and guest in rematch rounds (for order)
                            if leg % 2 == 1:
                                host, guest = p2, p1
                            else:
                                host, guest = p1, p2

                            Match.objects.create(
                                owner=comp_owner,
                                is_public=self.competition.is_public,
                                date=self.competition.start_date,  # Date to be edited later
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
                                round_number=actual_round_number  # <--- SAVING ROUND HERE
                            )

                    # Player rotation (Berger Algorithm)
                    # Keep the first one (index 0) in place, shift the rest
                    # [0, 1, 2, 3] -> [0, 3, 1, 2]
                    current_rotation.insert(1, current_rotation.pop())

    def regenerate_schedule(self):
        """
        Regenerates matches for the current group composition (without deleting groups).
        Used after manual editing (Manage Groups).
        """
        from .models import Match

        # 1. Safeguard: If there are finished matches, do not touch!
        if self.matches.filter(status='FINISHED').exists():
            return False, "Cannot regenerate schedule because some matches are already finished."

        # 2. Get settings from existing matches (before deleting them)
        # To know how many frames to play.
        sample_match = self.matches.first()
        frames_count = sample_match.number_of_frames if sample_match else 2  # Default to 2 just in case

        # 3. Delete only matches (SCHEDULED)
        self.matches.all().delete()

        # 4. Generate new pairs for each group (Round Robin Logic)
        comp_owner = self.competition.owner

        for group in self.groups.all():
            # Get players from this group's table
            group_players = [standing.player for standing in group.standings.all()]

            if len(group_players) < 2:
                continue

            # --- Round Robin Algorithm (same as creation) ---
            rotation_players = list(group_players)
            if len(rotation_players) % 2 != 0:
                rotation_players.append(None)  # "Ghost"

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
    # --- BRACKET CONFIGURATION ---
    num_rounds = models.IntegerField(validators=[MinValueValidator(1)],
                                     help_text="Number of rounds (e.g. 3 for quarter-finals: 1/4 -> 1/2 -> Final)")
    frames_per_match = models.IntegerField(validators=[MinValueValidator(1)])

    # Optional: 3rd Place Match?
    has_third_place_match = models.BooleanField(default=False)

    def create_knockout_matches(self, selected_players=None):
        """Creates the bracket."""
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

            # round_num starts at 0. Save in DB as 1, 2, 3...
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
                    round_number=db_round_number  # <--- SAVING ROUND
                )

            current_round_matches = current_round_matches // 2

        # 3rd Place Match
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
                round_number=99  # Special number for 3rd place match
            )

    def _get_round_name(self, matches_count):
        """
        Returns round name based on the number of matches in that round.
        4 matches -> Quarter-Final
        2 matches -> Semi-Final
        1 match  -> Final
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


# --- 4. EQUIPMENT (Equipment History - PRO Version) ---
class Equipment(models.Model):
    # Equipment Types
    TYPE_CHOICES = [
        ('CUE', 'Snooker Cue'),
        ('TIP', 'Cue Tip'),
        ('CHALK', 'Chalk'),
        ('CASE', 'Cue Case'),
        ('OTHER', 'Other'),
    ]

    # Units and Options
    WEIGHT_UNITS = [('OZ', 'oz'), ('G', 'g')]
    LENGTH_UNITS = [('INCH', 'inch'), ('CM', 'cm')]
    JOINT_CHOICES = [('1PC', '1-piece'), ('3/4', '3/4'), ('2PC', '1/2 (Center)'), ('4/4', '4/4')]
    HARDNESS_CHOICES = [
        ('SS', 'Super Soft'), ('S', 'Soft'), ('M', 'Medium'),
        ('H', 'Hard'), ('XH', 'Extra Hard')
    ]
    SHAFT_MATERIALS = [('ASH', 'Ash'), ('MAPLE', 'Maple'), ('CARBON', 'Carbon'), ('OTHER', 'Other')]

    # Relationships
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='equipment')

    # Basic
    item_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='CUE')
    brand = models.CharField(max_length=50, blank=True, null=True, verbose_name="Manufacturer/Brand")
    name = models.CharField(max_length=100, help_text="Model name or custom name")

    # --- SPECIFICATION (Details) ---
    # Cue
    shaft_material = models.CharField(max_length=10, choices=SHAFT_MATERIALS, blank=True, null=True)
    joint_type = models.CharField(max_length=5, choices=JOINT_CHOICES, blank=True, null=True)

    # Weight
    weight_value = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Weight")
    weight_unit = models.CharField(max_length=4, choices=WEIGHT_UNITS, default='OZ', blank=True, null=True)

    # Length
    length_value = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Length")
    length_unit = models.CharField(max_length=4, choices=LENGTH_UNITS, default='INCH', blank=True, null=True)

    # Ferrule
    ferrule_material = models.CharField(max_length=30, blank=True, null=True, help_text="e.g. Brass, Titanium")
    ferrule_size = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=True,
                                       help_text="Diameter in mm")

    # Tip
    tip_hardness = models.CharField(max_length=3, choices=HARDNESS_CHOICES, blank=True, null=True)
    tip_diameter = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=True,
                                       verbose_name="Tip Size (mm)")

    # Logic and History
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
        # If this photo is main, uncheck other main photos for this equipment
        if self.is_main:
            EquipmentPhoto.objects.filter(equipment=self.equipment).update(is_main=False)
        super().save(*args, **kwargs)


# --- 5. TRAINING SESSION (Training Diary) ---
class TrainingSession(models.Model):
    # --- LIST A: TRAINING FORMAT ---
    TYPE_CHOICES = [
        ('SOLO', 'Solo Practice'),  # Casual play
        ('LINEUP', 'Line-up / Drills'),  # Drills / Setups
        ('SPARING', 'Sparing (No Match)'),  # Playing with a buddy without scoring
        ('MATCH', 'Match Play'),  # Competitive match / Tournament
        ('COACHING', 'Coaching Session'),  # With a coach
    ]

    # --- LIST B: MAIN FOCUS ---
    FOCUS_CHOICES = [
        ('GENERAL', 'General / Mixed'),  # General / Warm-up
        ('TECHNIQUE', 'Technique / Cue Action'),  # Technique / Stance
        ('POTTING', 'Potting Success'),  # Potting Success
        ('LONG', 'Long Potting'),  # Long Potting
        ('BREAK', 'Break Building'),  # Break Building
        ('SAFETY', 'Safety / Tactical'),  # Safety / Tactical
        ('ESCAPES', 'Escapes / Snookers'),  # Escapes / Psychology
        ('REST', 'Rest Play'),  # Rest Play
        ('CLEARANCE', 'Clearance Drills'),  # Clearing the table
        ('MATCH_SIM', 'Match Simulation'),  # Match Simulation (Solo)
    ]
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    player = models.ForeignKey('Player', on_delete=models.CASCADE, related_name='sessions')
    venue = models.ForeignKey('Venue', on_delete=models.SET_NULL, null=True, blank=True)

    date = models.DateField(default=timezone.now)
    duration_minutes = models.PositiveIntegerField(help_text="Duration in minutes", default=60)

    # Format and focus selection
    session_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='SOLO')
    main_focus = models.CharField(max_length=15, choices=FOCUS_CHOICES, default='GENERAL')

    # --- OPTIONAL STATISTICS (FUTURE PROOF) ---
    best_break = models.PositiveIntegerField(
        default=0,
        blank=True,
        help_text="Highest break achieved (Optional)"
    )

    # Percentages (0-100) - all optional (blank=True, null=True)
    pot_success = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Potting %"
    )
    safety_success = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Safety %"
    )
    long_pot_success = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Long Potting %"
    )

    # --- OTHER ---
    notes = models.TextField(blank=True, null=True, help_text="Notes, feelings, specific drills used")
    rating = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Self-rating (1-10)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.date} - {self.get_session_type_display()} ({self.get_main_focus_display()})"


# --- 6. COMPETITION RESULT (Tournament Achievements) ---
class CompetitionResult(models.Model):
    RESULT_CHOICES = [
        # --- PODIUM ---
        ('WINNER', 'Winner 🏆'),
        ('RUNNER_UP', 'Runner-up 🥈'),
        ('THIRD_PLACE', '3rd Place 🥉'),
        ('FOURTH_PLACE', '4th Place'),

        # --- DYNAMIC STAGES ---
        ('KNOCKOUT_ROUND', 'Knockout Round (Last X)'),  # E.g. Last 16, Last 128
        ('GROUP_STAGE', 'Group Stage'),  # E.g. Group I, Group II
        ('QUALIFIER', 'Qualifier'),  # Qualifier
    ]

    competition = models.ForeignKey('Competition', on_delete=models.CASCADE, related_name='results')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='competition_results')

    result = models.CharField(max_length=20, choices=RESULT_CHOICES)

    # --- NEW MAGIC FIELD ---
    detail_number = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="For Knockout: enter number (e.g. 32 for Last 32). For Group: stage number (e.g. 2 for Group Stage II)."
    )

    rank = models.PositiveIntegerField(
        default=0,
        help_text="Numeric rank for sorting (1=Winner, 2=Runner-up, 3=3rd Place, 4=4th Place, 5-8=Quarter...)"
    )

    prize_money = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        # A player can have only one final result in a given tournament
        unique_together = ('competition', 'player')
        ordering = ['rank', 'detail_number']  # Sort by rank, then details for ties

    def __str__(self):
        # Smart name display logic
        if self.result == 'KNOCKOUT_ROUND' and self.detail_number:
            status = f"Last {self.detail_number}"
        elif self.result == 'GROUP_STAGE':
            if self.detail_number and self.detail_number > 1:
                # Convert digit to Roman (optional) or just "Stage 2"
                status = f"Group Stage {self.detail_number}"
            else:
                status = "Group Stage"
        else:
            status = self.get_result_display()

        return f"{self.player} - {status} in {self.competition}"


# --- USER PROFILE MODEL (Avatar, Club/Organizer Data) ---

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    email_confirmed = models.BooleanField(default=False)
    new_email_temp = models.EmailField(blank=True, null=True)
    show_tutorial = models.BooleanField(default=False)

    # --- 1. VISUAL ---
    image = models.ImageField(default='default_profile.jpg', upload_to='profile_pics', blank=True, null=True)

    # --- 2. ORGANIZER / CLUB DATA ---
    club_name = models.CharField(max_length=150, blank=True, null=True, help_text="Name of club or organization")
    founded_date = models.DateField(blank=True, null=True, help_text="Date of club foundation")

    # --- 3. LOCATION ---
    address = models.CharField(max_length=255, blank=True, null=True, help_text="Street and number")
    city = models.CharField(max_length=100, blank=True, null=True, help_text="City")

    # --- 4. CONTACT ---
    public_email = models.EmailField(blank=True, null=True, help_text="Public contact email (visible to players)")
    phone_main = models.CharField(max_length=20, blank=True, null=True, help_text="Main contact number")
    phone_secondary = models.CharField(max_length=20, blank=True, null=True, help_text="Alternative number")

    # --- 5. SOCIAL MEDIA & WEB ---
    website = models.URLField(blank=True, null=True, help_text="Official website URL")
    facebook = models.URLField(blank=True, null=True, help_text="Facebook profile URL")
    instagram = models.URLField(blank=True, null=True, help_text="Instagram profile URL")
    twitter = models.URLField(blank=True, null=True, help_text="X (Twitter) profile URL")

    # --- 6. BIO ---
    bio = models.TextField(max_length=500, blank=True, null=True, help_text="A short description about you or the club")

    # ==========================================
    # --- 7. SAAS FOUNDATIONS (FUTURE PROOF) ---
    # ==========================================

    # A. TIER / ACCOUNT TYPE
    TIER_CHOICES = (
        ('FREE', 'Free Tier'),
        ('PRO', 'Pro Organizer'),
        ('CLUB', 'Club Manager'),
    )
    account_tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='FREE',
                                    help_text="Current subscription plan")

    # B. SUBSCRIPTION TIME & HISTORY
    subscription_start = models.DateTimeField(blank=True, null=True, help_text="Start of current billing cycle")
    subscription_end = models.DateTimeField(blank=True, null=True, help_text="End of current billing cycle")

    # JSON for past subscriptions (e.g. [{'plan': 'PRO', 'start': '2025-01-01', 'end': '2026-01-01'}])
    subscription_history = models.JSONField(default=dict, blank=True, null=True)

    # C. QUOTAS / LIMITS (Hard Numbers)
    # Default values are set for 'FREE' users. Pro users will have higher numbers set by logic.
    limit_players = models.IntegerField(default=5, help_text="Max number of players allowed")
    limit_tournaments = models.IntegerField(default=1, help_text="Max active tournaments allowed")
    limit_venues = models.IntegerField(default=1, help_text="Max venues allowed")
    limit_referees = models.IntegerField(default=2, help_text="Max referees allowed")
    limit_storage_mb = models.IntegerField(default=50, help_text="Max storage for photos in MB")

    # D. BILLING & INVOICE DATA
    billing_company_name = models.CharField(max_length=200, blank=True, null=True,
                                            help_text="Company name for invoices")
    tax_id = models.CharField(max_length=50, blank=True, null=True, help_text="NIP / VAT ID")
    billing_address = models.TextField(blank=True, null=True,
                                       help_text="Full billing address if different from club address")

    # JSON for Payment History, Stripe Customer IDs, Payment Methods, Tax Rules etc.
    billing_metadata = models.JSONField(default=dict, blank=True, null=True)

    # E. SETTINGS & EXTRAS
    # JSON for UI preferences (Dark mode, notifications, language etc.)
    preferences = models.JSONField(default=dict, blank=True, null=True)

    # JSON "Backup" field for absolutely anything else in the future
    extra_data = models.JSONField(default=dict, blank=True, null=True)

    # Admin private notes about this user (e.g. "Friend of owner", "Suspicious activity")
    admin_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f'{self.user.username} Profile ({self.account_tier})'


# --- SIGNALS (Unchanged - essential for automation) ---

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, raw=False, **kwargs):
    if raw:
        return

    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    instance.profile.save()


# --- RANKING SYSTEM (Foundation) ---

class Ranking(models.Model):
    """
    Ranking definition (e.g. 'Season 2026', 'Tuesday League', 'All-time Ranking').
    This is a container for player points.
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rankings')
    name = models.CharField(max_length=100, help_text="Ranking name, e.g. 'Season 2025/2026'")
    description = models.TextField(blank=True, null=True)

    # --- LOGO & VISIBILITY ---
    ranking_logo = models.ImageField(upload_to='ranking_logos/', blank=True, null=True,
                                     help_text="Sponsor logo or league crest")

    # Active = whether it is counted, Public = whether guests can see it
    is_active = models.BooleanField(default=True, help_text="Is this ranking currently active/calculated?")
    is_public = models.BooleanField(default=False, help_text="Visible to everyone (including guests)?")

    # --- RANKING TYPES ---
    RANKING_TYPES = (
        ('SEASON', 'Seasonal (Resets yearly)'),
        ('ROLLING', 'Rolling (e.g. 2-year logic)'),
        ('ALL_TIME', 'All-Time / General'),
        ('CUSTOM', 'Custom Period'),
    )
    ranking_type = models.CharField(max_length=20, choices=RANKING_TYPES, default='SEASON',
                                    help_text="Logic used for points calculation")

    # Validity dates (optional, for archiving)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    # Scoring rules: e.g. {"win": 3, "draw": 1, "frame_win": 1}
    points_system = models.JSONField(default=dict, blank=True, help_text="Rules for calculating points")

    # Reward template: e.g. {"winner": 1000, "runner_up": 500}
    prize_money_rules = models.JSONField(default=dict, blank=True, help_text="Default prize structure template")

    # Reserve for other data (e.g. table colors, sponsor links)
    extra_metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_ranking_type_display()})"


class RankingPosition(models.Model):
    """
    Single row in the ranking. Assigns a player to a ranking and stores their stats.
    """
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE, related_name='positions')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='ranking_positions')

    # --- MAIN CRITERIA ---
    points = models.IntegerField(default=0, db_index=True, help_text="Main ranking points")
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0.00,
                                         help_text="Total prize money won")

    # --- POSITION HISTORY & TRENDS ---
    current_rank = models.IntegerField(default=0, help_text="Current rank (calculated during update)")
    previous_rank = models.IntegerField(default=0, help_text="Previous rank (for showing rise/fall)")

    # Trend (-1, 0, 1) and Form ("WWLWD")
    trend_direction = models.IntegerField(default=0, help_text="1=Up, 0=Stable, -1=Down")
    recent_form = models.CharField(max_length=20, blank=True, null=True, help_text="e.g. WWLWD")

    # --- TOURNAMENT STATISTICS ---
    tournaments_played = models.IntegerField(default=0, help_text="Number of tournaments played in this cycle")
    titles_won = models.IntegerField(default=0, help_text="Number of tournaments won")
    finals_reached = models.IntegerField(default=0, help_text="Number of finals reached")

    # --- MATCH STATISTICS ---
    matches_played = models.IntegerField(default=0)
    matches_won = models.IntegerField(default=0)
    matches_lost = models.IntegerField(default=0)
    matches_drawn = models.IntegerField(default=0)

    # --- FRAME STATISTICS (SNOOKER SPECIFIC) ---
    frames_won = models.IntegerField(default=0)
    frames_lost = models.IntegerField(default=0)

    # Physical field in database (instead of @property) for sorting!
    frame_difference = models.IntegerField(default=0, help_text="Frames Won - Frames Lost (for sorting)")

    # --- SMALL POINTS ---
    small_points_scored = models.IntegerField(default=0)
    small_points_conceded = models.IntegerField(default=0)

    # --- BREAKS (SNOOKER SPECIFIC) ---
    highest_break = models.IntegerField(default=0)
    centuries_count = models.IntegerField(default=0, help_text="Number of century breaks (100+)")
    fifties_count = models.IntegerField(default=0, help_text="Number of 50+ breaks")

    # Stock up on statistics
    extra_stats = models.JSONField(default=dict, blank=True, help_text="Extra stats like fouls, avg shot time etc.")

    class Meta:
        unique_together = ('ranking', 'player')
        # Changed sorting: Points -> Frame Difference -> Matches Won
        ordering = ['-points', '-frame_difference', '-matches_won']

    def __str__(self):
        return f"#{self.current_rank} {self.player.last_name} in {self.ranking.name}"

    @property
    def win_percentage(self):
        if self.matches_played == 0:
            return 0
        return round((self.matches_won / self.matches_played) * 100, 1)


class SharingToken(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sharing_tokens')
    code = models.CharField(max_length=6, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional: If code applies to only one specific player
    # If empty -> means sharing the ENTIRE stable
    specific_player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, blank=True)

    def is_valid(self):
        # Code valid for only 90 seconds
        return timezone.now() < self.created_at + timedelta(seconds=90)

    def __str__(self):
        return f"Token {self.code} ({self.owner.username})"


# This decorator says: "Run me when a Match object is deleted"
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.core.exceptions import ObjectDoesNotExist


@receiver(post_delete, sender='snooker_app.Match')
def update_stats_on_delete(sender, instance, **kwargs):
    """
   Automatically updates stats after a match is deleted.
   Additionally: Cleans up orphaned TEMPORARY players if they no longer have any matches.
    """
    from .services import update_career_stats

    # We define a helper function to avoid writing the same thing twice (for P1 and P2)
    def handle_player_cleanup(player):
        # 1. Update stats (i.e. subtract this match from history if player stays)
        update_career_stats(player)

        #2. CLEANING LOGIC
        # We check if the player is TEMPORARY. We don't touch permanent players!
        if player.is_temporary:
            # We check if this player plays in any OTHER matches.
            # Since this particular match (instance) has already been deleted,
            # count() will return the number of matches remaining.
            remaining_matches = player.matches_as_p1.count() + player.matches_as_p2.count()

            if remaining_matches == 0:
                print(f"--- CLEANUP: Usuwanie osieroconego gracza tymczasowego: {player} ---")
                player.delete()
            else:
                print(
                    f"--- INFO: Gracz tymczasowy {player} zostaje (gra jeszcze w {remaining_matches} innych meczach) ---")

    # --- PLAYER SERVICE 1 ---
    try:
        if instance.player1:
            handle_player_cleanup(instance.player1)
    except ObjectDoesNotExist:
        # This error will occur if it was the deletion of Player 1 that caused the match to be deleted.
        # Then Player 1 no longer exists, so we don't need to clean it up.
        pass

    # --- PLAYER SERVICE 2 ---
    try:
        if instance.player2:
            handle_player_cleanup(instance.player2)
    except ObjectDoesNotExist:
        pass