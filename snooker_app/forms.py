from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q

from .models import Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage


# --- OSOBY I MIEJSCA ---

class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname', 'is_public', 'is_temporary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'nickname': forms.TextInput(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_temporary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)  # Pobieramy request
        super().__init__(*args, **kwargs)

        # Jeśli użytkownik NIE JEST superuserem (albo nie jest zalogowany)
        if not self.request or not self.request.user.is_superuser:
            # Ukrywamy Is Public
            if 'is_public' in self.fields:
                self.fields['is_public'].widget = forms.HiddenInput()
                self.fields['is_public'].initial = False

            # Ukrywamy Is Temporary
            if 'is_temporary' in self.fields:
                self.fields['is_temporary'].widget = forms.HiddenInput()
                self.fields['is_temporary'].initial = False


class PlayerEditForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname', 'is_public']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'nickname': forms.TextInput(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None) # Pobieramy request
        super().__init__(*args, **kwargs)

        # Logika ukrywania Is Public dla nie-admina
        if not self.request or not self.request.user.is_superuser:
            if 'is_public' in self.fields:
                self.fields['is_public'].widget = forms.HiddenInput()


class RefereeForm(forms.ModelForm):
    class Meta:
        model = Referee
        fields = ['first_name', 'last_name', 'license_number', 'is_public']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'license_number': forms.TextInput(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if not self.request or not self.request.user.is_superuser:
            if 'is_public' in self.fields:
                self.fields['is_public'].widget = forms.HiddenInput()
                self.fields['is_public'].initial = False


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        # Dodałem tables_count
        fields = ['name', 'address', 'capacity', 'tables_count', 'is_public']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'tables_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if not self.request or not self.request.user.is_superuser:
            if 'is_public' in self.fields:
                self.fields['is_public'].widget = forms.HiddenInput()
                self.fields['is_public'].initial = False


# --- MECZE ---

class MatchForm(forms.ModelForm):
    # Dynamiczne pola
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
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
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Match
        fields = [
            'date', 'time', 'venue', 'game_variant', 'number_of_frames',
            'allow_draws', 'players', 'referees', 'is_public', 'table_number'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'game_variant': forms.Select(attrs={'class': 'form-select'}),
            'number_of_frames': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'table_number': forms.TextInput(attrs={'class': 'form-control'}),  # <--- Zmiana na TextInput
            'allow_draws': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        is_auth = self.request and self.request.user.is_authenticated

        if is_auth:
            user = self.request.user
            # Filtrujemy
            self.fields['players'].queryset = Player.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['referees'].queryset = Referee.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))

            # --- NOWOŚĆ: SPRAWDZANIE PUSTYCH LIST ---

            # Sprawdzamy graczy
            if not self.fields['players'].queryset.exists():
                self.fields['players'].help_text = "No players found. Please add players in your profile first."
                self.fields['players'].disabled = True  # Blokujemy pole

            # Sprawdzamy sędziów
            if not self.fields['referees'].queryset.exists():
                self.fields['referees'].help_text = "No referees found. You can add them in the Referees section."
                self.fields['referees'].disabled = True

            # Ukrywamy opcje konfiguracyjne (domyślne wartości)
            self.fields['is_public'].widget = forms.HiddenInput()
            self.fields['allow_draws'].widget = forms.HiddenInput()
            self.fields['is_public'].initial = False
            self.fields['allow_draws'].initial = False

        else:
            # DLA GOŚCIA
            del self.fields['venue']
            del self.fields['referees']
            del self.fields['players']
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
        players = cleaned_data.get('players')
        create_temp = cleaned_data.get('create_temporary_players')

        # Walidacja tylko jeśli pole players istnieje (czyli dla zalogowanego)
        if 'players' in self.fields:
            if not create_temp and (not players or players.count() < 2):
                raise ValidationError("Select at least two players OR check 'Create temporary players'.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        create_temp_players = self.cleaned_data.get('create_temporary_players', False)

        if commit:
            instance.save()
            self.save_m2m()

            if create_temp_players:
                owner = instance.owner
                count_base = Player.objects.filter(owner=owner).count() if owner else 0
                prefix = "Temp Player"

                p1 = Player.objects.create(first_name=f'{prefix} {count_base + 1}', is_temporary=True, owner=owner)
                p2 = Player.objects.create(first_name=f'{prefix} {count_base + 2}', is_temporary=True, owner=owner)
                instance.players.add(p1, p2)
                instance.temp_player1 = p1
                instance.temp_player2 = p2
                instance.is_temporary = True
                instance.save()
        return instance


# --- TURNIEJE ---

class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        # Usunąłem nieistniejące pola (is_group_stage, is_knockout), dodałem game_variant
        fields = ['name', 'start_date', 'end_date', 'venue', 'game_variant', 'is_public']

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Competition Name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'venue': forms.Select(attrs={'class': 'form-control'}),
            'game_variant': forms.Select(attrs={'class': 'form-select'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

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
            # Pokazujemy mecze użytkownika, które nie są jeszcze w tym turnieju (poprzez etapy)
            # Uwaga: filtrowanie po 'competitions' może wymagać dostosowania,
            # bo Match nie ma bezpośredniego pola 'competitions', tylko przez GroupStage/KnockoutStage.
            # Ale jeśli zostawiłeś related_name='competitions' w modelu Competition M2M to zadziała.
            # Jeśli nie, trzeba to zmienić w widoku. Na razie zostawiam jak masz.
            self.fields['matches'].queryset = Match.objects.filter(owner=self.user)


class GroupStageForm(forms.ModelForm):
    # To pole nie jest w modelu, ale jest potrzebne do generowania meczów
    default_frames = forms.IntegerField(min_value=1, initial=3,
                                        widget=forms.NumberInput(attrs={'class': 'form-control'}))

    class Meta:
        model = GroupStage
        # Zaktualizowane pola modelu
        fields = [
            'name', 'order', 'num_groups', 'players_per_group',
            'matches_per_pair', 'points_for_win', 'points_for_draw', 'allow_draws'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Group Stage'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'num_groups': forms.NumberInput(attrs={'class': 'form-control'}),
            'players_per_group': forms.NumberInput(attrs={'class': 'form-control'}),
            'matches_per_pair': forms.NumberInput(attrs={'class': 'form-control'}),
            'points_for_win': forms.NumberInput(attrs={'class': 'form-control'}),
            'points_for_draw': forms.NumberInput(attrs={'class': 'form-control'}),
            'allow_draws': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class KnockoutStageForm(forms.ModelForm):
    class Meta:
        model = KnockoutStage
        # Zaktualizowane pola
        fields = ['name', 'order', 'num_rounds', 'frames_per_match', 'has_third_place_match']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Finals'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'num_rounds': forms.NumberInput(attrs={'class': 'form-control'}),
            'frames_per_match': forms.NumberInput(attrs={'class': 'form-control'}),
            'has_third_place_match': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

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