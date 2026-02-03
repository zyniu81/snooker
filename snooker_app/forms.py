from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.forms import BaseModelFormSet

from .models import (Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage, Group, GroupStanding,
                     Equipment, EquipmentPhoto)

import math


# --- OSOBY I MIEJSCA ---

class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname', 'photo', 'is_public', 'is_temporary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'nickname': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}), # <--- NOWE
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_temporary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # Logika dla zwykłego usera (nie-Admina)
        if not self.request or not self.request.user.is_superuser:
            # Usuwamy pole public całkowicie (czyściej niż ukrywanie)
            if 'is_public' in self.fields:
                del self.fields['is_public']

            # Ukrywamy Is Temporary (domyślnie False, user nie powinien tego klikać przy dodawaniu)
            if 'is_temporary' in self.fields:
                self.fields['is_temporary'].widget = forms.HiddenInput()
                self.fields['is_temporary'].initial = False


# --- FORMULARZ EDYCJI GRACZA ---
class PlayerEditForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['first_name', 'last_name', 'nickname', 'photo', 'is_public', 'is_temporary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'nickname': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}), # <--- NOWE
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_temporary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # 1. Logika Is Public
        if not self.request or not self.request.user.is_superuser:
            if 'is_public' in self.fields:
                del self.fields['is_public']

        # 2. LOGIKA RATOWANIA GRACZA
        # Jeśli gracz JUŻ jest stały, nie pozwalamy go zmienić na tymczasowego.
        if self.instance.pk and not self.instance.is_temporary:
             if 'is_temporary' in self.fields:
                 self.fields['is_temporary'].widget = forms.HiddenInput()
                 self.fields['is_temporary'].disabled = True
        else:
            # Jeśli gracz JEST tymczasowy, zachęcamy do zmiany
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

        # Logika dla Admina:
        # Jeśli nie admin -> usuwamy pole is_public całkowicie
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

        # LOGIKA DLA ADMINA:
        # Jeśli nie ma requesta lub użytkownik nie jest superuserem (adminem)...
        if not self.request or not self.request.user.is_superuser:
            # ... to całkowicie usuwamy pole 'is_public' z tego formularza.
            # Zwykły user nawet nie dowie się, że ono istnieje.
            if 'is_public' in self.fields:
                del self.fields['is_public']


# --- MECZE ---

class MatchForm(forms.ModelForm):
    # --- NOWOŚĆ: Dwa osobne fotele zamiast jednego worka ---
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
            # 1. Baza: Wszyscy Twoi gracze + publiczni
            base_players = Player.objects.filter(Q(owner=user) | Q(is_public=True))

            # --- NOWOŚĆ: FILTROWANIE CONTEXTOWE (Turniejowe) ---
            # Jeśli edytujemy istniejący mecz (self.instance.pk), sprawdzamy czy to turniej
            if self.instance.pk:

                # SCENARIUSZ A: Mecz w Grupie
                if self.instance.group:
                    # Pobieramy ID graczy, którzy są w tabeli (standings) tej konkretnej grupy
                    allowed_ids = self.instance.group.standings.values_list('player_id', flat=True)
                    # Zawężamy listę tylko do tych graczy
                    base_players = base_players.filter(id__in=allowed_ids)

                # SCENARIUSZ B: Mecz Pucharowy (Knockout)
                elif self.instance.knockout_stage:
                    # Pobieramy graczy z całego turnieju
                    competition = self.instance.knockout_stage.competition
                    allowed_ids = competition.players.values_list('id', flat=True)
                    base_players = base_players.filter(id__in=allowed_ids)

            # Przypisujemy przefiltrowaną listę do pól
            self.fields['player1'].queryset = base_players
            self.fields['player2'].queryset = base_players
            # ----------------------------------------------------

            self.fields['referees'].queryset = Referee.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))

            if not base_players.exists():
                # Tutaj mała zmiana komunikatu, żeby pasował też do pustej grupy
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
            # Dla niezalogowanych (bez zmian)
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

        # 1. Walidacja podstawowa (Wymagani gracze i różni przeciwnicy)
        if 'player1' in self.fields:
            if not create_temp:
                if not p1 or not p2:
                    raise ValidationError("Please select both Player 1 and Player 2.")

        if p1 and p2 and p1 == p2:
            raise ValidationError("Player 1 and Player 2 cannot be the same person.")

        # --- WALIDACJA TURNIEJOWA ---

        # A. WALIDACJA DLA PUCHARÓW (Knockout) - "Czy gracz jest zajęty w CAŁEJ drabince?"
        # ZMIANA: Nie patrzymy na rundę, tylko na to, czy gracz ma jakikolwiek niezakończony mecz w tym etapie.
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

        # B. WALIDACJA DLA GRUP (Group) - "Czy ta para już ze sobą grała?"
        # Tutaj bez zmian - pilnujemy duplikatów par w grupie
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

    # --- UPROSZCZONA METODA ---
    def create_temp_players_if_needed(self, match):
        """
        Tworzy graczy tymczasowych i przypisuje do nowych pól player1/player2.
        Resztę (tworzenie MatchPlayer) załatwia teraz model Match.save().
        """
        create_temp = self.cleaned_data.get('create_temporary_players', False)

        if create_temp:
            owner = match.owner  # Może być None dla anonimowych

            # 1. Tworzymy graczy
            p1 = Player.objects.create(first_name='Temp Player 1', is_temporary=True, owner=owner)
            p2 = Player.objects.create(first_name='Temp Player 2', is_temporary=True, owner=owner)

            # 2. Przypisujemy do nowych foteli
            match.player1 = p1
            match.player2 = p2
            match.temp_player1 = p1
            match.temp_player2 = p2
            match.is_temporary = True

            # 3. Zapisujemy - to uruchomi "most" w models.py i stworzy MatchPlayer!
            match.save()


# --- TURNIEJE ---

class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        # Dodany 'status', aby ręcznie zmienić "Scheduled" na "Active"
        fields = ['name', 'start_date', 'end_date', 'venue', 'game_variant', 'is_public', 'status']

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Competition Name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'venue': forms.Select(attrs={'class': 'form-control'}),
            'game_variant': forms.Select(attrs={'class': 'form-select'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.Select(attrs={'class': 'form-select'}), # <-- Nowy widget
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and self.request.user.is_authenticated:
            user = self.request.user
            # Filtrujemy venue (moje + publiczne)
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))

        # Ukrywanie opcji publicznej dla zwykłych userów
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
            # Pokazujemy mecze użytkownika, które nie są jeszcze w tym turnieju (poprzez etapy)
            # Uwaga: filtrowanie po 'competitions' może wymagać dostosowania,
            # bo Match nie ma bezpośredniego pola 'competitions', tylko przez GroupStage/KnockoutStage.
            # Ale jeśli zostawiłeś related_name='competitions' w modelu Competition M2M to zadziała.
            # Jeśli nie, trzeba to zmienić w widoku. Na razie zostawiam jak masz.
            self.fields['matches'].queryset = Match.objects.filter(owner=self.user)


class GroupStageForm(forms.ModelForm):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Select Players for this Stage"
    )

    # Pole dodatkowe (nie z modelu Stage, ale potrzebne do tworzenia meczów)
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

        # --- WIDGETY DLA PÓL MODELU (Żeby wyglądały ładnie) ---
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Group Stage'}),
            'num_groups': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'players_per_group': forms.NumberInput(attrs={'class': 'form-control', 'min': '2'}),

            # <--- NOWY WIDGET DLA AWANSUJĄCYCH ---
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
            # ZMIANA: Pobieramy tylko graczy z tego turnieju (zamiast wszystkich z bazy)
            self.fields['players'].queryset = self.competition.players.all()

            # Domyślne zaznaczanie (logika bez zmian)
            if self.winner_list:
                self.fields['players'].initial = [p.id for p in self.winner_list]
            else:
                # Jeśli to pierwszy etap, zaznaczy wszystkich dostępnych
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

        if self.competition:
            # ZMIANA: Pobieramy tylko graczy z tego turnieju
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

        # 1. PODSTAWOWY WARUNEK: Musi być parzysta liczba na start
        if count % 2 != 0:
            raise forms.ValidationError(f"Selected {count} players. You need an even number of players to start.")

        # 2. SYMULACJA RUND
        if num_rounds:
            current_players = count
            for r in range(1, num_rounds + 1):
                # Na początku każdej rundy musimy mieć parzystą liczbę graczy
                if current_players % 2 != 0:
                    raise forms.ValidationError(
                        f"Cannot create {num_rounds} rounds with {count} players. "
                        f"After Round {r - 1}, there would be {current_players} players left, which cannot be paired."
                    )
                # Po rundzie zostaje połowa
                current_players = current_players // 2

        return cleaned_data


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

        # 1. ZABEZPIECZENIE PRZED PUSTYM POLEM (Gamma vs None)
        # Jeśli brakuje p1 lub p2 -> zgłoś błąd przy konkretnym polu
        if not p1:
            self.add_error('player1', "Player 1 is required.")

        if not p2:
            self.add_error('player2', "Player 2 is required.")

        # 2. ZABEZPIECZENIE: Ten sam gracz przeciwko sobie
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

            # Możemy dodać widgety dla graczy tutaj, żeby były ładne
            'player1': forms.Select(attrs={'class': 'form-select'}),
            'player2': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)

        if competition:
            # Filtrujemy listę graczy tylko do uczestników tego turnieju
            self.fields['player1'].queryset = competition.players.all()
            self.fields['player2'].queryset = competition.players.all()

            # Ładne etykiety
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

            # === ZMIANA: ROZPOZNAWANIE TYPU ETAPU ===

            # Sprawdzamy, czy to etap GRUPOWY (czy model ma pole 'groups')
            if hasattr(self.stage, 'groups'):
                # --- LOGIKA DLA GRUP (STARA) ---
                finished_matches = Match.objects.filter(
                    group_stage=self.stage,
                    status='FINISHED'
                )
                # Gracze są wyciągani z tabeli grupowej (GroupStanding)
                players_in_stage_ids = list(Player.objects.filter(
                    groupstanding__group__stage=self.stage
                ).values_list('id', flat=True))

            else:
                # --- LOGIKA DLA PLAY-OFF (NOWA) ---
                # Tutaj szukamy po knockout_stage
                finished_matches = Match.objects.filter(
                    knockout_stage=self.stage,
                    status='FINISHED'
                )
                # Gracze są wyciągani bezpośrednio z Turnieju (bo w Play-off grają wszyscy, którzy zostali)
                # Zakładamy: self.stage.competition.players
                players_in_stage_ids = list(self.stage.competition.players.values_list('id', flat=True))

            # ========================================

            # Reszta kodu bez zmian - działa tak samo dla obu wersji
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


# Formularz do zmiany grupy dla istniejącego gracza (wiersz tabeli)
class GroupAssignmentForm(forms.ModelForm):
    # Pole Checkbox do usunięcia gracza z etapu
    delete_player = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = GroupStanding
        fields = ['group']  # Tylko zmiana grupy

    def __init__(self, *args, **kwargs):
        stage = kwargs.pop('stage', None)
        super().__init__(*args, **kwargs)
        if stage:
            # W dropdownie pokazujemy tylko grupy z tego etapu
            self.fields['group'].queryset = Group.objects.filter(stage=stage)
            self.fields['group'].widget.attrs.update({'class': 'form-select form-select-sm'})


# Formularz do dodania zupełnie nowego gracza z zewnątrz
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
            # Gracze dostępni = Wszyscy moi gracze MINUS ci co już są w grupach
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
            # Pobieramy graczy TYLKO z 1. rundy tego etapu
            # (Tylko w 1. rundzie są "żywi" gracze na starcie)
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


# Formularz wpisywania kodu
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

# Formularz wyboru graczy (z checkboxami)
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

        # Słownik: Klucz to (ID etapu, Numer Rundy) -> Wartość to zbiór ID graczy w tej rundzie
        usage_map = {}

        for form in self.forms:
            if not form.is_valid() or not form.cleaned_data or self._should_delete_form(form):
                continue

            # Pobieramy dane, które Ty wpisałeś w formularzu (NOWY STAN)
            match = form.instance
            p1 = form.cleaned_data.get('player1')
            p2 = form.cleaned_data.get('player2')

            # Określamy klucz (Gdzie jesteśmy? Jaki etap, jaka runda?)
            stage_key = None
            context_name = ""

            if match.group_stage:
                # Grupy: Kluczem jest Etap + Numer Kolejki
                stage_key = ('group', match.group_stage.id, match.round_number)
                context_name = f"Group Stage - Round {match.round_number}"
            elif match.knockout_stage:
                # Puchar: Kluczem jest Etap + Numer Rundy
                stage_key = ('knockout', match.knockout_stage.id, match.round_number)
                context_name = f"Knockout - Round {match.round_number}"

            # Jeśli mecz należy do jakiegoś etapu, sprawdzamy unikalność graczy
            if stage_key:
                if stage_key not in usage_map:
                    usage_map[stage_key] = set()

                # Sprawdzamy gracza 1
                if p1:
                    if p1.id in usage_map[stage_key]:
                        raise forms.ValidationError(
                            f"Player '{p1}' appears twice in {context_name}. You cannot assign the same player to multiple matches in one round.")
                    usage_map[stage_key].add(p1.id)

                # Sprawdzamy gracza 2
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
            # --- PODSTAWOWE ---
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Manufacturer'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Model name'}),

            # --- SPECYFIKACJA (Tu brakowało klas!) ---
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

            # --- DATY I NOTATKI ---
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