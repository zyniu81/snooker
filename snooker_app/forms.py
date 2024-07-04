from django import forms
from django.core.exceptions import ValidationError
from .models import Player, Referee, Venue, Match, Competition
from django.utils import timezone


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
        fields = ['name', 'start_date', 'end_date', 'venue', 'competition_type', 'is_group_stage', 'is_knockout']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'venue': forms.Select(attrs={'class': 'form-control'}),
            'competition_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if end_date < start_date:
            raise forms.ValidationError('End date cannot be earlier than start date.')

        return cleaned_data
