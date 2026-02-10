from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.forms import BaseModelFormSet

from .models import (Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage, Group, GroupStanding,
                     Equipment, EquipmentPhoto, Profile, TrainingSession)

import math


# --- PEOPLE AND PLACES ---

class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname', 'photo', 'is_public', 'is_temporary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'nickname': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}), # <--- NEW
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_temporary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # Logic for regular user (non-Admin)
        if not self.request or not self.request.user.is_superuser:
            # Remove public field entirely (cleaner than hiding)
            if 'is_public' in self.fields:
                del self.fields['is_public']

            # Hide Is Temporary (default False, user shouldn't click this when adding)
            if 'is_temporary' in self.fields:
                self.fields['is_temporary'].widget = forms.HiddenInput()
                self.fields['is_temporary'].initial = False


# --- PLAYER EDIT FORM ---
class PlayerEditForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname', 'photo', 'is_public', 'is_temporary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'nickname': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}), # <--- NEW
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_temporary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # 1. Is Public Logic
        if not self.request or not self.request.user.is_superuser:
            if 'is_public' in self.fields:
                del self.fields['is_public']

        # 2. PLAYER RESCUE LOGIC
        # If player is ALREADY permanent, do not allow changing to temporary.
        if self.instance.pk and not self.instance.is_temporary:
             if 'is_temporary' in self.fields:
                 self.fields['is_temporary'].widget = forms.HiddenInput()
                 self.fields['is_temporary'].disabled = True
        else:
            # If player IS temporary, encourage change
            self.fields['is_temporary'].label = "Is Temporary (Uncheck to save player permanently)"


class RefereeForm(forms.ModelForm):
    class Meta:
        model = Referee
        fields = ['first_name', 'last_name', 'license_number', 'photo', 'is_public']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'license_number': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # Admin Logic:
        # If not admin -> remove is_public field entirely
        if not self.request or not self.request.user.is_superuser:
            if 'is_public' in self.fields:
                del self.fields['is_public']


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = [
            'name',
            'image',
            'address',
            'phone',
            'email',
            'website',
            'tables_count',
            'table_info',
            'price_per_hour',
            'capacity',
            'is_public'
        ]

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'tables_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'table_info': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Star Tables'}),
            'price_per_hour': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # ADMIN LOGIC:
        # If no request or user is not superuser (admin)...
        if not self.request or not self.request.user.is_superuser:
            # ... then completely remove 'is_public' field from this form.
            # Regular user won't even know it exists.
            if 'is_public' in self.fields:
                del self.fields['is_public']


# --- MATCHES ---

class MatchForm(forms.ModelForm):
    # --- NEW: Two separate slots instead of one collection ---
    player1 = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        required=False,
        label="Player 1 (Host / Left)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    player2 = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        required=False,
        label="Player 2 (Guest / Right)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    # -------------------------------------------------------

    referees = forms.ModelMultipleChoiceField(
        queryset=Referee.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    venue = forms.ModelChoiceField(
        queryset=Venue.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    create_temporary_players = forms.BooleanField(
        label='Create temporary players',
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Match
        fields = [
            'date', 'time', 'venue', 'game_variant', 'number_of_frames',
            'allow_draws', 'player1', 'player2', 'referees', 'is_public', 'table_number'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'time': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control'}),
            'game_variant': forms.Select(attrs={'class': 'form-select'}),
            'number_of_frames': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'table_number': forms.TextInput(attrs={'class': 'form-control'}),
            'allow_draws': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        is_auth = self.request and self.request.user.is_authenticated

        if is_auth:
            user = self.request.user
            # 1. Base: All your players + public ones
            base_players = Player.objects.filter(Q(owner=user) | Q(is_public=True))

            # --- NEW: CONTEXT FILTERING (Tournament) ---
            # If editing existing match (self.instance.pk), check if it is a tournament
            if self.instance.pk:

                # SCENARIO A: Group Match
                if self.instance.group:
                    # Get IDs of players who are in the standings of this specific group
                    allowed_ids = self.instance.group.standings.values_list('player_id', flat=True)
                    # Narrow down the list to only these players
                    base_players = base_players.filter(id__in=allowed_ids)

                # SCENARIO B: Knockout Match
                elif self.instance.knockout_stage:
                    # Get players from the entire tournament
                    competition = self.instance.knockout_stage.competition
                    allowed_ids = competition.players.values_list('id', flat=True)
                    base_players = base_players.filter(id__in=allowed_ids)

            # Assign filtered list to fields
            self.fields['player1'].queryset = base_players
            self.fields['player2'].queryset = base_players
            # ----------------------------------------------------

            self.fields['referees'].queryset = Referee.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))

            if not base_players.exists():
                # Small message change here to fit empty group too
                msg = "No eligible players found."
                self.fields['player1'].help_text = msg
                self.fields['player1'].disabled = True
                self.fields['player2'].disabled = True

            if not self.fields['referees'].queryset.exists():
                self.fields['referees'].help_text = "No referees found."
                self.fields['referees'].disabled = True

            self.fields['is_public'].widget = forms.HiddenInput()
            self.fields['allow_draws'].widget = forms.HiddenInput()
            self.fields['is_public'].initial = False
            self.fields['allow_draws'].initial = False

        else:
            # For non-logged-in users (no changes)
            del self.fields['venue']
            del self.fields['referees']
            del self.fields['player1']
            del self.fields['player2']
            del self.fields['table_number']

            self.fields['create_temporary_players'].initial = True
            self.fields['create_temporary_players'].widget = forms.HiddenInput()
            self.fields['is_public'].initial = True
            self.fields['is_public'].widget = forms.HiddenInput()
            self.fields['allow_draws'].initial = False
            self.fields['allow_draws'].widget = forms.HiddenInput()

    def clean_number_of_frames(self):
        frames = self.cleaned_data.get('number_of_frames')
        if frames is not None:
            if frames % 2 == 0:
                raise ValidationError("The number of frames must be odd (e.g. 1, 3, 5).")
        return frames

    def clean(self):
        cleaned_data = super().clean()

        p1 = cleaned_data.get('player1')
        p2 = cleaned_data.get('player2')
        create_temp = cleaned_data.get('create_temporary_players')
        match_instance = self.instance

        # 1. Basic validation (Required players and different opponents)
        if 'player1' in self.fields:
            if not create_temp:
                if not p1 or not p2:
                    raise ValidationError("Please select both Player 1 and Player 2.")

        if p1 and p2 and p1 == p2:
            raise ValidationError("Player 1 and Player 2 cannot be the same person.")

        # --- TOURNAMENT VALIDATION ---

        # A. KNOCKOUT VALIDATION - "Is player busy in the ENTIRE bracket?"
        # CHANGE: We don't look at the round, only if the player has any unfinished match in this stage.
        if match_instance.knockout_stage and (p1 or p2):
            other_matches = Match.objects.filter(
                knockout_stage=match_instance.knockout_stage
            ).exclude(status='FINISHED').exclude(pk=match_instance.pk)

            if p1 and other_matches.filter(Q(player1=p1) | Q(player2=p1)).exists():
                raise ValidationError(
                    f"Player '{p1}' is already playing in another active match in this Knockout Stage.")

            if p2 and other_matches.filter(Q(player1=p2) | Q(player2=p2)).exists():
                raise ValidationError(
                    f"Player '{p2}' is already playing in another active match in this Knockout Stage.")

        # B. GROUP VALIDATION - "Has this pair played each other already?"
        # No changes here - preventing duplicate pairs in group
        if match_instance.group_stage and p1 and p2:
            group_filter = Q(group_stage=match_instance.group_stage)
            if match_instance.group:
                group_filter &= Q(group=match_instance.group)

            duplicate_exists = Match.objects.filter(group_filter).exclude(pk=match_instance.pk).filter(
                (Q(player1=p1) & Q(player2=p2)) | (Q(player1=p2) & Q(player2=p1))
            ).exists()

            if duplicate_exists:
                raise ValidationError(f"Match between '{p1}' and '{p2}' already exists in this Group.")

        return cleaned_data

    # --- SIMPLIFIED METHOD ---
    def create_temp_players_if_needed(self, match):
        """
        Creates temporary players and assigns them to the new player1/player2 fields.
        The rest (MatchPlayer creation) is now handled by Match.save().
        """
        create_temp = self.cleaned_data.get('create_temporary_players', False)

        if create_temp:
            owner = match.owner  # Can be None for anonymous users

            # 1. Create players
            p1 = Player.objects.create(first_name='Temp Player 1', is_temporary=True, owner=owner)
            p2 = Player.objects.create(first_name='Temp Player 2', is_temporary=True, owner=owner)

            # 2. Assign to new slots
            match.player1 = p1
            match.player2 = p2
            match.temp_player1 = p1
            match.temp_player2 = p2
            match.is_temporary = True

            # 3. Save - this triggers the "bridge" in models.py and creates MatchPlayer!
            match.save()


# --- TOURNAMENTS ---

class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        # Added 'status' to manually change "Scheduled" to "Active"
        fields = ['name', 'start_date', 'end_date', 'venue', 'game_variant', 'is_public', 'status']

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Competition Name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'venue': forms.Select(attrs={'class': 'form-control'}),
            'game_variant': forms.Select(attrs={'class': 'form-select'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.Select(attrs={'class': 'form-select'}), # <-- New widget
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and self.request.user.is_authenticated:
            user = self.request.user
            # Filter venues (mine + public)
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))

        # Hide public option for regular users
        if not self.request or not self.request.user.is_superuser:
            if 'is_public' in self.fields:
                self.fields['is_public'].widget = forms.HiddenInput()
                self.fields['is_public'].initial = False

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date cannot be earlier than start date.")
        return cleaned_data


class AddMatchesToCompetitionForm(forms.Form):
    matches = forms.ModelMultipleChoiceField(
        queryset=Match.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if competition and self.user:
            # Show user matches that are not yet in this tournament (via stages)
            # Note: filtering by 'competitions' might need adjustment because Match
            # doesn't have a direct 'competitions' field, only via GroupStage/KnockoutStage.
            # But if you left related_name='competitions' in the Competition M2M model, it will work.
            # If not, it needs to be changed in the view. Leaving as is for now.
            self.fields['matches'].queryset = Match.objects.filter(owner=self.user)


class GroupStageForm(forms.ModelForm):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Select Players for this Stage"
    )

    # Additional field (not from Stage model, but needed for creating matches)
    default_frames = forms.IntegerField(
        min_value=1,
        initial=3,
        label="Frames per Match",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = GroupStage
        fields = [
            'name', 'num_groups', 'players_per_group',
            'num_qualifiers',
            'matches_per_pair', 'points_for_win', 'points_for_draw', 'allow_draws'
        ]

        # --- WIDGETS FOR MODEL FIELDS (To look nice) ---
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Group Stage'}),
            'num_groups': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'players_per_group': forms.NumberInput(attrs={'class': 'form-control', 'min': '2'}),

            # <--- NEW WIDGET FOR QUALIFIERS ---
            'num_qualifiers': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'e.g. 2'}),

            'matches_per_pair': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'value': '1'}),
            'points_for_win': forms.NumberInput(attrs={'class': 'form-control'}),
            'points_for_draw': forms.NumberInput(attrs={'class': 'form-control'}),
            'allow_draws': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.competition = kwargs.pop('competition', None)
        self.winner_list = kwargs.pop('winners', [])
        self.eliminated_list = kwargs.pop('eliminated', [])
        self.other_list = kwargs.pop('others', [])

        super().__init__(*args, **kwargs)

        if self.competition:
            # CHANGE: Get only players from this tournament (instead of all from DB)
            self.fields['players'].queryset = self.competition.players.all()

            # Default selection (logic unchanged)
            if self.winner_list:
                self.fields['players'].initial = [p.id for p in self.winner_list]
            else:
                # If this is the first stage, select all available
                self.fields['players'].initial = [p.id for p in self.other_list]


class KnockoutStageForm(forms.ModelForm):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Select Players for this Stage"
    )

    class Meta:
        model = KnockoutStage
        fields = ['name', 'num_rounds', 'frames_per_match', 'has_third_place_match']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Finals'}),
            'num_rounds': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'frames_per_match': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'has_third_place_match': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.competition = kwargs.pop('competition', None)
        self.winner_list = kwargs.pop('winners', [])
        self.eliminated_list = kwargs.pop('eliminated', [])
        self.other_list = kwargs.pop('others', [])

        super().__init__(*args, **kwargs)

        # CHANGE 1: Set rounds field as optional and add placeholder
        self.fields['num_rounds'].required = False
        self.fields['num_rounds'].widget.attrs['placeholder'] = 'Auto (Full bracket)'

        if self.competition:
            self.fields['players'].queryset = self.competition.players.all()

            if self.winner_list:
                self.fields['players'].initial = [p.id for p in self.winner_list]
            else:
                self.fields['players'].initial = [p.id for p in self.other_list]

    def clean(self):
        cleaned_data = super().clean()
        players = cleaned_data.get('players')
        num_rounds = cleaned_data.get('num_rounds')

        if not players:
            raise forms.ValidationError("You must select players.")

        count = len(players)

        # 1. BASIC CONDITION: Must be an even number to start
        if count % 2 != 0:
            raise forms.ValidationError(f"Selected {count} players. You need an even number of players to start.")

        # CHANGE 2: AUTO CALCULATION (if field is empty)
        if not num_rounds:
            # Check if number is a power of 2 (e.g. 4, 8, 16, 32...)
            # Bitwise formula: (n & (n-1) == 0) works for powers of 2
            if (count & (count - 1) != 0) or count == 0:
                raise forms.ValidationError(
                    f"Auto-calculation works only for full brackets (Power of 2: 4, 8, 16...). "
                    f"You have {count} players. Please enter rounds manually."
                )

            # Calculate logarithm (e.g. log2(16) = 4)
            num_rounds = int(math.log2(count))
            # Save the calculated value back so the view receives it
            cleaned_data['num_rounds'] = num_rounds

        # 3. ROUND SIMULATION (Your old logic - checks auto-calculated ones too)
        if num_rounds:
            current_players = count
            for r in range(1, num_rounds + 1):
                # At the start of every round, we must have an even number of players
                if current_players % 2 != 0:
                    raise forms.ValidationError(
                        f"Cannot create {num_rounds} rounds with {count} players. "
                        f"After Round {r - 1}, there would be {current_players} players left, which cannot be paired."
                    )
                # Half remain after the round
                current_players = current_players // 2

        return cleaned_data


class SignUpForm(UserCreationForm):
    # 1. Login (Technical)
    username = forms.CharField(
        label='Username (Login)',
        max_length=150,
        help_text='Required. Letters, digits and @/./+/-/_ only. No spaces.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ac_milan'})
    )

    # 2. Display Name (Optional)
    display_name = forms.CharField(
        label='Display Name / Club Name',
        max_length=150,
        required=False,
        help_text='Optional. If left empty, your login username will be used.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. AC Milan'})
    )

    # 3. Email (Required & Unique check below)
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'})
    )

    class Meta:
        model = User
        fields = ('username', 'display_name', 'email', 'password1', 'password2')
        widgets = {
            'password1': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
            'password2': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
        }

    # --- NEW: VALIDATION TO PREVENT DUPLICATE EMAILS ---
    def clean_email(self):
        # We download the entered email
        email = self.cleaned_data.get('email')

        # We check if such email already exists in the (User) database
        if User.objects.filter(email=email).exists():
            # If so - we throw an error that will block registration
            raise ValidationError("A user with that email already exists.")

        # If not - we return the email and the process continues
        return email

    def save(self, commit=True):
        user = super(SignUpForm, self).save(commit=commit)

        club_name_input = self.cleaned_data.get('display_name')

        if commit:
            if hasattr(user, 'profile'):
                if club_name_input:
                    user.profile.club_name = club_name_input
                else:
                    user.profile.club_name = user.username

                user.profile.save()

        return user


class MassMatchEditForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ['date', 'time', 'table_number', 'player1', 'player2', 'referees']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}),
            'time': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control form-control-sm'}),
            'table_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'style': 'width: 60px;'}),
            'referees': forms.SelectMultiple(attrs={'class': 'form-select form-select-sm', 'size': 1}),
            'player1': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'player2': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('player1')
        p2 = cleaned_data.get('player2')

        # 1. PROTECTION AGAINST EMPTY FIELDS (Gamma vs None)
        # If p1 or p2 is missing -> raise error on specific field
        if not p1:
            self.add_error('player1', "Player 1 is required.")

        if not p2:
            self.add_error('player2', "Player 2 is required.")

        # 2. PROTECTION: Same player against themselves
        if p1 and p2 and p1 == p2:
            self.add_error('player2', "Player cannot play against themselves.")

        return cleaned_data


class ExtraMatchForm(forms.ModelForm):

    class Meta:
        model = Match
        fields = ['date', 'time', 'player1', 'player2', 'table_number', 'game_variant', 'number_of_frames']

        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'table_number': forms.TextInput(attrs={'class': 'form-control'}),
            'game_variant': forms.Select(attrs={'class': 'form-select'}),
            'number_of_frames': forms.NumberInput(attrs={'class': 'form-control'}),

            # We can add widgets for players here to make them look nice
            'player1': forms.Select(attrs={'class': 'form-select'}),
            'player2': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)

        if competition:
            # Filter player list only to participants of this tournament
            self.fields['player1'].queryset = competition.players.all()
            self.fields['player2'].queryset = competition.players.all()

            # Nice labels
            self.fields['player1'].label = "Player 1 (Left)"
            self.fields['player2'].label = "Player 2 (Right)"

            self.fields['game_variant'].initial = competition.game_variant


class SubstitutePlayerForm(forms.Form):
    player_out = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        label="Player to Replace (OUT)",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Only players who haven't played any finished matches in this stage are listed."
    )

    player_in = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        label="New Player (IN)",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select a player to take over the spot."
    )

    def __init__(self, *args, **kwargs):
        self.stage = kwargs.pop('stage', None)
        self.owner = kwargs.pop('owner', None)
        super().__init__(*args, **kwargs)

        if self.stage and self.owner:

            # === CHANGE: STAGE TYPE RECOGNITION ===

            # Check if it is a GROUP stage (if model has 'groups' field)
            if hasattr(self.stage, 'groups'):
                # --- LOGIC FOR GROUPS (OLD) ---
                finished_matches = Match.objects.filter(
                    group_stage=self.stage,
                    status='FINISHED'
                )
                # Players are pulled from group table (GroupStanding)
                players_in_stage_ids = list(Player.objects.filter(
                    groupstanding__group__stage=self.stage
                ).values_list('id', flat=True))

            else:
                # --- LOGIC FOR PLAY-OFF (NEW) ---
                # Here we look by knockout_stage
                finished_matches = Match.objects.filter(
                    knockout_stage=self.stage,
                    status='FINISHED'
                )
                # Players are pulled directly from Tournament (because in Play-off, everyone remaining plays)
                # Assumption: self.stage.competition.players
                players_in_stage_ids = list(self.stage.competition.players.values_list('id', flat=True))

            # ========================================

            # Rest of code unchanged - works the same for both versions
            busy_ids = set()
            for m in finished_matches:
                if m.player1: busy_ids.add(m.player1.id)
                if m.player2: busy_ids.add(m.player2.id)

            self.fields['player_out'].queryset = Player.objects.filter(
                id__in=players_in_stage_ids
            ).exclude(id__in=busy_ids)

            self.fields['player_in'].queryset = Player.objects.filter(
                owner=self.owner,
                is_temporary=False
            ).exclude(id__in=players_in_stage_ids)


# Form to change group for existing player (table row)
class GroupAssignmentForm(forms.ModelForm):
    # Checkbox field to remove player from stage
    delete_player = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = GroupStanding
        fields = ['group']  # Only group change

    def __init__(self, *args, **kwargs):
        stage = kwargs.pop('stage', None)
        super().__init__(*args, **kwargs)
        if stage:
            # In dropdown show only groups from this stage
            self.fields['group'].queryset = Group.objects.filter(stage=stage)
            self.fields['group'].widget.attrs.update({'class': 'form-select form-select-sm'})


# Form to add a completely new player from outside
class AddPlayerToGroupForm(forms.Form):
    player = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        label="Select Player",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        label="Assign to Group",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        self.stage = kwargs.pop('stage', None)
        self.owner = kwargs.pop('owner', None)
        super().__init__(*args, **kwargs)

        if self.stage and self.owner:
            # Available players = All my players MINUS those already in groups
            players_in_stage = Player.objects.filter(groupstanding__group__stage=self.stage)

            self.fields['player'].queryset = Player.objects.filter(
                owner=self.owner, is_temporary=False
            ).exclude(id__in=players_in_stage.values('id'))

            self.fields['group'].queryset = Group.objects.filter(stage=self.stage)


class KnockoutSwapForm(forms.Form):
    player_1 = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        label="Player A",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    player_2 = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        label="Swap with Player B",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        stage = kwargs.pop('stage', None)
        super().__init__(*args, **kwargs)
        if stage:
            # Get players ONLY from 1st round of this stage
            # (Only in 1st round are "alive" players at start)
            r1_matches = Match.objects.filter(knockout_stage=stage, round_number=1)

            p_ids = set()
            for m in r1_matches:
                if m.player1: p_ids.add(m.player1.id)
                if m.player2: p_ids.add(m.player2.id)

            self.fields['player_1'].queryset = Player.objects.filter(id__in=p_ids).order_by('last_name')
            self.fields['player_2'].queryset = Player.objects.filter(id__in=p_ids).order_by('last_name')

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("player_1")
        p2 = cleaned_data.get("player_2")

        if p1 == p2:
            raise forms.ValidationError("Please select two different players to swap.")

        return cleaned_data


# Code entry form
class ImportCodeForm(forms.Form):
    code = forms.CharField(
        label="Enter 6-digit Code",
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-center letter-spacing-2',
            'placeholder': '######',
            'style': 'letter-spacing: 5px; font-size: 1.5rem;'
        })
    )


# Player selection form (with checkboxes)
class SelectImportedPlayersForm(forms.Form):
    selected_players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Select players to import"
    )

    def __init__(self, *args, **kwargs):
        found_players = kwargs.pop('found_players', None)
        super().__init__(*args, **kwargs)
        if found_players:
            self.fields['selected_players'].queryset = found_players


class MatchFormSetValidating(BaseModelFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        # Dictionary: Key is (Stage ID, Round Number) -> Value is set of player IDs in this round
        usage_map = {}

        for form in self.forms:
            if not form.is_valid() or not form.cleaned_data or self._should_delete_form(form):
                continue

            # Get data entered in the form (NEW STATE)
            match = form.instance
            p1 = form.cleaned_data.get('player1')
            p2 = form.cleaned_data.get('player2')

            # Determine key (Where are we? Which stage, which round?)
            stage_key = None
            context_name = ""

            if match.group_stage:
                # Groups: Key is Stage + Round Number
                stage_key = ('group', match.group_stage.id, match.round_number)
                context_name = f"Group Stage - Round {match.round_number}"
            elif match.knockout_stage:
                # Knockout: Key is Stage + Round Number
                stage_key = ('knockout', match.knockout_stage.id, match.round_number)
                context_name = f"Knockout - Round {match.round_number}"

            # If match belongs to a stage, check player uniqueness
            if stage_key:
                if stage_key not in usage_map:
                    usage_map[stage_key] = set()

                # Check player 1
                if p1:
                    if p1.id in usage_map[stage_key]:
                        raise forms.ValidationError(
                            f"Player '{p1}' appears twice in {context_name}. You cannot assign the same player to multiple matches in one round.")
                    usage_map[stage_key].add(p1.id)

                # Check player 2
                if p2:
                    if p2.id in usage_map[stage_key]:
                        raise forms.ValidationError(
                            f"Player '{p2}' appears twice in {context_name}. You cannot assign the same player to multiple matches in one round.")
                    usage_map[stage_key].add(p2.id)


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        exclude = ['owner', 'player']
        widgets = {
            # --- BASIC ---
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Manufacturer'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Model name'}),

            # --- SPECIFICATION (Classes were missing here!) ---
            'shaft_material': forms.Select(attrs={'class': 'form-select'}),
            'joint_type': forms.Select(attrs={'class': 'form-select'}),

            'weight_value': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.0'}),
            'weight_unit': forms.Select(attrs={'class': 'form-select'}),

            'length_value': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.0'}),
            'length_unit': forms.Select(attrs={'class': 'form-select'}),

            'tip_hardness': forms.Select(attrs={'class': 'form-select'}),
            'tip_diameter': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'mm'}),

            'ferrule_material': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Material'}),
            'ferrule_size': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'mm'}),

            # --- DATES AND NOTES ---
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Additional info...'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')

        if start and end and end < start:
            raise forms.ValidationError("End date cannot be earlier than start date.")
        return cleaned_data

class EquipmentPhotoForm(forms.ModelForm):
    class Meta:
        model = EquipmentPhoto
        fields = ['image', 'is_main']


# --- FORM 1: USER DATA (Username, Email, Names) ---
class UserUpdateForm(forms.ModelForm):
    # We redefine email to ensure it's required and has consistent styling
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )

    # We verify the username format here as well
    username = forms.CharField(
        help_text="Required. Technical login. No spaces allowed.",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
        }

    # --- VALIDATION: PREVENT DUPLICATE EMAILS ---
    def clean_email(self):
        email = self.cleaned_data.get('email')

        # Logic: Check if this email exists in DB, BUT exclude the current user.
        # Otherwise, the user would get an error for their own existing email.
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This email is already in use by another account.")

        return email

    # --- VALIDATION: PREVENT SPACES IN USERNAME ---
    def clean_username(self):
        username = self.cleaned_data.get('username')

        # Strict check for spaces
        if ' ' in username:
            raise ValidationError("Username cannot contain spaces. Use 'Display Name' in profile settings instead.")

        return username


# --- FORM 2: PROFILE DATA (Club Name, Bio, Socials) ---
class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            'image', 'club_name', 'founded_date', 'bio',
            'address', 'city',
            'public_email', 'phone_main', 'phone_secondary',
            'website', 'facebook', 'instagram', 'twitter'
        ]
        widgets = {
            # Image input hidden for styling via label
            'image': forms.FileInput(attrs={'class': 'd-none', 'id': 'real-file-input'}),

            # Organization
            'club_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Club Name'}),
            'founded_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Short description...'}),

            # Location
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street and Number'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),

            # Contact
            'public_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contact@club.com'}),
            'phone_main': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+48...'}),
            'phone_secondary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Alternative number'}),

            # Social Media
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'facebook': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://facebook.com/...'}),
            'instagram': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://instagram.com/...'}),
            'twitter': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://x.com/...'}),
        }


class TrainingSessionForm(forms.ModelForm):
    venue = forms.ModelChoiceField(
        queryset=Venue.objects.none(),
        required=False,
        label="Location / Venue",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = TrainingSession
        fields = [
            'player',
            'date', 'duration_minutes', 'venue',
            'session_type', 'main_focus',
            'best_break',
            'pot_success', 'safety_success', 'long_pot_success',
            'rating', 'notes'
        ]

        widgets = {
            'player': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 10, 'step': 5}),
            'venue': forms.Select(attrs={'class': 'form-select'}),

            'session_type': forms.Select(attrs={'class': 'form-select'}),
            'main_focus': forms.Select(attrs={'class': 'form-select'}),

            'best_break': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Highest break (optional)'}),
            'pot_success': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '%', 'min': 0, 'max': 100}),
            'safety_success': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': '%', 'min': 0, 'max': 100}),
            'long_pot_success': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': '%', 'min': 0, 'max': 100}),

            'rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10, 'placeholder': '1-10'}),
            'notes': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe your drills...'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        # Get pre-selected player (if exists)
        preselected_player = kwargs.pop('preselected_player', None)

        super().__init__(*args, **kwargs)

        if self.user:
            self.fields['player'].queryset = Player.objects.filter(owner=self.user)
            self.fields['venue'].queryset = Venue.objects.filter(
                Q(is_public=True) | Q(owner=self.user)
            ).order_by('name')

        # HIDE PLAYER FIELD LOGIC
        if preselected_player:
            # Set field value to this player
            self.fields['player'].initial = preselected_player
            # Change widget to hidden (user doesn't see it, but it's there)
            self.fields['player'].widget = forms.HiddenInput()
            # Optional: remove label so empty text doesn't hang there
            self.fields['player'].label = ""