from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q  # <--- Potrzebne do filtrowania (Moje LUB Publiczne)

from .models import Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname']
        # Usunęliśmy 'owner' i 'is_public', ustawimy je w widoku

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        nickname = cleaned_data.get('nickname')

        # Logika walidacji (opcjonalna, pusta w Twoim kodzie, ale zostawiam)
        if not (first_name or last_name or nickname):
            pass
        return cleaned_data


class PlayerEditForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname']


class RefereeForm(forms.ModelForm):
    class Meta:
        model = Referee
        fields = ['first_name', 'last_name', 'license_number']


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = ['name', 'address', 'capacity']


class MatchForm(forms.ModelForm):
    # Pola definiujemy tutaj, żeby móc dynamicznie zmieniać QuerySet w __init__
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),  # Domyślnie puste, wypełnimy w __init__
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

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
    )

    class Meta:
        model = Match
        fields = ['date', 'time', 'venue', 'number_of_frames', 'players', 'referees']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'number_of_frames': forms.NumberInput(attrs={'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # FILTROWANIE LIST ROZWIJANYCH:
        # Jeśli mamy użytkownika w request, pokazujemy tylko jego obiekty + publiczne
        if self.request and self.request.user.is_authenticated:
            user = self.request.user
            self.fields['players'].queryset = Player.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['referees'].queryset = Referee.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))
        else:
            # Fallback dla testów lub niezalogowanych (choć widok to zablokuje)
            self.fields['players'].queryset = Player.objects.filter(is_public=True)
            self.fields['referees'].queryset = Referee.objects.filter(is_public=True)
            self.fields['venue'].queryset = Venue.objects.filter(is_public=True)

    def clean_date(self):
        date = self.cleaned_data['date']
        if date < timezone.now().date():
            raise ValidationError("The date cannot be in the past.")
        return date

    def clean(self):
        cleaned_data = super().clean()
        players = cleaned_data.get('players')
        create_temp = cleaned_data.get('create_temporary_players')

        if not create_temp:
            if not players or players.count() < 2:
                raise ValidationError(
                    "You must select at least two players OR check 'Create temporary players'."
                )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        create_temp_players = self.cleaned_data.get('create_temporary_players', False)

        if commit:
            instance.save()
            self.save_m2m()

            if create_temp_players:
                owner = instance.owner  # Może być None

                # Zliczanie graczy dla nazwy
                count_base = 0
                if owner:
                    count_base = Player.objects.filter(owner=owner).count()

                prefix = "Temporary Player"

                # Tworzymy z owner=None (jeśli instance.owner jest None)
                temp_player1 = Player.objects.create(
                    first_name=f'{prefix} {count_base + 1}',
                    is_temporary=True,
                    owner=owner
                )
                temp_player2 = Player.objects.create(
                    first_name=f'{prefix} {count_base + 2}',
                    is_temporary=True,
                    owner=owner
                )
                instance.players.add(temp_player1, temp_player2)

        return instance


class CompetitionForm(forms.ModelForm):
    venue = forms.ModelChoiceField(
        queryset=Venue.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    matches = forms.ModelMultipleChoiceField(
        queryset=Match.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Competition
        fields = ['name', 'start_date', 'end_date', 'venue', 'competition_type', 'is_group_stage', 'is_knockout',
                  'matches']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'competition_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)  # Pobieramy request
        super().__init__(*args, **kwargs)

        if self.request and self.request.user.is_authenticated:
            user = self.request.user
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))
            # W zawodach chcemy wybierać raczej tylko SWOJE mecze
            self.fields['matches'].queryset = Match.objects.filter(owner=user)
        else:
            self.fields['venue'].queryset = Venue.objects.none()
            self.fields['matches'].queryset = Match.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError('End date cannot be earlier than start date.')

        return cleaned_data


class AddMatchesToCompetitionForm(forms.Form):
    matches = forms.ModelMultipleChoiceField(
        queryset=Match.objects.none(),  # Puste na start
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        self.user = kwargs.pop('user', None)  # Przekazujemy usera
        super().__init__(*args, **kwargs)

        if competition and self.user:
            # Pokazujemy mecze użytkownika, które nie są jeszcze w tym turnieju
            self.fields['matches'].queryset = Match.objects.filter(owner=self.user).exclude(competitions=competition)


class GroupStageForm(forms.ModelForm):
    default_frames = forms.IntegerField(min_value=1, initial=5)

    class Meta:
        model = GroupStage
        fields = ['num_groups', 'players_per_group', 'matches_per_pair', 'default_frames']

    def clean(self):
        cleaned_data = super().clean()
        # Tutaj walidacja ilości graczy jest trudna w Form, bo nie mamy dostępu do Competition.
        # Przeniesiemy walidację logiczną do views lub zostawimy prostą.
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
