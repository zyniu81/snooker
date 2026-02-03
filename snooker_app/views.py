from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView
from django.contrib import messages
from django.db.models import Count, Sum, F, Case, When, IntegerField, Q, Max
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.forms import modelformset_factory
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from datetime import timedelta
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.db import transaction, models
from django.utils.crypto import get_random_string
from django.template.loader import render_to_string
from collections import defaultdict
from django.core.management import call_command

from io import StringIO
from openai import OpenAI
import os, json, openpyxl, sys

from .services import update_career_stats, calculate_competition_results

from snooker_app.forms import (PlayerForm, PlayerEditForm, RefereeForm, VenueForm,
                               MatchForm, CompetitionForm, AddMatchesToCompetitionForm,
                               GroupStageForm, SignUpForm, KnockoutStageForm, MassMatchEditForm, ExtraMatchForm,
                               SubstitutePlayerForm, GroupAssignmentForm, AddPlayerToGroupForm, KnockoutSwapForm,
                               ImportCodeForm, SelectImportedPlayersForm, MatchFormSetValidating, EquipmentForm,
                               EquipmentPhotoForm, UserUpdateForm, ProfileUpdateForm)
from snooker_app.models import (Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage,
                                MatchPlayer, Frame, GroupStanding, SharingToken, CompetitionResult, Equipment,
                                EquipmentPhoto)


# --- FUNKCJE POMOCNICZE ---

def check_ownership(request, obj):
    """
    Sprawdza, czy użytkownik jest właścicielem obiektu.
    Jeśli obiekt jest publiczny, tylko Superuser może go edytować.
    """
    if request.user.is_superuser:
        return True
    if obj.owner == request.user:
        return True
    return False


# --------------------------

@login_required
def player_list(request):
    # Logika: (Moi LUB Publiczni) ORAZ (Nie Goście)
    players = Player.objects.filter(
        (Q(owner=request.user) | Q(is_public=True)) & Q(is_guest=False)
    ).order_by('-created_at')  # Warto dodać sortowanie

    return render(request, 'player_list.html', {'players': players})


@login_required
def add_player(request):
    if request.method == 'POST':
        # ZMIANA: Dodano request.FILES
        form = PlayerForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            player = form.save(commit=False)
            player.owner = request.user

            # Admin domyślnie tworzy publicznych (opcjonalnie)
            if request.user.is_superuser:
                player.is_public = True

            player.save()
            return redirect('player_list')
    else:
        form = PlayerForm(request=request)

    return render(request, 'add_player.html', {'form': form})


@login_required
def player_edit(request, pk):
    player = get_object_or_404(Player, pk=pk)

    if not check_ownership(request, player):
        messages.error(request, "You cannot edit this player.")
        return redirect('player_list')

    if request.method == 'POST':
        form = PlayerEditForm(request.POST, request.FILES, instance=player, request=request)

        was_temporary = player.is_temporary

        if form.is_valid():
            saved_player = form.save(commit=False)
            is_now_temporary = saved_player.is_temporary
            saved_player.save()

            # --- Logika konwersji (Tymczasowy -> Stały) ---
            if was_temporary and not is_now_temporary:
                # POPRAWKA 1: Używamy Q dla player1/player2
                matches_qs = Match.objects.filter(
                    (Q(player1=saved_player) | Q(player2=saved_player)) & Q(is_temporary=True)
                )

                # POPRAWKA 2: Szukanie przeciwników po poprawnych relacjach (matches_as_p1 / matches_as_p2)
                opponents_list = list(Player.objects.filter(
                    (Q(matches_as_p1__in=matches_qs) | Q(matches_as_p2__in=matches_qs)) &
                    Q(is_temporary=True)
                ).exclude(id=saved_player.id).distinct())

                matches_count = matches_qs.update(is_temporary=False)

                opponents_info = []
                for opponent in opponents_list:
                    opponent.is_temporary = False
                    opponent.save()
                    edit_url = reverse('player_edit', args=[opponent.pk])
                    link = f"<a href='{edit_url}' class='alert-link'>{opponent.first_name}</a>"
                    opponents_info.append(link)

                msg = f"Player '{saved_player.first_name}' converted to permanent successfully."
                if matches_count > 0:
                    msg += f" <br><strong>{matches_count} matches</strong> were also saved to history."
                if opponents_info:
                    opponents_str = ", ".join(opponents_info)
                    msg += f"<br>Note: The following opponents were also converted: {opponents_str}. Click to rename them."

                messages.success(request, mark_safe(msg))

            else:
                messages.success(request, "Player updated successfully.")

            # --- Aktualizacja nazw w meczach (Cache) ---
            # POPRAWKA 3: Tutaj też używamy Q dla player1/player2
            player_matches = Match.objects.filter(
                Q(player1=saved_player) | Q(player2=saved_player)
            )
            for m in player_matches:
                m.save() # To wywoła metodę save() modelu, która zaktualizuje player_names

            return redirect('player_detail', pk=player.pk)
    else:
        form = PlayerEditForm(instance=player, request=request)

    return render(request, 'player_edit.html', {'form': form, 'player': player})


@login_required
def player_detail(request, pk):
    # Możemy podglądać publiczne lub swoje
    # Tutaj mała uwaga: Jeśli wchodzisz na "Gościa" (is_guest=True),
    # to on technicznie jest Twój (owner=request.user), więc ten warunek zadziała poprawnie.
    player = get_object_or_404(Player, pk=pk)

    if not (player.is_public or player.owner == request.user):
        raise PermissionDenied("You do not have access to this player.")

    # --- POBIERANIE HISTORII MECZÓW (POPRAWIONE) ---
    # Używamy Q, żeby sprawdzić czy gracz jest w player1 LUB w player2
    recent_matches = Match.objects.filter(
        Q(player1=player) | Q(player2=player)
    ).order_by('-date', '-time')[:5]
    # -----------------------------------------------

    # --- POBIERANIE WYNIKÓW TURNIEJOWYCH ---
    comp_results = CompetitionResult.objects.filter(player=player).select_related('competition').order_by(
        '-competition__end_date')

    # Liczniki do "Gabloty"
    trophies = {
        'gold': comp_results.filter(result='WINNER').count(),
        'silver': comp_results.filter(result='RUNNER_UP').count(),
        'bronze': comp_results.filter(result='THIRD_PLACE').count(),
    }
    # -----------------------------------------------

    return render(request, 'player_detail.html', {
        'player': player,
        'matches': recent_matches,
        'competition_results': comp_results,
        'trophies': trophies
    })


class PlayerDeleteView(DeleteView):
    model = Player
    template_name = 'player_delete.html'
    success_url = reverse_lazy('player_list')

    def get_queryset(self):
        # DeleteView używa tego do pobrania obiektu. Filtrujemy tylko do własnych.
        # User nie może usunąć publicznego gracza, nawet jak go widzi.
        return Player.objects.filter(owner=self.request.user)


@login_required
def referee_list(request):
    referees = Referee.objects.filter(Q(owner=request.user) | Q(is_public=True))
    return render(request, 'referee_list.html', {'referees': referees})


@login_required
def add_referee(request):
    if request.method == 'POST':
        # Dodano request.FILES
        form = RefereeForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            referee = form.save(commit=False)
            referee.owner = request.user
            # Opcjonalne: Admin domyślnie tworzy publicznych, ale ma też checkboxa
            if request.user.is_superuser:
                referee.is_public = True
            referee.save()
            return redirect('referee_list')
    else:
        form = RefereeForm(request=request)

    return render(request, 'add_referee.html', {'form': form})


@login_required
def edit_referee(request, pk):
    referee = get_object_or_404(Referee, pk=pk)
    if not check_ownership(request, referee):
        messages.error(request, "Brak uprawnień.")
        return redirect('referee_list')

    if request.method == 'POST':
        # Dodano request.FILES
        form = RefereeForm(request.POST, request.FILES, instance=referee, request=request)
        if form.is_valid():
            form.save()
            return redirect('referee_detail', pk=referee.pk)
    else:
        form = RefereeForm(instance=referee, request=request)

    return render(request, 'edit_referee.html', {'form': form, 'referee': referee})


@login_required
def delete_referee(request, pk):
    referee = get_object_or_404(Referee, pk=pk)
    if not check_ownership(request, referee):
        raise PermissionDenied

    if request.method == 'POST':
        referee.delete()
        return redirect('referee_list')

    return render(request, 'delete_referee.html', {'referee': referee})


@login_required
def referee_detail(request, pk):
    referee = get_object_or_404(Referee, pk=pk)
    if not (referee.is_public or referee.owner == request.user):
        raise PermissionDenied
    return render(request, 'referee_detail.html', {'referee': referee})


@login_required
def venue_list(request):
    venues = Venue.objects.filter(Q(owner=request.user) | Q(is_public=True))
    return render(request, 'venue_list.html', {'venues': venues})


@login_required
def add_venue(request):
    if request.method == 'POST':
        # TU BYŁ BŁĄD: Dodano request.FILES
        form = VenueForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            venue = form.save(commit=False)
            venue.owner = request.user

            # Ta logika jest ok, jeśli wymuszamy publiczność dla admina,
            # choć admin ma teraz checkbox w formularzu.
            if request.user.is_superuser:
                venue.is_public = True

            venue.save()
            return redirect('venue_list')
    else:
        form = VenueForm(request=request)

    return render(request, 'add_venue.html', {'form': form})


@login_required
def edit_venue(request, pk):
    venue = get_object_or_404(Venue, pk=pk)
    if not check_ownership(request, venue):
        messages.error(request, "Brak uprawnień.")
        return redirect('venue_list')

    if request.method == 'POST':
        # TU BYŁ BŁĄD: Dodano request.FILES przed instance
        form = VenueForm(request.POST, request.FILES, instance=venue, request=request)
        if form.is_valid():
            form.save()
            # Sugestia: Po edycji lepiej wrócić do szczegółów niż do listy
            return redirect('venue_detail', pk=venue.pk)
    else:
        form = VenueForm(instance=venue, request=request)

    return render(request, 'edit_venue.html', {'form': form, 'venue': venue})


class VenueDeleteView(DeleteView):
    model = Venue
    template_name = 'delete_venue.html'
    success_url = reverse_lazy('venue_list')

    def get_queryset(self):
        return Venue.objects.filter(owner=self.request.user)


@login_required
def venue_detail(request, pk):
    venue = get_object_or_404(Venue, pk=pk)
    if not (venue.is_public or venue.owner == request.user):
        raise PermissionDenied
    return render(request, 'venue_detail.html', {'venue': venue})


@login_required
def match_list(request):
    # 1. BAZA: Twoje oryginalne zapytanie
    matches = Match.objects.filter(owner=request.user).order_by('-date', '-time')

    # 2. Pobieramy lata do listy rozwijanej (zanim przefiltrujemy listę!)
    # Metoda .dates() zwraca unikalne daty (lata) z QuerySetu
    available_years = matches.dates('date', 'year', order='DESC')

    # 3. FILTR: ROK
    selected_year = request.GET.get('year')
    if selected_year:
        matches = matches.filter(date__year=selected_year)

    # 4. FILTR: STATUS
    selected_status = request.GET.get('status')
    if selected_status:
        matches = matches.filter(status=selected_status)

    return render(request, 'match_list.html', {
        'matches': matches,
        # Przekazujemy dane do formularza filtrów
        'available_years': available_years,
        'selected_year': selected_year,
        'selected_status': selected_status,
    })


@login_required
def add_match(request):
    # 1. Sprawdzamy, czy wracamy z importu z konkretnym gościem
    guest_id = request.GET.get('guest_id')

    # 2. Budujemy QuerySet graczy dostępnych w tym formularzu
    # Logika: (Moi Zwykli Gracze) LUB (Ten Jeden Konkretny Gość, jeśli istnieje)
    # Dzięki temu normalnie nie widzisz gości, ale tego jednego teraz zobaczysz.

    # Bazowi gracze (Twoi, nietymczasowi)
    base_players = Player.objects.filter(owner=request.user, is_guest=False)

    if guest_id:
        # Jeśli jest guest_id, dodajemy go do puli (upewniając się, że należy do Ciebie)
        specific_guest = Player.objects.filter(owner=request.user, pk=guest_id)
        players_queryset = (base_players | specific_guest).distinct().order_by('last_name')
    else:
        players_queryset = base_players.order_by('last_name')

    if request.method == 'POST':
        form = MatchForm(request.POST, request=request)

        # WAŻNE: Musimy nadpisać queryset w polach formularza PRZED walidacją.
        # Inaczej Django powie "Wybrany gracz jest nieprawidłowy", bo gość jest ukryty w domyślnym QuerySecie formularza.
        form.fields['player1'].queryset = players_queryset
        form.fields['player2'].queryset = players_queryset

        if form.is_valid():
            match = form.save(commit=False)
            match.owner = request.user

            # ZAPISUJEMY MECZ
            match.save()

            # Zapisujemy sędziów
            form.save_m2m()

            # Obsługa graczy tymczasowych (stworzonych ręcznie z inputa, a nie z kodu)
            form.create_temp_players_if_needed(match)

            return redirect('match_detail', pk=match.pk)
    else:
        form = MatchForm(request=request)

        # Nadpisujemy queryset, żeby gracz pojawił się na liście rozwijanej
        form.fields['player1'].queryset = players_queryset
        form.fields['player2'].queryset = players_queryset

        # UX: Jeśli mamy gościa, ustawiamy go automatycznie w polu Player 2
        if guest_id:
            form.fields['player2'].initial = guest_id

    return render(request, 'add_match.html', {
        'form': form,
        'guest_id': guest_id  # Przekazujemy do template'u (żeby obsłużyć przycisk Import)
    })


def match_detail(request, pk):
    match = get_object_or_404(Match, pk=pk)

    # --- LOGIKA DOSTĘPU (Bez zmian) ---
    has_access = False
    if match.owner is None:
        has_access = True
    elif match.is_public:
        has_access = True
    elif request.user.is_authenticated and match.owner == request.user:
        has_access = True

    if not has_access:
        if request.user.is_authenticated:
            raise PermissionDenied
        else:
            return redirect(f'{reverse("login")}?next={request.path}')
    # ----------------------------------

    # Status gry (korzysta już z nowej logiki w modelu)
    game_status = match.get_game_status()

    # Pobieramy framy (one są podpięte przez MatchPlayer, ale filtrujemy je po meczu)
    frames = Frame.objects.filter(match_player__match=match).order_by('frame_number')

    # --- NOWA LOGIKA POBIERANIA GRACZY (Prosto z foteli) ---
    # Nie musimy już szukać w MatchPlayer i sortować. Mamy ich pod ręką.

    p1_data = None
    p2_data = None

    # Gracz 1 (Gospodarz / Lewy)
    if match.player1:
        # Liczymy wygrane framy (winner we Frame to ForeignKey do Player, więc to zadziała bezpośrednio)
        p1_wins = frames.filter(winner=match.player1).count()
        p1_data = {
            'name': str(match.player1),
            'obj': match.player1,  # Przekazujemy obiekt Player
            'wins': p1_wins
        }

    # Gracz 2 (Gość / Prawy)
    if match.player2:
        p2_wins = frames.filter(winner=match.player2).count()
        p2_data = {
            'name': str(match.player2),
            'obj': match.player2,  # Przekazujemy obiekt Player
            'wins': p2_wins
        }

    return render(request, 'match_detail.html', {
        'match': match,
        'is_finished': game_status['is_finished'],
        'winner': game_status['winner'],
        'frames': frames,
        'p1': p1_data,
        'p2': p2_data,
    })


@login_required
def edit_match(request, pk):
    match = get_object_or_404(Match, pk=pk)
    if match.owner != request.user:
        messages.error(request, "Możesz edytować tylko swoje mecze.")
        return redirect('match_list')

    if request.method == 'POST':
        form = MatchForm(request.POST, instance=match, request=request)
        if form.is_valid():
            form.save()
            return redirect('match_detail', pk=pk)
    else:
        form = MatchForm(instance=match, request=request)

    return render(request, 'edit_match.html', {'form': form, 'match': match})


class MatchDeleteView(DeleteView):
    model = Match
    template_name = 'delete_match.html'
    success_url = reverse_lazy('match_list')

    def get_queryset(self):
        return Match.objects.filter(owner=self.request.user)

    # --- NOWE ZABEZPIECZENIE ---
    # Zamiast def delete(...), użyj tego:
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # WARUNEK BLOKADY
        if self.object.group_stage or self.object.knockout_stage:
            messages.error(request, "You cannot delete a match that is part of a tournament!")
            # Wracamy na listę, zamiast kasować
            return redirect(self.success_url)

        # Jeśli warunek nie spełniony -> kasujemy
        return self.delete(request, *args, **kwargs)


def start_game(request, pk):
    # Pobieramy mecz
    match = get_object_or_404(Match, pk=pk)

    # --- LOGIKA DOSTĘPU ---
    has_access = False
    if match.owner is None:
        has_access = True
    elif match.is_public:
        has_access = True
    elif request.user.is_authenticated and match.owner == request.user:
        has_access = True

    if not has_access:
        if request.user.is_authenticated:
            raise PermissionDenied("Brak dostępu do meczu.")
        else:
            return redirect(f'{reverse("login")}?next={request.path}')
    # ----------------------

    status = match.get_game_status()
    if status['is_finished']:
        messages.warning(request, "Ten mecz jest już zakończony!")
        return redirect('match_detail', pk=pk)

    # --- CZYSTA LOGIKA (Bez auto-naprawy) ---
    # Pobieramy graczy TYLKO z tabeli MatchPlayer, posortowanych po pozycji.
    # Jeśli tu jest pusto -> trudno. Nie zgadujemy.
    match_players = MatchPlayer.objects.filter(match=match).order_by('position')

    # Tworzymy listę obiektów Player (potrzebna do active_player itp.)
    players_list = [mp.player for mp in match_players]

    # --- LOGIKA FRAMÓW ---
    existing_frames = Frame.objects.filter(match_player__in=match_players)
    active_frame_object = None

    # Tworzymy Frame 1 tylko jeśli mamy graczy (żeby nie wywaliło błędu przy pustej liście)
    if not existing_frames.exists() and match_players.exists():
        active_frame_object = Frame.objects.create(
            match_player=match_players.first(), # To jest bezpieczne, bo mamy .exists()
            frame_number=1,
            points_scored_player1=0,
            points_scored_player2=0,
            active_player=players_list[0] if players_list else None
        )
    else:
        active_frame_object = existing_frames.last()

    # --- WYLICZANIE WYNIKÓW ---
    frame_results = Frame.objects.filter(match_player__match=match).values('winner').annotate(
        frames_won=Count('winner'))
    frames_won = {result['winner']: result['frames_won'] for result in frame_results if result['winner']}

    player_results = []
    for player in players_list:
        player_results.append({
            'player': player,
            'frames_won': frames_won.get(player.id, 0)
        })

    context = {
        'match': match,
        'players': player_results, # Jeśli mecz był zepsuty, to będzie puste. I dobrze.
        'pk': pk,
        'number_of_frames': match.number_of_frames,
        'frame': active_frame_object
    }
    return render(request, 'start_game.html', context)


@login_required
def add_competition(request):
    if request.method == 'POST':
        form = CompetitionForm(request.POST, request=request)
        if form.is_valid():
            competition = form.save(commit=False)
            competition.owner = request.user
            if request.user.is_superuser:
                competition.is_public = True
            competition.save()
            form.save_m2m()
            return redirect('competition_list')
    else:
        form = CompetitionForm(request=request)

    return render(request, 'add_competition.html', {'form': form})


@login_required
def edit_competition(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    if not check_ownership(request, competition):
        return redirect('competition_list')

    if request.method == 'POST':
        form = CompetitionForm(request.POST, instance=competition, request=request)
        if form.is_valid():
            form.save()
            return redirect('competition_detail', pk=pk)
    else:
        form = CompetitionForm(instance=competition, request=request)

    return render(request, 'edit_competition.html', {'form': form, 'competition': competition})


@login_required
def competition_stages(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    if not (competition.owner == request.user or competition.is_public):
        raise PermissionDenied

    group_stages = competition.groupstage_stages.all()
    knockout_stages = competition.knockoutstage_stages.all()
    stages = list(group_stages) + list(knockout_stages)

    stages_with_matches = []
    for stage in stages:
        matches = stage.matches.all()
        stages_with_matches.append({'stage': stage, 'matches': matches})

    return render(request, 'competition_stages.html', {
        'competition': competition,
        'stages_with_matches': stages_with_matches
    })


@login_required
def competition_list(request):
    competitions = Competition.objects.filter(Q(owner=request.user) | Q(is_public=True))
    return render(request, 'competition_list.html', {'competitions': competitions})


def competition_detail(request, pk):
    competition = get_object_or_404(Competition, pk=pk)

    # 1. Pobieranie danych (bez zmian)
    group_stages_qs = competition.groupstage_stages.prefetch_related(
        'groups__standings__player',
        'groups__matches',
        'groups__matches__player1',
        'groups__matches__player2',
        'groups__matches__venue'
    )

    knockout_stages_qs = competition.knockoutstage_stages.prefetch_related(
        'matches',
        'matches__player1',
        'matches__player2',
        'matches__venue'
    )

    # 2. Logika widoku Drabinki (NOWOŚĆ)
    view_mode = request.GET.get('view', 'list')  # Domyślnie lista

    for stage in knockout_stages_qs:
        matches = stage.matches.all().order_by('round_number', 'id')

        rounds_map = defaultdict(list)
        stage.third_place_matches = []  # <--- Tworzymy listę na mecz o 3 miejsce

        for m in matches:
            if m.round_number < 99:
                # Główne drzewo
                rounds_map[m.round_number].append(m)
            else:
                # Mecz o 3 miejsce (lub inne specjalne)
                stage.third_place_matches.append(m)

        # Budowanie drzewa (bez zmian)
        stage.bracket_tree = []
        for r_num in sorted(rounds_map.keys()):
            stage.bracket_tree.append({
                'round_number': r_num,
                'matches': rounds_map[r_num]
            })

    # 3. Łączenie etapów (bez zmian)
    from itertools import chain
    all_stages = sorted(
        chain(group_stages_qs, knockout_stages_qs),
        key=lambda s: s.order,
        reverse=True
    )

    is_owner = (request.user == competition.owner)
    add_players_url = reverse('add_players_to_competition', args=[competition.id])

    return render(request, 'competition_detail.html', {
        'competition': competition,
        'all_stages': all_stages,
        'is_owner': is_owner,
        'add_players_url': add_players_url,
        'view_mode': view_mode,
    })


class CompetitionDeleteView(DeleteView):
    model = Competition
    template_name = 'delete_competition.html'
    success_url = reverse_lazy('competition_list')

    def get_queryset(self):
        return Competition.objects.filter(owner=self.request.user)


# --- Sprawdzanie kolejności etapów ---
def get_next_stage_order_or_block(competition, request):
    """
    Sprawdza, czy poprzedni etap jest zakończony.
    Zwraca (next_order, error_message).
    Jeśli error_message jest ustawiony, należy przerwać akcję.
    """
    # Pobieramy wszystkie etapy posortowane
    stages = competition.get_stages()  # Używamy metody z modelu Competition

    if not stages:
        return 1, None  # To pierwszy etap, Order = 1

    last_stage = stages[-1]  # Ostatni dodany etap

    if not last_stage.is_finished:
        return None, f"You must finish the current stage '{last_stage.name}' before adding a new one."

    return last_stage.order + 1, None


@login_required
def add_matches_to_competition(request, competition_id):
    """
    Tworzy pojedynczy 'Extra Match' w ramach turnieju.
    """
    competition = get_object_or_404(Competition, pk=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        form = ExtraMatchForm(request.POST, competition=competition)
        if form.is_valid():
            # 1. Znajdź lub stwórz etap "Extras"
            extra_stage, created = KnockoutStage.objects.get_or_create(
                competition=competition,
                name="Extras",
                defaults={
                    'order': 999,
                    'num_rounds': 1,
                    'frames_per_match': form.cleaned_data['number_of_frames'],
                    'has_third_place_match': False
                }
            )

            # 2. Utwórz mecz
            match = form.save(commit=False)
            match.owner = request.user
            match.knockout_stage = extra_stage
            match.knockout_name = "Extra Match"

            # Zapisujemy mecz.
            # To uruchomi nasz "automat" w models.py, który stworzy wpisy w MatchPlayer.
            match.save()

            messages.success(request, "Extra Match created successfully!")
            return redirect('competition_detail', pk=competition.pk)
    else:
        form = ExtraMatchForm(competition=competition, initial={
            'date': timezone.now().date(),
            'time': timezone.now().strftime('%H:%M'),
            'number_of_frames': 3
        })

    return render(request, 'add_matches_to_competition.html', {
        'form': form,
        'competition': competition
    })


def create_temporary_match(request):
    # Czyścimy sesję (bez zmian)
    if 'temp_match_id' in request.session:
        del request.session['temp_match_id']

    if request.method == 'POST':
        form = MatchForm(request.POST, request=request)
        if form.is_valid():
            # To przypisuje dane z formularza do obiektu (w tym player1/player2 jeśli wybrano z listy)
            match = form.save(commit=False)

            # Ustawienia zależne od logowania
            if request.user.is_authenticated:
                match.owner = request.user
                match.is_public = False
            else:
                match.owner = None
                match.is_public = True

            match.is_temporary = True

            # --- LOGIKA GRACZY ---
            create_temp = form.cleaned_data.get('create_temporary_players')

            if not request.user.is_authenticated or create_temp:
                # SCENARIUSZ 1: Tworzymy nowych graczy tymczasowych
                prefix = "Temporary Player"

                # Tworzymy obiekty Player
                p1 = Player.objects.create(first_name=f"{prefix} 1", is_temporary=True, owner=match.owner)
                p2 = Player.objects.create(first_name=f"{prefix} 2", is_temporary=True, owner=match.owner)

                # --- ZMIANA: Przypisujemy ich do foteli ---
                match.player1 = p1
                match.player2 = p2

                # Pola pomocnicze do sprzątania
                match.temp_player1 = p1
                match.temp_player2 = p2

            # --- ZAPIS ---
            # To wywołuje kod w models.py, który automatycznie tworzy MatchPlayer!
            match.save()

            # Zapisujemy sędziów (bo to relacja ManyToMany, wymaga zapisanego ID meczu)
            form.save_m2m()

            if not request.user.is_authenticated:
                request.session['temp_match_id'] = match.id

            return redirect('match_detail', pk=match.pk)
    else:
        form = MatchForm(request=request)

    return render(request, 'create_temporary_match.html', {'form': form})


@login_required
def create_group_stage(request, competition_id):
    competition = get_object_or_404(Competition, id=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    # 1. Sprawdzamy czy można dodać etap
    next_order, error_msg = get_next_stage_order_or_block(competition, request)
    if error_msg:
        messages.error(request, error_msg)
        return redirect('competition_detail', pk=competition.id)

    # 2. Logika formularza
    winner_list, eliminated_list, other_list = get_sorted_players_for_stage(competition, request.user)

    if request.method == 'POST':
        form = GroupStageForm(
            request.POST,
            competition=competition,
            winners=winner_list,
            eliminated=eliminated_list,
            others=other_list
        )
        if form.is_valid():
            stage = form.save(commit=False)
            stage.competition = competition
            stage.order = next_order  # <--- AUTO ORDER (Wymuszamy)
            stage.save()

            # (Tu reszta logiki zapisu graczy i generowania meczów - bez zmian)
            selected_players = form.cleaned_data.get('players')
            if selected_players:
                competition.players.add(*selected_players)

            stage.create_groups_and_matches(
                default_frames=form.cleaned_data.get('default_frames'),
                selected_players=selected_players
            )

            messages.success(request, f"Group Stage '{stage.name}' created successfully.")
            return redirect('competition_detail', pk=competition.id)
    else:
        # Przekazujemy next_order jako initial (dla pewności, choć pole jest ukryte)
        form = GroupStageForm(
            initial={'order': next_order},
            competition=competition,
            winners=winner_list,
            eliminated=eliminated_list,
            others=other_list
        )

    return render(request, 'create_group_stage.html', {'form': form, 'competition': competition})


@login_required
def create_knockout_stage(request, competition_id):
    competition = get_object_or_404(Competition, id=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    # 1. Sprawdzamy czy można dodać etap
    next_order, error_msg = get_next_stage_order_or_block(competition, request)
    if error_msg:
        messages.error(request, error_msg)
        return redirect('competition_detail', pk=competition.id)

    # 2. Pobieramy graczy (z logiką awansu z grup, którą robiliśmy wcześniej)
    winners, eliminated, others = get_sorted_players_for_stage(competition, request.user)

    last_group_stage = competition.groupstage_stages.order_by('-order').first()
    if last_group_stage:
        qualifiers = []
        limit = last_group_stage.num_qualifiers
        for group in last_group_stage.groups.all():
            standings = group.standings.order_by('-points', '-frames_won', '-small_points_scored')[:limit]
            for standing in standings:
                qualifiers.append(standing.player)
        if qualifiers:
            winners = qualifiers

    if request.method == 'POST':
        form = KnockoutStageForm(
            request.POST,
            competition=competition,
            winners=winners,
            eliminated=eliminated,
            others=others
        )
        if form.is_valid():
            stage = form.save(commit=False)
            stage.competition = competition
            stage.order = next_order  # <--- AUTO ORDER
            stage.save()

            selected_players = form.cleaned_data.get('players')
            if selected_players:
                competition.players.add(*selected_players)

            stage.create_knockout_matches(selected_players=selected_players)

            messages.success(request, f"Knockout Stage '{stage.name}' created successfully.")
            return redirect('competition_detail', pk=competition.id)
    else:
        form = KnockoutStageForm(
            initial={'order': next_order},
            competition=competition,
            winners=winners,
            eliminated=eliminated,
            others=others
        )

    return render(request, 'create_knockout_stage.html', {'form': form, 'competition': competition})


def register(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)

            # --- PRZEJMOWANIE MECZU TYMCZASOWEGO ---
            temp_match_id = request.session.get('temp_match_id')

            if temp_match_id:
                try:
                    # Szukamy meczu po ID z sesji
                    match = Match.objects.get(pk=temp_match_id)

                    # Jeśli mecz nie ma właściciela (jest sierotą), to go przejmujemy
                    if match.owner is None:
                        match.owner = user
                        match.is_temporary = False  # To już nie jest tymczasowy mecz
                        match.is_public = False  # Staje się prywatny
                        match.save()

                        # --- NAPRAWA: Iterujemy po konkretnych fotelach ---
                        players_to_check = [match.player1, match.player2]

                        for player in players_to_check:
                            # Sprawdzamy 'if player', bo teoretycznie któryś fotel mógłby być pusty
                            if player and player.owner is None:
                                player.owner = user
                                player.is_temporary = False
                                player.save()
                        # --------------------------------------------------

                        messages.success(request, "Registration successful! Your temporary match has been saved to your account.")

                        # Czyścimy sesję
                        del request.session['temp_match_id']

                        # Przekierowujemy od razu do tego meczu
                        return redirect('match_detail', pk=match.pk)

                except Match.DoesNotExist:
                    # Mecz mógł zostać usunięty w międzyczasie, ignorujemy to
                    pass
            # ---------------------------------------

            messages.success(request, "Registration successful.")
            return redirect('home')
        else:
            messages.error(request, "Registration failed. Check for errors below.")
    else:
        form = SignUpForm()
    return render(request, 'register.html', {'form': form})


def home(request):
    # Strona główna dostępna dla każdego (zalogowani widzą co innego w menu)
    return render(request, 'home.html')


@login_required
def user_settings(request):
    user = request.user
    if request.method == 'POST':
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password updated!")
            return redirect('login')
        else:
            messages.error(request, 'Please correct error.')
    else:
        form = PasswordChangeForm(user)
    return render(request, 'user_settings.html', {'form': form})


@login_required
def delete_user(request):
    user = request.user
    if request.method == 'POST':
        user.delete()
        return redirect('home')
    return render(request, 'delete_user.html', {'user': user})


def custom_logout(request):
    logout(request)
    return redirect(reverse('login'))


@login_required
def add_players_to_competition(request, pk):
    competition = get_object_or_404(Competition, id=pk)
    if competition.owner != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        player_ids = request.POST.getlist('players')
        players = Player.objects.filter(id__in=player_ids, is_guest=False)
        competition.players.add(*players)
        return redirect('competition_detail', pk=competition.id)
    else:
        # Pokaż tylko moich + publicznych graczy, którzy nie są w tym turnieju
        available_players = Player.objects.filter(
            (Q(owner=request.user) | Q(is_public=True)) & Q(is_guest=False)
        ).exclude(competitions=competition)

        return render(request, 'add_players_to_competition.html', {
            'competition': competition,
            'available_players': available_players
        })


@login_required
def achievement_list(request):
    # Sortujemy np. po najwyższym breaku malejąco
    # ZMIANA: Dodano warunek & Q(is_guest=False)
    players = Player.objects.filter(
        (Q(owner=request.user) | Q(is_public=True)) & Q(is_guest=False)
    ).order_by('-highest_break')

    # Przekazujemy listę graczy do szablonu (zamiast achievements)
    return render(request, 'achievement_list.html', {'players': players})


client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


@csrf_exempt
@require_POST
def gpt_analysis(request):
    # Zakomentowane na życzenie
    return JsonResponse({'error': 'Feature disabled'}, status=503)


@csrf_exempt
@require_POST
def update_game_data(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        match_id = data.get('match_id')
        player_id = data.get('player_id')
        points = data.get('points')

        # Opcjonalne: kolor bili do statystyk
        ball_color = data.get('ball_color')

        if match_id is None or player_id is None or points is None:
            return JsonResponse({'status': 'error', 'message': 'Missing data fields'})

        # KROK 1: Próbujemy znaleźć Frame'a
        try:
            frame = Frame.objects.filter(match_player__match_id=match_id).latest('frame_number')
        except Frame.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'No active frame found for this match'})

        # KROK 2: Ustalamy, KTÓRY to gracz (1 czy 2?) - TYLKO TWARDE DANE
        match_player = MatchPlayer.objects.filter(match_id=match_id, player_id=player_id).first()

        target_position = None

        if match_player:
            # Ufamy tylko bazie danych
            target_position = match_player.position
        else:
            # ZERO TOLERANCE: Jeśli gracza nie ma w MatchPlayer, to jest błąd krytyczny.
            # Nie zgadujemy, nie sprawdzamy czy ID to "1" czy "2".
            return JsonResponse(
                {'status': 'error', 'message': f'Security: Player ID {player_id} is not assigned to Match {match_id}.'})

        # KROK 3: Zapisujemy punkty we właściwej kolumnie
        if target_position == 1:
            frame.points_scored_player1 = (frame.points_scored_player1 or 0) + points
            if frame.break_points_player1 is None: frame.break_points_player1 = []
            frame.break_points_player1.append(points)

        elif target_position == 2:
            frame.points_scored_player2 = (frame.points_scored_player2 or 0) + points
            if frame.break_points_player2 is None: frame.break_points_player2 = []
            frame.break_points_player2.append(points)

        else:
            # To się teoretycznie nie powinno wydarzyć, jeśli MatchPlayer ma position 1 lub 2
            return JsonResponse({'status': 'error', 'message': f'Invalid player position: {target_position}'})

        frame.save()
        return JsonResponse({'status': 'success'})

    except Exception as e:
        print(f"Error in update_game_data: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})


@csrf_exempt
@require_POST
def set_active_player(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        match_id = data.get('match_id')
        frame_id = data.get('frame_id')
        player_id = data.get('player_id')

        if frame_id is None or player_id is None:
            return JsonResponse({'status': 'error', 'message': 'Invalid frame or player ID'})

        frame = Frame.objects.get(id=frame_id)
        player = Player.objects.get(id=player_id)
        frame.active_player = player
        frame.save()

        if match_id is None or player_id in None:
            return JsonResponse({'status': 'error', 'message': 'Missing match_id or plauer_id'})

        match_player = MatchPlayer.objects.filter(match_id=match_id, player_id=player_id).first()

        if not match_player:
            return JsonResponse({'status': 'error', 'message': 'Match of player not found'})

        match_player.is_active = True
        match_player.save()

        MatchPlayer.objects.filter(match_id=match_id).exclude(player_id=player_id).update(is_active=False)

        return JsonResponse({'status': 'success', 'active_player': player_id})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
def save_frame_result(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        match_id = data.get('match_id')

        # --- ZABEZPIECZENIE API ---
        match = get_object_or_404(Match, pk=match_id)

        has_access = False
        if match.owner is None:
            has_access = True
        elif match.is_public:
            has_access = True
        elif request.user.is_authenticated and match.owner == request.user:
            has_access = True

        if not has_access:
            return JsonResponse({'status': 'error', 'message': 'Permission Denied'}, status=403)

        game_status = match.get_game_status()
        if game_status['is_finished']:
            return JsonResponse({'status': 'error', 'message': 'Match is already finished!'}, status=400)
        # ---------------------------

        winner_id = data.get('winner_id')
        p1_score = data.get('p1_score')
        p2_score = data.get('p2_score')
        duration_seconds = data.get('duration', 0)

        # Statystyki...
        p1_fouls = data.get('p1_fouls', 0)
        p2_fouls = data.get('p2_fouls', 0)
        p1_foul_pts = data.get('p1_foul_pts', 0)
        p2_foul_pts = data.get('p2_foul_pts', 0)
        p1_shots = data.get('p1_shots', 0)
        p1_misses = data.get('p1_misses', 0)
        p1_pots = data.get('p1_pots', 0)
        p2_shots = data.get('p2_shots', 0)
        p2_misses = data.get('p2_misses', 0)
        p2_pots = data.get('p2_pots', 0)
        p1_safeties = data.get('p1_safeties', 0)
        p2_safeties = data.get('p2_safeties', 0)
        p1_safe_succ = data.get('p1_safe_success_count', 0)
        p2_safe_succ = data.get('p2_safe_success_count', 0)
        p1_breaks_list = data.get('p1_breaks', [])
        p2_breaks_list = data.get('p2_breaks', [])

        if not all([match_id, winner_id, p1_score is not None, p2_score is not None]):
            return JsonResponse({'status': 'error', 'message': 'Missing data fields'})

        winner = get_object_or_404(Player, pk=winner_id)

        # 1. Pobieramy graczy (CZYSTA LOGIKA)
        match_players = MatchPlayer.objects.filter(match=match).order_by('position')

        # --- ZERO TOLERANCE ---
        # Jeśli nie ma graczy w MatchPlayer, przerywamy. Nie naprawiamy na siłę.
        if not match_players.exists():
            return JsonResponse({
                'status': 'error',
                'message': 'CRITICAL ERROR: Match data integrity violation. Players not found in MatchPlayer table. Please recreate the match.'
            })

        # 2. Szukamy ostatniego frama
        last_frame = Frame.objects.filter(match_player__in=match_players).order_by('-frame_number').first()

        # --- SEKCJA RATUNKOWA FRAMA (To zostawiamy, bo tworzenie frama jest bezpieczne, jeśli mamy graczy) ---
        if not last_frame:
            last_frame = Frame.objects.create(
                match_player=match_players.first(),
                frame_number=1,
                points_scored_player1=0,
                points_scored_player2=0,
                active_player=match_players.first().player
            )

        # --- OBLICZANIE SKUTECZNOŚCI ---
        p1_attempts = p1_pots + p1_misses
        p1_success_rate = 0.0
        if p1_attempts > 0:
            p1_success_rate = round((p1_pots / p1_attempts) * 100, 2)

        p2_attempts = p2_pots + p2_misses
        p2_success_rate = 0.0
        if p2_attempts > 0:
            p2_success_rate = round((p2_pots / p2_attempts) * 100, 2)

        # 3. Zapisz wyniki
        last_frame.points_scored_player1 = p1_score
        last_frame.points_scored_player2 = p2_score
        last_frame.winner = winner
        last_frame.player1_fouls = p1_fouls
        last_frame.player2_fouls = p2_fouls
        last_frame.foul_points_player1 = p1_foul_pts
        last_frame.foul_points_player2 = p2_foul_pts
        last_frame.total_shots_player1 = p1_shots
        last_frame.total_shots_player2 = p2_shots
        last_frame.misses_player1 = p1_misses
        last_frame.misses_player2 = p2_misses
        last_frame.potted_balls_player1 = p1_pots
        last_frame.potted_balls_player2 = p2_pots
        last_frame.pot_success_percentage_player1 = p1_success_rate
        last_frame.pot_success_percentage_player2 = p2_success_rate
        last_frame.safety_shot_player1 = p1_safeties
        last_frame.safety_shot_player2 = p2_safeties
        last_frame.successful_safety_shots_player1 = p1_safe_succ
        last_frame.successful_safety_shots_player2 = p2_safe_succ

        if duration_seconds > 0:
            last_frame.time_duration = timedelta(seconds=duration_seconds)

        last_frame.break_points_player1 = p1_breaks_list
        last_frame.break_points_player2 = p2_breaks_list

        if p1_breaks_list:
            last_frame.max_break_player1 = max(p1_breaks_list)
        else:
            last_frame.max_break_player1 = 0

        if p2_breaks_list:
            last_frame.max_break_player2 = max(p2_breaks_list)
        else:
            last_frame.max_break_player2 = 0

        last_frame.save()

        # 4. Aktualizacja statusu
        match.update_status_from_frames()
        game_status = match.get_game_status()
        match_over = game_status['is_finished']
        match_winner_obj = game_status['winner']

        winner_name = "Unknown"
        if match_over:
            if match_winner_obj:
                winner_name = str(match_winner_obj)
            else:
                winner_name = "Draw"

            players_in_match = [mp.player for mp in match_players]
            for p in players_in_match:
                if p:
                    update_career_stats(p)

        if not match_over:
            new_frame_number = last_frame.frame_number + 1
            Frame.objects.create(
                match_player=match_players.first(),
                frame_number=new_frame_number,
                points_scored_player1=0,
                points_scored_player2=0,
                active_player=match_players.first().player
            )

        return JsonResponse({
            'status': 'success',
            'match_over': match_over,
            'match_winner': winner_name if match_over else None
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
def update_player_stats(request):
    """
    Updates player statistics (shots count and time spent) when they leave the table.
    Expects JSON data: { frame_id, player_id, added_shots, added_time_seconds }
    """
    try:
        data = json.loads(request.body)
        frame_id = data.get('frame_id')
        player_id = data.get('player_id')
        added_shots = int(data.get('added_shots', 0))
        added_time = float(data.get('added_time_seconds', 0.0))

        frame = get_object_or_404(Frame, id=frame_id)

        # Create a timedelta object from the seconds received
        time_delta = timedelta(seconds=added_time)

        if player_id == 1:
            # Update Shots
            frame.total_shots_player1 += added_shots

            # Update Time (Handle None case for the first update)
            if frame.time_shots_player1 is None:
                frame.time_shots_player1 = time_delta
            else:
                frame.time_shots_player1 += time_delta

        elif player_id == 2:
            # Update Shots
            frame.total_shots_player2 += added_shots

            # Update Time
            if frame.time_shots_player2 is None:
                frame.time_shots_player2 = time_delta
            else:
                frame.time_shots_player2 += time_delta

        frame.save()

        return JsonResponse({'status': 'success', 'message': 'Stats updated'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def mass_edit_matches(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    if competition.owner != request.user:
        raise PermissionDenied

    # 1. Pobieramy mecze (Grupy + Puchar)
    # --- WAŻNA ZMIANA SORTOWANIA ---
    # Musimy sortować najpierw po ETAPIE, potem po GRUPIE/RUNDZIE, a dopiero na końcu po CZASIE.
    # Dzięki temu w HTML tag {% ifchanged %} ładnie pogrupuje mecze belkami.
    matches = (Match.objects.filter(
        Q(group_stage__competition=competition) |
        Q(knockout_stage__competition=competition)
    ).exclude(status='FINISHED') \
    .exclude(player1__isnull=True) \
    .exclude(player2__isnull=True) \
    .order_by(
        'group_stage',  # Najpierw etap grupowy
        'group',  # Potem konkretna grupa (1, 2, 3...)
        'knockout_stage',  # Potem etap pucharowy
        'round_number',  # Potem numer kolejki/rundy (TO JEST KLUCZOWE!)
        'date',  # Dopiero teraz data
        'time'  # I godzina
    ))

    # Tworzymy klasę Formsetu
    MatchFormSet = modelformset_factory(
        Match,
        form=MassMatchEditForm,
        formset=MatchFormSetValidating,
        extra=0
        )

    if request.method == 'POST':
        formset = MatchFormSet(request.POST, queryset=matches)
        if formset.is_valid():
            # Zapis formularzy
            formset.save()
            messages.success(request, "Matches updated successfully.")
            return redirect('competition_detail', pk=competition.id)
    else:
        formset = MatchFormSet(queryset=matches)

    # --- FILTROWANIE DROPDOWNÓW ---
    my_referees = Referee.objects.filter(Q(owner=request.user) | Q(is_public=True))

    # Pobieramy bazową listę wszystkich graczy w turnieju
    all_tournament_players = competition.players.all()

    for form in formset:
        # 1. Sędziowie (bez zmian)
        form.fields['referees'].queryset = my_referees

        # 2. Pobieramy instancję meczu dla tego wiersza
        match = form.instance

        # 3. Ustalamy, kogo można wybrać w tym wierszu
        # Domyślnie: Wszyscy z turnieju (dla Play-off)
        allowed_players = all_tournament_players

        # Jeśli mecz należy do GRUPY -> zawężamy listę tylko do członków tej grupy
        if match.group:
            # Pobieramy ID graczy z tabeli tej konkretnej grupy
            group_ids = match.group.standings.values_list('player_id', flat=True)
            allowed_players = all_tournament_players.filter(id__in=group_ids)

        # 4. Przypisujemy "skrojoną na miarę" listę do pól
        if 'player1' in form.fields:
            form.fields['player1'].queryset = allowed_players
        if 'player2' in form.fields:
            form.fields['player2'].queryset = allowed_players

    return render(request, 'mass_edit_matches.html', {
        'formset': formset,
        'competition': competition
    })


# --- FUNKCJA POMOCNICZA W VIEWS.PY ---

def get_sorted_players_for_stage(competition, user):
    """
    Zwraca trzy listy graczy:
    1. winners: Zwycięzcy ostatniego etapu
    2. eliminated: Przegrani w ostatnim etapie
    3. others: Wszyscy pozostali gracze użytkownika (bez tymczasowych),
       którzy nie grali w ostatnim etapie.
    """

    # 1. Znajdź wszystkie etapy i posortuj
    group_stages = list(competition.groupstage_stages.all())
    knockout_stages = list(competition.knockoutstage_stages.all())
    all_stages = sorted(group_stages + knockout_stages, key=lambda x: x.order)

    # Pobieramy tylko tych graczy, którzy są uczestnikami TEGO turnieju
    all_user_players = set(competition.players.all())

    # Jeśli to pierwszy etap (brak historii etapów), wszyscy Twoi gracze trafiają do 'others'
    if not all_stages:
        return [], [], list(all_user_players)

    # 3. Pobierz ostatni etap
    last_stage = all_stages[-1]

    # Pobierz mecze
    if hasattr(last_stage, 'matches'):
        matches = last_stage.matches.filter(status='FINISHED')
    else:
        matches = []

    # 4. Sortowanie uczestników ostatniego etapu
    winners = set()
    participants = set()  # Wszyscy, którzy grali w ostatnim etapie

    for match in matches:
        # Sprawdzamy konkretne fotele
        if match.player1:
            participants.add(match.player1)
        if match.player2:
            participants.add(match.player2)
        # -------------------------------------------------------------

        if match.winner:
            winners.add(match.winner)

    # Przegrani to: Uczestnicy ostatniego etapu MINUS Zwycięzcy
    eliminated = participants - winners

    # Inni to: Wszyscy Twoi gracze z bazy MINUS ci, którzy brali udział w ostatnim etapie
    others = all_user_players - participants

    return list(winners), list(eliminated), list(others)


# --- ZAMYKANIE ETAPÓW I TURNIEJU ---

@login_required
def end_group_stage(request, stage_id):
    stage = get_object_or_404(GroupStage, pk=stage_id)
    if stage.competition.owner != request.user:
        raise PermissionDenied

    stage.is_finished = True
    stage.save()
    messages.success(request, f"Stage '{stage.name}' has been marked as finished.")
    return redirect('competition_detail', pk=stage.competition.id)


@login_required
def end_knockout_stage(request, stage_id):
    stage = get_object_or_404(KnockoutStage, pk=stage_id)
    if stage.competition.owner != request.user:
        raise PermissionDenied

    stage.is_finished = True
    stage.save()
    messages.success(request, f"Stage '{stage.name}' has been marked as finished.")
    return redirect('competition_detail', pk=stage.competition.id)


@login_required
def end_competition(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    # Ustawiamy status turnieju na FINISHED
    # (Upewnij się, że masz takie pole w modelu Competition, jeśli nie - dodaj je)
    competition.status = 'FINISHED'
    competition.save()

    messages.success(request, f"Tournament '{competition.name}' has been officially closed! 🏆")
    return redirect('competition_ranking', competition_id=competition.pk)


@receiver(user_logged_in)
def claim_temporary_match(sender, user, request, **kwargs):
    """
    Funkcja uruchamia się AUTOMATYCZNIE po każdym poprawnym zalogowaniu.
    Sprawdza, czy w sesji jest ID tymczasowego meczu i przypisuje go do użytkownika.
    """
    temp_match_id = request.session.get('temp_match_id')

    if temp_match_id:
        try:
            # Szukamy meczu, który nie ma właściciela (jest gościa)
            match = Match.objects.get(id=temp_match_id, owner__isnull=True)

            # 1. Przypisujemy mecz do użytkownika
            match.owner = user
            match.save()

            # 2. Przypisujemy też graczy tymczasowych do tego użytkownika!
            # Tworzymy listę potencjalnych graczy do sprawdzenia
            # (może być None, dlatego w pętli sprawdzamy 'if player')
            players_to_check = [match.player1, match.player2]

            for player in players_to_check:
                if player and player.is_temporary and player.owner is None:
                    player.owner = user
                    player.save()
            # -----------------------------------------------------------------------

            if 'temp_match_id' in request.session:
                del request.session['temp_match_id']

            print(f"Success! Match {match.id} has been assigned to the user {user}.")

        except Match.DoesNotExist:
            pass


@login_required
def substitute_player(request, stage_id):
    stage = get_object_or_404(GroupStage, pk=stage_id)
    competition = stage.competition

    if competition.owner != request.user:
        raise PermissionDenied

    # Blokada dla zakończonego etapu
    if stage.is_finished:
        messages.error(request, "Cannot substitute players in a finished stage.")
        return redirect('competition_detail', pk=competition.id)

    if request.method == 'POST':
        form = SubstitutePlayerForm(request.POST, stage=stage, owner=request.user)
        if form.is_valid():
            player_out = form.cleaned_data['player_out']
            player_in = form.cleaned_data['player_in']

            # --- OPERACJA PODMIANY (Transakcja atomowa dla bezpieczeństwa) ---
            with transaction.atomic():
                # 1. Dodaj nowego gracza do turnieju (jeśli go nie ma)
                competition.players.add(player_in)

                # 2. Podmień w TABELI (GroupStanding)
                # Szukamy wpisu starego gracza w tym etapie
                standing = GroupStanding.objects.filter(
                    group__stage=stage,
                    player=player_out
                ).first()

                if standing:
                    standing.player = player_in
                    standing.save()

                # 3. Podmień w MECZACH (Player 1)
                matches_p1 = Match.objects.filter(group_stage=stage, player1=player_out)
                for match in matches_p1:
                    match.player1 = player_in
                    match.save()

                # 4. Podmień w MECZACH (Player 2)
                matches_p2 = Match.objects.filter(group_stage=stage, player2=player_out)
                for match in matches_p2:
                    match.player2 = player_in
                    match.save()

            messages.success(request, f"Successfully substituted {player_out} with {player_in}.")
            return redirect('competition_detail', pk=competition.id)
    else:
        form = SubstitutePlayerForm(stage=stage, owner=request.user)

    return render(request, 'substitute_player.html', {
        'form': form,
        'stage': stage,
        'competition': competition
    })


@login_required
def manage_groups(request, stage_id):
    stage = get_object_or_404(GroupStage, pk=stage_id)
    competition = stage.competition

    if competition.owner != request.user:
        raise PermissionDenied

    # BLOKADA BEZPIECZEŃSTWA
    if stage.matches.filter(status='FINISHED').exists():
        messages.error(request, "Cannot edit groups because matches have already been played.")
        return redirect('competition_detail', pk=competition.id)

    # Definiujemy Formset (Tabela edycji dla wszystkich graczy)
    StandingFormSet = modelformset_factory(
        GroupStanding,
        form=GroupAssignmentForm,
        extra=0,  # Nie chcemy pustych wierszy automat
        can_delete=True  # Włączamy obsługę usuwania
    )
    # Musimy przekazać 'stage' do formularza wewnątrz formsetu, więc używamy form_kwargs
    formset_queryset = GroupStanding.objects.filter(group__stage=stage).order_by('group__name', 'player__last_name')

    if request.method == 'POST':
        # Sprawdzamy czy to akcja dodawania nowego gracza
        if 'add_player_submit' in request.POST:
            add_form = AddPlayerToGroupForm(request.POST, stage=stage, owner=request.user)
            if add_form.is_valid():
                new_player = add_form.cleaned_data['player']
                target_group = add_form.cleaned_data['group']
                competition.players.add(new_player)  # Upewniamy się, że jest w turnieju

                # Tworzymy wpis w tabeli
                GroupStanding.objects.create(
                    group=target_group, player=new_player,
                    matches_played=0, matches_won=0, matches_drawn=0, matches_lost=0,
                    frames_won=0, frames_lost=0, points=0,
                    small_points_scored=0, small_points_conceded=0, highest_break=0
                )
                messages.success(request, f"Added {new_player} to Group {target_group.name}.")
                # Po dodaniu od razu regenerujemy mecze
                stage.regenerate_schedule()
                return redirect('manage_groups', stage_id=stage.id)

        # Sprawdzamy czy to akcja zapisu zmian w grupach (Formset)
        else:
            formset = StandingFormSet(request.POST, queryset=formset_queryset, form_kwargs={'stage': stage})
            if formset.is_valid():
                formset.save()  # Zapisuje zmiany grup i usuwa zaznaczonych graczy

                # REGENERACJA TERMINARZA
                success, msg = stage.regenerate_schedule()
                if success:
                    messages.success(request, "Groups updated and schedule regenerated successfully.")
                else:
                    messages.error(request, msg)

                return redirect('competition_detail', pk=competition.id)
            else:
                add_form = AddPlayerToGroupForm(stage=stage, owner=request.user)

    else:
        # GET request
        formset = StandingFormSet(queryset=formset_queryset, form_kwargs={'stage': stage})
        add_form = AddPlayerToGroupForm(stage=stage, owner=request.user)

    return render(request, 'manage_groups.html', {
        'stage': stage,
        'formset': formset,
        'add_form': add_form,
        'competition': competition
    })


@login_required
def manage_knockout(request, stage_id):
    stage = get_object_or_404(KnockoutStage, pk=stage_id)
    competition = stage.competition

    if competition.owner != request.user:
        raise PermissionDenied

    # Pobieramy mecze 1. rundy do wyświetlenia (żebyś widział kogo zamieniasz)
    matches_r1 = Match.objects.filter(knockout_stage=stage, round_number=1).order_by('id')

    if request.method == 'POST':
        form = KnockoutSwapForm(request.POST, stage=stage)
        if form.is_valid():
            p1 = form.cleaned_data['player_1']
            p2 = form.cleaned_data['player_2']

            # --- LOGIKA SWAP (ZAMIANA) ---
            # Musimy znaleźć mecze, w których Ci gracze są
            # Uwaga: Mogą być w tym samym meczu (zamiana gospodarz/gość) lub w różnych

            # Szukamy meczu dla P1
            m1 = matches_r1.filter(player1=p1).first() or matches_r1.filter(player2=p1).first()
            # Szukamy meczu dla P2
            m2 = matches_r1.filter(player1=p2).first() or matches_r1.filter(player2=p2).first()

            if m1 and m2:
                # Jeśli to ten sam mecz -> prosta zamiana stron
                if m1 == m2:
                    m1.player1, m1.player2 = m1.player2, m1.player1
                    m1.save()
                else:
                    # Różne mecze -> Krzyżowa zamiana
                    # 1. Gdzie w m1 jest p1?
                    if m1.player1 == p1:
                        m1.player1 = p2
                    else:
                        m1.player2 = p2

                    # 2. Gdzie w m2 jest p2?
                    if m2.player1 == p2:
                        m2.player1 = p1
                    else:
                        m2.player2 = p1

                    m1.save()
                    m2.save()

                messages.success(request, f"Swapped {p1} with {p2}.")
                return redirect('manage_knockout', stage_id=stage.id)
            else:
                messages.error(request, "Could not find matches for selected players.")
    else:
        form = KnockoutSwapForm(stage=stage)

    return render(request, 'manage_knockout.html', {
        'stage': stage,
        'competition': competition,
        'matches': matches_r1,
        'form': form
    })


@login_required
def substitute_player_knockout(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    if competition.owner != request.user:
        raise PermissionDenied

    # 1. POBIERAMY ETAP PUCHAROWY
    # Musimy znaleźć KnockoutStage przypisany do tego turnieju.
    # Używamy .first(), zakładając że jest jeden (standard w turniejach).
    knockout_stage = competition.knockoutstage_stages.first()

    if not knockout_stage:
        messages.error(request, "Knockout stage not found!")
        return redirect('competition_detail', pk=competition.id)

    if request.method == 'POST':
        # ZMIANA: Przekazujemy 'stage', a nie 'competition'
        form = SubstitutePlayerForm(request.POST, stage=knockout_stage, owner=request.user)

        if form.is_valid():
            p_out = form.cleaned_data['player_out']
            p_in = form.cleaned_data['player_in']

            with transaction.atomic():
                # A. Aktualizacja listy uczestników turnieju (M2M na modelu Competition)
                competition.players.remove(p_out)
                competition.players.add(p_in)

                # B. Znalezienie meczów w fazie pucharowej
                matches_to_fix = Match.objects.filter(
                    knockout_stage=knockout_stage
                ).filter(
                    Q(player1=p_out) | Q(player2=p_out)
                )

                # C. Podmiana w meczach
                count = 0
                for match in matches_to_fix:
                    changed = False
                    if match.player1 == p_out:
                        match.player1 = p_in
                        changed = True

                    if match.player2 == p_out:
                        match.player2 = p_in
                        changed = True

                    if changed:
                        match.save()  # Naprawa MatchPlayer
                        count += 1

                messages.success(request, f"Successfully substituted {p_out} with {p_in} in {count} matches.")
                return redirect('competition_detail', pk=competition.id)
    else:
        # ZMIANA: Tutaj też przekazujemy 'stage'
        form = SubstitutePlayerForm(stage=knockout_stage, owner=request.user)

    return render(request, 'substitute_player.html', {
        'form': form,
        'competition': competition,
        'stage_name': 'Knockout Stage'
    })


# 1. GENEROWANIE KODU (Dla Gościa)
@login_required
def generate_token(request):
    """Generuje 6-cyfrowy kod ważny 90 sekund i odsyła go (np. do modala)."""
    # Usuwamy stare tokeny usera, żeby nie śmiecić
    SharingToken.objects.filter(owner=request.user).delete()

    # Generujemy cyfry
    new_code = get_random_string(length=6, allowed_chars='0123456789')

    SharingToken.objects.create(
        owner=request.user,
        code=new_code
    )

    # Jeśli to żądanie AJAX, można zwrócić JSON, ale tutaj proste przekierowanie/message
    # W praktyce najlepiej zrobić to jako API, ale na razie zróbmy prosto:
    messages.success(request, f"Your Code: {new_code} (Valid for 90 seconds)")
    # Przekieruj tam skąd przyszedł (np. do profilu)
    return redirect(request.META.get('HTTP_REFERER', 'player_list'))


# 2. IMPORTOWANIE GRACZY (Dla Organizatora)


@login_required
def import_players_to_competition(request, comp_id):
    competition = get_object_or_404(Competition, pk=comp_id)

    code_form = ImportCodeForm(request.POST or None)
    select_form = None
    token_owner = None

    if request.method == 'POST':
        # --- KROK 1: Sprawdzenie kodu ---
        if 'check_code' in request.POST and code_form.is_valid():
            code = code_form.cleaned_data['code']
            try:
                token = SharingToken.objects.get(code=code)
                if token.is_valid():
                    token_owner = token.owner
                    # Szukamy graczy u właściciela tokena
                    found_players = Player.objects.filter(owner=token_owner)

                    if not found_players.exists():
                        messages.warning(request, "Code valid, but user has no players.")
                    else:
                        select_form = SelectImportedPlayersForm(found_players=found_players)
                else:
                    code_form.add_error('code', "Code expired.")
            except SharingToken.DoesNotExist:
                code_form.add_error('code', "Invalid code.")

        # --- KROK 2: Import (Klonowanie jako GOŚĆ) ---
        elif 'confirm_import' in request.POST:
            player_ids = request.POST.getlist('selected_players')
            if player_ids:
                source_players = Player.objects.filter(id__in=player_ids)
                count = 0

                for source in source_players:
                    suffix = f" ({source.owner.username})"

                    # Logika nazwy (żeby była unikalna i czytelna)
                    new_last_name = source.last_name + suffix if source.last_name else ""
                    new_first_name = source.first_name
                    new_nickname = source.nickname

                    if not new_last_name:
                        if new_nickname:
                            new_nickname += suffix
                        else:
                            new_first_name += suffix

                    # Sprawdzenie konfliktu w turnieju (czy taki gracz już tu jest?)
                    # Sprawdzamy po nazwisku/imieniu LUB po relacji OneToOne z Userem (jeśli istnieje)
                    is_conflict = False
                    if source.user:
                        is_conflict = competition.players.filter(user=source.user).exists()

                    # Możesz tu dodać sprawdzenie po nazwach stringowych, jeśli chcesz być bardzo ścisły

                    if not is_conflict:
                        # TWORZYMY KLONA-GOŚCIA
                        new_guest = Player.objects.create(
                            owner=request.user,
                            user=source.user,
                            is_guest=True,  # <--- KLUCZOWA ZMIANA: To jest Gość
                            first_name=new_first_name,
                            last_name=new_last_name,
                            nickname=new_nickname,
                            # photo=source.photo
                        )
                        # Dodajemy go do turnieju
                        competition.players.add(new_guest)
                        count += 1

                messages.success(request, f"Imported {count} guests to the tournament.")
                return redirect('competition_detail', pk=competition.id)
            else:
                messages.error(request, "No players selected.")

    return render(request, 'import_players.html', {
        'competition': competition,  # Ważne dla przycisku Cancel
        'code_form': code_form,
        'select_form': select_form,
        'token_owner': token_owner
    })


@login_required
def import_guest_for_match(request):
    """
    Importuje gościa specjalnie dla pojedynczego meczu.
    Po sukcesie wraca do add_match z parametrem ?guest=ID
    """
    code_form = ImportCodeForm(request.POST or None)

    # Jeśli wejście GET (wyświetlenie formularza)
    if request.method == 'GET':
        return render(request, 'import_players.html', {
            'code_form': code_form,
            'is_match_import': True  # Flaga dla template'u
        })

    # Jeśli wejście POST (zatwierdzenie kodu)
    if request.method == 'POST':
        if 'check_code' in request.POST and code_form.is_valid():
            code = code_form.cleaned_data['code']
            try:
                token = SharingToken.objects.get(code=code)
                if token.is_valid():
                    # Pokaż formularz wyboru (ten sam mechanizm co wcześniej)
                    found_players = Player.objects.filter(owner=token.owner)
                    select_form = SelectImportedPlayersForm(found_players=found_players)
                    return render(request, 'import_players.html', {
                        'code_form': code_form,
                        'select_form': select_form,
                        'token_owner': token.owner,
                        'is_match_import': True
                    })
                else:
                    code_form.add_error('code', "Code expired.")
            except SharingToken.DoesNotExist:
                code_form.add_error('code', "Invalid code.")

        elif 'confirm_import' in request.POST:
            player_ids = request.POST.getlist('selected_players')
            if player_ids:
                # Bierzemy pierwszego zaznaczonego (do meczu zazwyczaj 1 vs 1)
                # Ale pętla obsłuży, jakbyś zaznaczył kilku, weźmiemy ostatniego jako "Active"
                last_created_id = None

                source_players = Player.objects.filter(id__in=player_ids)
                for source in source_players:
                    suffix = f" ({source.owner.username})"

                    new_last_name = source.last_name + suffix if source.last_name else ""
                    new_first_name = source.first_name
                    new_nickname = source.nickname

                    if not new_last_name:
                        if new_nickname:
                            new_nickname += suffix
                        else:
                            new_first_name += suffix

                    # Tworzymy Gościa (is_guest=True)
                    new_guest = Player.objects.create(
                        owner=request.user,
                        user=source.user,
                        is_guest=True,
                        first_name=new_first_name,
                        last_name=new_last_name,
                        nickname=new_nickname,
                    )
                    last_created_id = new_guest.id

                messages.success(request, "Guest imported for the match.")
                # WRACAMY DO ADD MATCH Z ID GRACZA
                return redirect(f"{reverse('add_match')}?guest_id={last_created_id}")
            else:
                messages.error(request, "No players selected.")

    return render(request, 'import_players.html', {'code_form': code_form})


@login_required
def my_global_stats(request):
    """
    Sumuje statystyki ze wszystkich 'wcieleń' gracza (Oryginał + Klony u innych).
    """
    # Znajdź wszystkie instancje graczy powiązane z Twoim kontem User
    my_avatars = Player.objects.filter(user=request.user)

    # Agregacja danych
    stats = my_avatars.aggregate(
        total_wins=Sum('matches_won'),
        total_matches=Sum('matches_played'),
        global_max_break=Max('highest_break'),
        total_centuries=Sum('centuries_count'),
        total_points=Sum('total_career_points')
    )

    return render(request, 'global_stats.html', {
        'stats': stats,
        'avatars_count': my_avatars.count()  # Ile razy zostałeś sklonowany/użyty
    })


@login_required
def competition_ranking(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    # Opcjonalnie: Przeliczaj tylko jeśli turniej zakończony lub na żądanie.
    # Ale dla bezpieczeństwa przeliczmy zawsze przy wejściu (lub dodaj przycisk "Recalculate")
    calculate_competition_results(competition)

    results = CompetitionResult.objects.filter(competition=competition).order_by('rank', 'player__last_name')

    return render(request, 'competition_ranking.html', {
        'competition': competition,
        'results': results
    })


@login_required
def player_match_history(request, pk):
    player = get_object_or_404(Player, pk=pk)

    # 1. Pobieramy WSZYSTKIE mecze gracza
    matches_qs = Match.objects.filter(
        Q(player1=player) | Q(player2=player)
    ).order_by('-date', '-time')

    # --- FILTR H2H (Head-to-Head) ---
    opponent_id = request.GET.get('opponent')
    opponent = None
    stats = {}

    if opponent_id:
        opponent = get_object_or_404(Player, pk=opponent_id)
        # Filtrujemy tylko mecze z tym rywalem
        matches_qs = matches_qs.filter(Q(player1=opponent) | Q(player2=opponent))

        # Obliczamy szybkie statystyki H2H
        total = matches_qs.count()
        wins = 0
        for m in matches_qs:
            if m.winner == player:
                wins += 1

        stats = {
            'total': total,
            'wins': wins,
            'losses': total - wins,
            'win_rate': (wins / total * 100) if total > 0 else 0
        }

    # 2. Lista wszystkich rywali do listy rozwijanej (dla filtra)
    # Pobieramy ID wszystkich przeciwników z meczów gracza
    # To zapytanie może być trochę ciężkie przy tysiącach graczy, ale na razie OK
    p1_ids = Match.objects.filter(player2=player).values_list('player1', flat=True)
    p2_ids = Match.objects.filter(player1=player).values_list('player2', flat=True)
    all_opponent_ids = list(set(list(p1_ids) + list(p2_ids)))

    possible_opponents = Player.objects.filter(id__in=all_opponent_ids).order_by('last_name')

    # --- PAGINACJA (LOAD MORE) ---
    paginator = Paginator(matches_qs, 10)  # 10 meczów na "stronę" (kliknięcie)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 3. Jeśli to zapytanie AJAX (Load More), zwracamy tylko wiersze tabeli
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render_to_string('partials/match_rows.html', {
            'matches': page_obj,
            'player': player
        }, request=request)

        return JsonResponse({
            'html': html,
            'has_next': page_obj.has_next()
        })

    # 4. Standardowe wyświetlenie strony
    return render(request, 'player_match_history.html', {
        'player': player,
        'matches': page_obj,  # Pierwsza strona
        'possible_opponents': possible_opponents,
        'selected_opponent': opponent,
        'stats': stats
    })


@login_required
def equipment_list(request, player_id):
    player = get_object_or_404(Player, pk=player_id)

    # Podział na sprzęt AKTUALNY i HISTORYCZNY
    current_gear = player.equipment.filter(end_date__isnull=True).order_by('item_type')
    archive_gear = player.equipment.filter(end_date__isnull=False).order_by('-end_date')

    return render(request, 'equipment/list.html', {
        'player': player,
        'current_gear': current_gear,
        'archive_gear': archive_gear
    })


@login_required
def add_equipment(request, player_id):
    player = get_object_or_404(Player, pk=player_id)

    if request.method == 'POST':
        form = EquipmentForm(request.POST)
        if form.is_valid():
            new_eq = form.save(commit=False)
            new_eq.owner = request.user
            new_eq.player = player

            # --- LOGIKA AUTO-ARCHIWIZACJI ---
            # Jeśli nowy sprzęt jest AKTYWNY (brak end_date), zamknij stary tego samego typu
            if new_eq.end_date is None:
                old_active = Equipment.objects.filter(
                    player=player,
                    item_type=new_eq.item_type,
                    end_date__isnull=True
                )
                # Ustaw datę końca starego na datę startu nowego
                for old in old_active:
                    old.end_date = new_eq.start_date
                    old.save()
                    messages.info(request, f"Auto-archived previous {new_eq.get_item_type_display()}: {old.name}")
            # -------------------------------

            new_eq.save()
            messages.success(request, "New equipment added successfully!")
            return redirect('equipment_list', player_id=player.id)
    else:
        form = EquipmentForm()

    return render(request, 'equipment/form.html', {
        'form': form,
        'player': player,
        'action': 'Add'
    })


@login_required
def edit_equipment(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        form = EquipmentForm(request.POST, instance=equipment)
        if form.is_valid():
            form.save()
            messages.success(request, "Equipment updated.")
            return redirect('equipment_list', player_id=equipment.player.id)
    else:
        form = EquipmentForm(instance=equipment)

    return render(request, 'equipment/form.html', {
        'form': form,
        'player': equipment.player,
        'action': 'Edit'
    })


@login_required
def equipment_detail(request, pk):
    item = get_object_or_404(Equipment, pk=pk)
    return render(request, 'equipment/detail.html', {'item': item})


@login_required
def delete_equipment(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    player_id = equipment.player.id
    equipment.delete()
    messages.success(request, "Equipment deleted.")
    return redirect('equipment_list', player_id=player_id)


@login_required
def manage_photos(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)

    if request.method == 'POST':
        form = EquipmentPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.equipment = equipment
            photo.save()
            messages.success(request, "Photo added.")
            return redirect('manage_photos', pk=pk)
    else:
        form = EquipmentPhotoForm()

    return render(request, 'equipment/photos.html', {
        'equipment': equipment,
        'form': form
    })


@login_required
def profile_settings(request):
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)

        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('profile_settings')  # Przeładowanie strony (PRG pattern)

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'u_form': u_form,
        'p_form': p_form
    }
    return render(request, 'users/profile_settings.html', context)


@login_required
def export_data_excel(request):
    workbook = openpyxl.Workbook()

    # =========================================================
    # ARKUSZ 1: GENERAL STATS (Dashboard)
    # =========================================================
    ws_dash = workbook.active
    ws_dash.title = "General Stats"
    ws_dash.append(['Metric', 'Value'])

    # POPRAWKA 1: status='FINISHED' (Wielkie litery)
    total_matches = Match.objects.filter(owner=request.user, status='FINISHED').count()
    total_players = Player.objects.filter(owner=request.user).count()
    total_tournaments = Competition.objects.filter(owner=request.user).count()

    # --- POPRAWKA GLÓWNA: Club Highest Break ---
    # Zamiast szukać w Turniejach, szukamy w Graczach (uwzględnia sparingi/quick match)
    all_players = Player.objects.filter(owner=request.user)

    all_breaks_values = []
    for p in all_players:
        # Sprawdzamy czy highest_break to metoda czy pole (dla bezpieczeństwa)
        val = p.highest_break() if callable(getattr(p, 'highest_break', None)) else p.highest_break
        all_breaks_values.append(val or 0)

    # Wyciągamy max z listy wszystkich graczy
    global_max_break = max(all_breaks_values) if all_breaks_values else 0

    ws_dash.append(['Total Finished Matches', total_matches])
    ws_dash.append(['Total Players Database', total_players])
    ws_dash.append(['Total Tournaments', total_tournaments])
    ws_dash.append(['Club Highest Break', global_max_break])  # Teraz pokaże 56!

    # =========================================================
    # ARKUSZ 2: FULL PLAYER STATISTICS
    # =========================================================
    ws_stats = workbook.create_sheet(title="Full Player Statistics")

    headers = [
        '#', 'Player',
        'Matches', 'Won', 'Lost', '% Win',
        'Frames', 'Won', 'Lost', '% Win',
        'Fastest Frame', 'Longest Frame', 'Avg Frame',
        'Deciders Won', 'Deciders Played', '% Deciders',
        'Whitewash',
        'Streak (Matches)', 'Streak (Frames)',
        'Pot %', 'Safe %', 'AST',
        'Max Break', '100+', '50+',
        'Break Details'
    ]
    ws_stats.append(headers)

    players = Player.objects.filter(owner=request.user)

    for idx, p in enumerate(players, 1):
        match_win_pct = round((p.matches_won / p.matches_played * 100), 1) if p.matches_played > 0 else 0.0
        frame_win_pct = round((p.frames_won / p.frames_played * 100), 1) if p.frames_played > 0 else 0.0
        decider_pct = round((p.deciders_won / p.deciders_played * 100), 1) if p.deciders_played > 0 else 0.0

        # Metody czasowe (z zabezpieczeniem callable)
        fastest = p.formatted_fastest_frame() if callable(
            getattr(p, 'formatted_fastest_frame', None)) else p.formatted_fastest_frame
        longest = p.formatted_longest_frame() if callable(
            getattr(p, 'formatted_longest_frame', None)) else p.formatted_longest_frame
        avg_frame = p.formatted_avg_frame() if callable(
            getattr(p, 'formatted_avg_frame', None)) else p.formatted_avg_frame
        ast = p.formatted_avg_shot_time() if callable(
            getattr(p, 'formatted_avg_shot_time', None)) else p.formatted_avg_shot_time

        # Breaki (Słownik -> Tekst)
        stats_dict = p.career_break_stats() if callable(
            getattr(p, 'career_break_stats', None)) else p.career_break_stats
        break_details_str = ""
        if isinstance(stats_dict, dict):
            items = [f"{k}: {v}" for k, v in stats_dict.items() if v > 0]
            break_details_str = " | ".join(items)

        row = [
            idx, str(p),
            p.matches_played, p.matches_won, p.matches_lost, f"{match_win_pct}%",
            p.frames_played, p.frames_won, p.frames_lost, f"{frame_win_pct}%",
            str(fastest), str(longest), str(avg_frame),
            p.deciders_won, p.deciders_played, f"{decider_pct}%",
            p.whitewashes_count,
            p.consecutive_matches_won, p.consecutive_frames_won,
            f"{p.global_pot_success:.0f}%" if p.global_pot_success else "-",
            f"{p.global_safety_success:.0f}%" if p.global_safety_success else "-",
            str(ast),
            p.max_breaks_count, p.centuries_count, p.fifties_count,
            break_details_str
        ]
        ws_stats.append(row)

    # =========================================================
    # ARKUSZ 3: TOURNAMENTS ARCHIVE
    # =========================================================
    ws_tour = workbook.create_sheet(title="Tournaments Archive")
    ws_tour.append(['Name', 'Start Date', 'Variant', 'Status', 'Winner', 'Max Break', 'Max Break Player'])

    tournaments = Competition.objects.filter(owner=request.user).order_by('-start_date')
    for t in tournaments:
        winner_name = str(t.winner) if t.winner else "-"
        max_break_val = t.highest_break_points if t.highest_break_points > 0 else "-"
        max_break_player = str(t.highest_break_player) if t.highest_break_player else "-"

        ws_tour.append([
            t.name, t.start_date.strftime('%Y-%m-%d'), t.get_game_variant_display(),
            t.get_status_display(), winner_name, max_break_val, max_break_player
        ])

    # =========================================================
    # ARKUSZ 4: REFEREES
    # =========================================================
    ws_ref = workbook.create_sheet(title="Referees")
    ws_ref.append(['Name', 'License', 'Matches Officiated', 'Last Match Date'])

    referees = Referee.objects.filter(owner=request.user)
    for r in referees:
        # status='FINISHED'
        ref_matches = Match.objects.filter(owner=request.user, status='FINISHED', referees=r).order_by('-date')
        count = ref_matches.count()
        last_match = ref_matches.first()
        last_date = last_match.date.strftime('%Y-%m-%d') if last_match and last_match.date else "-"
        ws_ref.append([str(r), r.license_number, count, last_date])

    # =========================================================
    # ARKUSZ 5: MATCH HISTORY
    # =========================================================
    ws_matches = workbook.create_sheet(title="Match History")
    ws_matches.append(['Date', 'Player 1', 'Score', 'Player 2', 'Winner'])

    # status='FINISHED'
    matches = Match.objects.filter(owner=request.user, status='FINISHED').order_by('-date')

    for m in matches:
        date_str = m.date.strftime('%Y-%m-%d') if m.date else ""
        score_str = f"{m.final_score_player1} - {m.final_score_player2}"
        ws_matches.append([date_str, str(m.player1), score_str, str(m.player2), str(m.winner)])

    # =========================================================
    # ZAPIS
    # =========================================================
    now_str = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    filename = f"snooker_report_{now_str}.xlsx"

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    workbook.save(response)
    return response


@user_passes_test(lambda u: u.is_superuser)  # Tylko dla Superusera!
def admin_backup_json(request):
    # Tworzymy bufor w pamięci (taki wirtualny plik)
    output = StringIO()

    # Wywołujemy komendę dumpdata (zrzut bazy)
    # exclude: pomijamy sesje i logi admina, bo to śmieci, które tylko zajmują miejsce
    # indent: ładne wcięcia w pliku (czytelność)
    call_command(
        'dumpdata',
        exclude=['contenttypes', 'sessions', 'admin.logentry'],
        indent=2,
        stdout=output
    )

    # Przewijamy bufor na początek, żeby móc go odczytać
    output.seek(0)

    # Przygotowujemy plik do pobrania
    now_str = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    filename = f"FULL_DB_BACKUP_{now_str}.json"

    response = HttpResponse(output.read(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename={filename}'

    return response