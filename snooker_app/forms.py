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
            self.fields['players'].queryset = Player.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['referees'].queryset = Referee.objects.filter(Q(owner=user) | Q(is_public=True))
            self.fields['venue'].queryset = Venue.objects.filter(Q(owner=user) | Q(is_public=True))

            if not self.fields['players'].queryset.exists():
                self.fields['players'].help_text = "No players found. Please add players in your profile first."
                self.fields['players'].disabled = True

            if not self.fields['referees'].queryset.exists():
                self.fields['referees'].help_text = "No referees found. You can add them in the Referees section."
                self.fields['referees'].disabled = True

            self.fields['is_public'].widget = forms.HiddenInput()
            self.fields['allow_draws'].widget = forms.HiddenInput()
            self.fields['is_public'].initial = False
            self.fields['allow_draws'].initial = False

        else:
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

        if 'players' in self.fields:
            if not create_temp and (not players or players.count() < 2):
                raise ValidationError("Select at least two players OR check 'Create temporary players'.")
        return cleaned_data

    # --- NOWA METODA (Zamiast def save) ---
    def create_temp_players_if_needed(self, match):
        """
        Tworzy graczy tymczasowych ORAZ obiekty MatchPlayer z przypisaną pozycją.
        """
        create_temp = self.cleaned_data.get('create_temporary_players', False)

        if create_temp:
            owner = match.owner

            # 1. Tworzymy graczy ze stałymi nazwami (zgodnie z życzeniem)
            # Nie dodajemy licznika, żeby na tablicy było ładnie "Temp Player 1"
            # W bazie stworzy się nowy rekord za każdym razem (to OK, tak ustaliliśmy)
            p1 = Player.objects.create(first_name='Temp Player 1', is_temporary=True, owner=owner)
            p2 = Player.objects.create(first_name='Temp Player 2', is_temporary=True, owner=owner)

            # 2. Przypisujemy do relacji ManyToMany (dla bezpieczeństwa i kompatybilności)
            match.players.add(p1, p2)

            # 3. KLUCZOWE: Tworzymy obiekty MatchPlayer z POZYCJĄ!
            # To naprawia "Niewidzialnych graczy" w match_detail oraz "Złą kolejność"

            # Importujemy tutaj, żeby uniknąć cyklicznych importów na górze pliku
            from .models import MatchPlayer

            # Gracz 1 -> Pozycja 1 (Lewa)
            MatchPlayer.objects.create(match=match, player=p1, position=1)

            # Gracz 2 -> Pozycja 2 (Prawa)
            MatchPlayer.objects.create(match=match, player=p2, position=2)

            # 4. Uzupełniamy pola pomocnicze w Match
            match.temp_player1 = p1
            match.temp_player2 = p2
            match.is_temporary = True

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
        widget=forms.NumberInput(attrs={'class': 'form-control'})  # <-- Widget dla pola spoza modelu
    )

    class Meta:
        model = GroupStage
        fields = [
            'name', 'order', 'num_groups', 'players_per_group',
            'matches_per_pair', 'points_for_win', 'points_for_draw', 'allow_draws'
        ]

        # --- WIDGETY DLA PÓL MODELU (Żeby wyglądały ładnie) ---
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Group Stage'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'num_groups': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'players_per_group': forms.NumberInput(attrs={'class': 'form-control', 'min': '2'}),
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
            # --- ZMIANA: ROZSZERZAMY LISTĘ ---
            # Zamiast ograniczać się do self.competition.players.all()...
            # ...pozwalamy wybrać każdego 'normalnego' gracza właściciela turnieju.
            owner = self.competition.owner
            self.fields['players'].queryset = Player.objects.filter(owner=owner, is_temporary=False)

            # Domyślne zaznaczanie (logika bez zmian)
            if self.winner_list:
                self.fields['players'].initial = [p.id for p in self.winner_list]
            else:
                # Jeśli to pierwszy etap, zaznaczy wszystkich dostępnych
                self.fields['players'].initial = [p.id for p in self.other_list]


class KnockoutStageForm(forms.ModelForm):
    # Lista graczy
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Select Players for this Stage"
    )

    class Meta:
        model = KnockoutStage
        # TO JEST KLUCZOWE: Tu muszą być wypisane wszystkie 5 pól
        fields = ['name', 'order', 'num_rounds', 'frames_per_match', 'has_third_place_match']

        # Definicja wyglądu (żeby pola miały ramki i wyglądały ładnie)
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Finals'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
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
            # --- ZMIANA: ROZSZERZAMY LISTĘ ---
            owner = self.competition.owner
            self.fields['players'].queryset = Player.objects.filter(owner=owner, is_temporary=False)

            # Domyślne zaznaczanie
            if self.winner_list:
                self.fields['players'].initial = [p.id for p in self.winner_list]
            else:
                self.fields['players'].initial = [p.id for p in self.other_list]

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


class MassMatchEditForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ['date', 'time', 'table_number', 'referees']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}),
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control form-control-sm'}),
            'table_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'style': 'width: 80px;'}),
            # Sędziów zostawiamy jako SelectMultiple, ale w HTML dodamy mu klasę, żeby nie był gigantyczny
            'referees': forms.SelectMultiple(attrs={'class': 'form-select form-select-sm', 'size': '1'}),
        }


class ExtraMatchForm(forms.ModelForm):
    # Pola wyboru graczy (ograniczone do uczestników turnieju)
    player1 = forms.ModelChoiceField(queryset=Player.objects.none(), label="Player 1")
    player2 = forms.ModelChoiceField(queryset=Player.objects.none(), label="Player 2")

    class Meta:
        model = Match
        fields = ['date', 'time', 'table_number', 'game_variant', 'number_of_frames']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'table_number': forms.TextInput(attrs={'class': 'form-control'}),
            'game_variant': forms.Select(attrs={'class': 'form-select'}),
            'number_of_frames': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)
        if competition:
            self.fields['player1'].queryset = competition.players.all()
            self.fields['player2'].queryset = competition.players.all()
            # Ustaw domyślny wariant z turnieju
            self.fields['game_variant'].initial = competition.game_variant

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('player1')
        p2 = cleaned_data.get('player2')
        if p1 and p2 and p1 == p2:
            raise forms.ValidationError("Player 1 and Player 2 cannot be the same person.")