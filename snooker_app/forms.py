from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname']

        def clean(self):
            cleaned_data = super().clean()
            first_name = cleaned_data.get('first_name')
            last_name = cleaned_data.get('last_name')
            nickname = cleaned_data.get('nickname')

            if not (first_name or last_name or nickname):
                pass

            return cleaned_data


class PlayerEditForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname']

    def clean(self):
        cleaned_data = super().clean()

        return cleaned_data


class RefereeForm(forms.ModelForm):
    class Meta:
        model = Referee
        fields = ['first_name', 'last_name', 'license_number']


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = ['name', 'address', 'capacity']


# =======================================================
# =======================================================
# =======================================================
# =======================================================


class MatchForm(forms.ModelForm):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    referees = forms.ModelMultipleChoiceField(
        queryset=Referee.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = Match
        fields = ['date', 'time', 'venue', 'number_of_frames', 'players', 'referees']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'venue': forms.Select(attrs={'class': 'form-control'}),
            'number_of_frames': forms.NumberInput(attrs={'min': 1}),
        }

    def clean_date(self):
        date = self.cleaned_data['date']
        if date < timezone.now().date():
            raise ValidationError("The date cannot be in the past.")
        return date

    def clean_players(self):
        players = self.cleaned_data.get('players')
        if players.count() < 2:
            raise ValidationError("A match must have at least two players.")
        return players


class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        fields = ['name', 'start_date', 'end_date', 'venue', 'competition_type', 'is_group_stage', 'is_knockout', 'matches']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'venue': forms.Select(attrs={'class': 'form-control'}),
            'competition_type': forms.Select(attrs={'class': 'form-control'}),
            'matches': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['matches'].queryset = Match.objects.all()
        self.fields['matches'].required = False

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if end_date < start_date:
            raise forms.ValidationError('End date cannot be earlier than start date.')

        return cleaned_data


class AddMatchesToCompetitionForm(forms.Form):
    matches = forms.ModelMultipleChoiceField(
        queryset=Match.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)
        if competition:
            self.fields['matches'].queryset = Match.objects.exclude(competitions=competition)


class GroupStageForm(forms.ModelForm):
    default_frames = forms.IntegerField(min_value=1, initial=5)

    class Meta:
        model = GroupStage
        fields = ['num_groups', 'players_per_group', 'matches_per_pair', 'default_frames']

    def clean(self):
        cleaned_data = super().clean()
        num_groups = cleaned_data.get('num_groups')
        players_per_group = cleaned_data.get('players_per_group')

        total_players = num_groups * players_per_group
        if total_players > Player.objects.count():
            raise ValidationError(f"Not enough players. Need {total_players}, but only {Player.objects.count()} available.")

        return cleaned_data


class KnockoutStageForm(forms.ModelForm):
    class Meta:
        model = KnockoutStage
        fields = ['num_rounds', 'frames_per_match']

    def clean_num_rounds(self):
        num_rounds = self.cleaned_data.get('num_rounds')
        if num_rounds < 1:
            raise forms.ValidationError('Number of rounds must be at least 1.')
        return num_rounds


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'password1': forms.PasswordInput(attrs={'class': 'form-control'}),
            'password2': forms.PasswordInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super(SignUpForm, self).save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user
