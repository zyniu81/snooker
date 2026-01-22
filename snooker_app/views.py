from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView
from django.contrib import messages
from django.db.models import Count, Sum, F, Case, When, IntegerField, Q
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.forms import modelformset_factory
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from datetime import timedelta
from django.utils.safestring import mark_safe
from django.urls import reverse

import os
from openai import OpenAI
import sys
import json

from snooker_app.forms import (PlayerForm, PlayerEditForm, RefereeForm, VenueForm,
                               MatchForm, CompetitionForm, AddMatchesToCompetitionForm,
                               GroupStageForm, SignUpForm, KnockoutStageForm, MassMatchEditForm, ExtraMatchForm)
from snooker_app.models import (Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage,
                                MatchPlayer, Frame)


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
    # Widzimy SWOJE + PUBLICZNE
    players = Player.objects.filter(Q(owner=request.user) | Q(is_public=True))
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
        # ZMIANA: Dodano request.FILES
        form = PlayerEditForm(request.POST, request.FILES, instance=player, request=request)

        was_temporary = player.is_temporary

        if form.is_valid():
            saved_player = form.save(commit=False)
            is_now_temporary = saved_player.is_temporary
            saved_player.save()

            # --- Logika konwersji (Tymczasowy -> Stały) ---
            if was_temporary and not is_now_temporary:
                matches_qs = Match.objects.filter(players=saved_player, is_temporary=True)

                opponents_list = list(Player.objects.filter(
                    match__in=matches_qs,
                    is_temporary=True
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

            # --- Aktualizacja nazw w meczach ---
            player_matches = Match.objects.filter(players=saved_player)
            for m in player_matches:
                m.save()

            # Powrót do szczegółów gracza po edycji jest zazwyczaj lepszy niż do listy
            return redirect('player_detail', pk=player.pk)
    else:
        form = PlayerEditForm(instance=player, request=request)

    return render(request, 'player_edit.html', {'form': form, 'player': player})


@login_required
def player_detail(request, pk):
    # Możemy podglądać publiczne lub swoje
    player = get_object_or_404(Player, pk=pk)

    if not (player.is_public or player.owner == request.user):
        raise PermissionDenied("You do not have access to this player.")

    # --- POBIERANIE HISTORII MECZÓW ---
    # Szukamy meczów, w których ten gracz jest na liście 'players'
    # Sortujemy: najpierw data malejąco (-date), potem czas malejąco (-time)
    # [:5] ogranicza listę do 5 ostatnich wyników (żeby nie zapchać profilu)
    recent_matches = Match.objects.filter(players=player).order_by('-date', '-time')[:5]
    # -------------------------------------------

    return render(request, 'player_detail.html', {
        'player': player,
        'matches': recent_matches  # Przekazujemy mecze do szablonu
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
    # Sortujemy: Najpierw data (od najnowszej), potem godzina (od najnowszej)
    matches = Match.objects.filter(owner=request.user).order_by('-date', '-time')
    return render(request, 'match_list.html', {'matches': matches})


@login_required
def add_match(request):
    if request.method == 'POST':
        form = MatchForm(request.POST, request=request)
        if form.is_valid():
            match = form.save(commit=False)
            match.owner = request.user
            match.save()
            form.save_m2m()  # Zapisuje graczy w relacji ManyToMany (ale bez pozycji)

            # 1. Sprawdzamy, czy formularz miał stworzyć tymczasowych
            # Jeśli tak, to funkcja wewnątrz formularza zajmie się tworzeniem MatchPlayer
            form.create_temp_players_if_needed(match)

            # 2. --- NOWOŚĆ: OBSŁUGA ZWYKŁYCH GRACZY ---
            # Jeśli NIE tworzyliśmy tymczasowych, to musimy "posadzić"
            # wybranych z listy graczy na pozycjach 1 i 2.
            # Sprawdzamy czy MatchPlayer są już utworzeni (żeby nie dublować tymczasowych)
            if not MatchPlayer.objects.filter(match=match).exists():
                players = list(match.players.all())

                # Jeśli wybrano graczy, przypisujemy im pozycje
                if len(players) >= 1:
                    MatchPlayer.objects.create(match=match, player=players[0], position=1)

                if len(players) >= 2:
                    MatchPlayer.objects.create(match=match, player=players[1], position=2)

            return redirect('match_detail', pk=match.pk)
    else:
        form = MatchForm(request=request)

    return render(request, 'add_match.html', {'form': form})


def match_detail(request, pk):
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
            raise PermissionDenied
        else:
            return redirect(f'{reverse("login")}?next={request.path}')
    # ----------------------

    game_status = match.get_game_status()

    # Pobieramy graczy i framy
    match_players = MatchPlayer.objects.filter(match=match).order_by('position')
    frames = Frame.objects.filter(match_player__match=match).order_by('frame_number')

    # Inicjalizacja zmiennych
    p1_data = None
    p2_data = None
    p1_wins = 0
    p2_wins = 0

    if match_players.count() >= 2:
        p1_mp = match_players[0]  # Obiekt MatchPlayer dla gracza 1
        p2_mp = match_players[1]  # Obiekt MatchPlayer dla gracza 2

        p1_wins = frames.filter(winner=p1_mp.player).count()
        p2_wins = frames.filter(winner=p2_mp.player).count()

        # Przygotowujemy dane do wyświetlenia w podsumowaniu meczu
        # (Model MatchPlayer ma już wiele z tych pól, ale safety musimy policzyć jeśli nie ma w modelu)
        # Zakładam, że AST (avg_shot_time) masz w modelu jako DurationField

        p1_data = {
            'name': str(p1_mp.player),
            'obj': p1_mp,
            'wins': p1_wins
        }
        p2_data = {
            'name': str(p2_mp.player),
            'obj': p2_mp,
            'wins': p2_wins
        }

    return render(request, 'match_detail.html', {
        'match': match,
        'is_finished': game_status['is_finished'],
        'winner': game_status['winner'],
        'frames': frames,
        'p1': p1_data,  # Przekazujemy słowniki z danymi
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


def start_game(request, pk):
    # Pobieramy mecz
    match = get_object_or_404(Match, pk=pk)

    # --- LOGIKA DOSTĘPU ---
    has_access = False

    # 1. Mecz bez właściciela (Tymczasowy) -> WSTĘP WOLNY
    if match.owner is None:
        has_access = True
    # 2. Mecz publiczny -> WSTĘP WOLNY
    elif match.is_public:
        has_access = True
    # 3. Mecz prywatny -> TYLKO WŁAŚCICIEL
    elif request.user.is_authenticated and match.owner == request.user:
        has_access = True

    # Jeśli żaden warunek nie jest spełniony -> BLOKADA
    if not has_access:
        if request.user.is_authenticated:
            # Zalogowany, ale próbuje wejść na cudzy prywatny mecz
            raise PermissionDenied("Brak dostępu do meczu.")
        else:
            # Niezalogowany próbuje wejść na prywatny mecz -> Logowanie
            return redirect(f'{reverse("login")}?next={request.path}')
    # ----------------------

    status = match.get_game_status()
    if status['is_finished']:
        messages.warning(request, "Ten mecz jest już zakończony!")
        return redirect('match_detail', pk=pk)

    match_players = MatchPlayer.objects.filter(match=match).order_by('position')

    # --- AUTO-NAPRAWA (Twoja logika) ---
    if not match_players.exists() and match.players.exists():
        print(f"⚠️ Naprawa MatchPlayer dla meczu {pk}...")
        for index, player in enumerate(match.players.all()):
            MatchPlayer.objects.create(match=match, player=player, position=index + 1)
        match_players = MatchPlayer.objects.filter(match=match).order_by('position')

    players_list = [mp.player for mp in match_players]

    # --- LOGIKA FRAMÓW ---
    existing_frames = Frame.objects.filter(match_player__in=match_players)
    active_frame_object = None

    if not existing_frames.exists() and match_players.exists():
        active_frame_object = Frame.objects.create(
            match_player=match_players.first(),
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
        'players': player_results,
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


@login_required
def competition_detail(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    if not (competition.owner == request.user or competition.is_public):
        raise PermissionDenied

    group_stages = competition.groupstage_stages.all().prefetch_related('matches')
    knockout_stages = competition.knockoutstage_stages.all().prefetch_related('matches')

    group_data = []
    for group_stage in group_stages:
        matches = group_stage.matches.all()
        players = Player.objects.filter(matchplayer__match__in=matches).distinct()

        player_stats = []
        for player in players:
            stats = MatchPlayer.objects.filter(
                match__in=matches,
                player=player).aggregate(
                played=Count('match', distinct=True),
                won=Sum(Case(
                    When(points_scored__gt=F('points_scored'), then=1),
                    default=0, output_field=IntegerField())),
                drawn=Sum(Case(
                    When(points_scored=F('points_scored'), then=1),
                    default=0, output_field=IntegerField())),
                frames_won=Sum('points_scored'),
                frames_lost=Sum(F('points_scored')) - Sum('points_scored')
            )
            stats['match_points'] = (stats['won'] or 0) * 3 + (stats['drawn'] or 0)
            player_stats.append(stats)

        player_stats.sort(key=lambda x: (x['match_points'], x['frames_won'] - x['frames_lost']), reverse=True)
        group_data.append({
            'stage': group_stage,
            'matches': matches,
            'player_stats': player_stats
        })

    knockout_data = []
    for knockout_stage in knockout_stages:
        matches = knockout_stage.matches.all().order_by('group_name')
        knockout_data.append({
            'stage': knockout_stage,
            'matches': matches
        })

    return render(request, 'competition_detail.html', {
        'competition': competition,
        'group_data': group_data,
        'knockout_data': knockout_data,
        'add_players_url': reverse('add_players_to_competition', kwargs={'pk': competition.pk})
    })


class CompetitionDeleteView(DeleteView):
    model = Competition
    template_name = 'delete_competition.html'
    success_url = reverse_lazy('competition_list')

    def get_queryset(self):
        return Competition.objects.filter(owner=self.request.user)


@login_required
def add_matches_to_competition(request, competition_id):
    """
    Tworzy pojedynczy 'Extra Match' (np. sparing, o 3 miejsce) w ramach turnieju.
    Automatycznie przypisuje go do etapu 'Extras' (KnockoutStage), tworząc go w razie potrzeby.
    """
    competition = get_object_or_404(Competition, pk=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        form = ExtraMatchForm(request.POST, competition=competition)
        if form.is_valid():
            # 1. Znajdź lub stwórz etap "Extras" (żeby mecz miał właściciela)
            # Używamy KnockoutStage, bo jest prostszy w strukturze
            extra_stage, created = KnockoutStage.objects.get_or_create(
                competition=competition,
                name="Extras",
                defaults={
                    'order': 999, # Zawsze na końcu
                    'num_rounds': 1,
                    'frames_per_match': form.cleaned_data['number_of_frames'],
                    'has_third_place_match': False
                }
            )

            # 2. Utwórz mecz
            match = form.save(commit=False)
            match.owner = request.user
            # WAŻNE: Podpinamy pod etap Extras
            match.knockout_stage = extra_stage
            # Oznaczamy jako knockout (dla porządku w nazwie)
            match.knockout_name = "Extra Match"
            match.save()

            # 3. Przypisz graczy
            p1 = form.cleaned_data['player1']
            p2 = form.cleaned_data['player2']
            match.players.add(p1, p2)
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
    # Czyścimy sesję
    if 'temp_match_id' in request.session:
        del request.session['temp_match_id']

    if request.method == 'POST':
        form = MatchForm(request.POST, request=request)
        if form.is_valid():
            match = form.save(commit=False)

            # Ustawienia zależne od logowania
            if request.user.is_authenticated:
                match.owner = request.user
                match.is_public = False
            else:
                match.owner = None
                match.is_public = True

            match.is_temporary = True
            match.save()

            if not request.user.is_authenticated:
                request.session['temp_match_id'] = match.id

            # --- LOGIKA GRACZY ---
            create_temp = form.cleaned_data.get('create_temporary_players')

            if not request.user.is_authenticated or create_temp:
                prefix = "Temporary Player"
                p1 = Player.objects.create(first_name=f"{prefix} 1", is_temporary=True, owner=match.owner)
                p2 = Player.objects.create(first_name=f"{prefix} 2", is_temporary=True, owner=match.owner)

                # 1. Dodajemy do relacji ogólnej (dla pewności)
                match.players.add(p1, p2)

                # 2. --- POPRAWKA: TWORZYMY MATCHPLAYER Z POZYCJĄ ---
                # To gwarantuje, że Player 1 będzie po lewej (Position 1)
                MatchPlayer.objects.create(match=match, player=p1, position=1)
                MatchPlayer.objects.create(match=match, player=p2, position=2)
                # ---------------------------------------------------

                match.temp_player1 = p1
                match.temp_player2 = p2
                match.save()

            else:
                # Jeśli wybrano istniejących graczy
                form.save_m2m()

            return redirect('match_detail', pk=match.pk)
    else:
        form = MatchForm(request=request)

    return render(request, 'create_temporary_match.html', {'form': form})


@login_required
def create_group_stage(request, competition_id):
    competition = get_object_or_404(Competition, id=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    # (Tu była blokada if count == 0 - już jej nie ma)

    # Pobieramy graczy (przekazujemy request.user, żeby widzieć całą bazę graczy)
    winners, eliminated, others = get_sorted_players_for_stage(competition, request.user)

    if request.method == 'POST':
        form = GroupStageForm(
            request.POST,
            competition=competition,
            winners=winners,
            eliminated=eliminated,
            others=others
        )
        if form.is_valid():
            group_stage = form.save(commit=False)
            group_stage.competition = competition
            group_stage.save()

            # Pobieramy wybranych graczy z formularza
            selected_players = form.cleaned_data.get('players')

            # --- NOWOŚĆ: Automatyczne dopisanie graczy do turnieju ---
            # Jeśli wybrałeś kogoś, kto jeszcze nie był w competition.players, teraz tam trafi.
            if selected_players:
                competition.players.add(*selected_players)
            # ---------------------------------------------------------

            group_stage.create_groups_and_matches(
                default_frames=form.cleaned_data['default_frames'],
                selected_players=selected_players
            )

            messages.success(request, f"Group Stage '{group_stage.name}' created successfully.")
            return redirect('competition_detail', pk=competition.id)
    else:
        form = GroupStageForm(
            competition=competition,
            winners=winners,
            eliminated=eliminated,
            others=others
        )

    return render(request, 'create_group_stage.html', {'form': form, 'competition': competition})


@login_required
def create_knockout_stage(request, competition_id):
    competition = get_object_or_404(Competition, id=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    # (Tu była blokada - usunięta)

    winners, eliminated, others = get_sorted_players_for_stage(competition, request.user)

    if request.method == 'POST':
        # Upewnij się, że tu jest KnockoutStageForm (nie GroupStageForm!)
        form = KnockoutStageForm(
            request.POST,
            competition=competition,
            winners=winners,
            eliminated=eliminated,
            others=others
        )
        if form.is_valid():
            knockout_stage = form.save(commit=False)
            knockout_stage.competition = competition
            knockout_stage.save()

            selected_players = form.cleaned_data.get('players')

            # --- NOWOŚĆ: Automatyczne dopisanie graczy do turnieju ---
            if selected_players:
                competition.players.add(*selected_players)
            # ---------------------------------------------------------

            knockout_stage.create_knockout_matches(
                selected_players=selected_players
            )

            messages.success(request, f"Knockout Stage '{knockout_stage.name}' created successfully.")
            return redirect('competition_detail', pk=competition.id)
    else:
        form = KnockoutStageForm(
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

                        # Przejmujemy też graczy z tego meczu (jeśli też są sierotami)
                        for player in match.players.all():
                            if player.owner is None:
                                player.owner = user
                                player.is_temporary = False
                                player.save()

                        messages.success(request, "Registration successful! Your temporary match has been saved to your account.")

                        # Czyścimy sesję, żeby nie przypisywać tego meczu w nieskończoność
                        del request.session['temp_match_id']

                        # Przekierowujemy od razu do tego meczu, żeby gracz mógł grać dalej
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
        players = Player.objects.filter(id__in=player_ids)
        competition.players.add(*players)
        return redirect('competition_detail', pk=competition.id)
    else:
        # Pokaż tylko moich + publicznych graczy, którzy nie są w tym turnieju
        available_players = Player.objects.filter(
            Q(owner=request.user) | Q(is_public=True)
        ).exclude(competitions=competition)

        return render(request, 'add_players_to_competition.html', {
            'competition': competition,
            'available_players': available_players
        })


@login_required
def achievement_list(request):
    # Sortujemy np. po najwyższym breaku malejąco
    players = Player.objects.filter(
        Q(owner=request.user) | Q(is_public=True)
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

        # Opcjonalne: kolor bili do statystyk (jeśli JS to wysyła)
        ball_color = data.get('ball_color')

        if match_id is None or player_id is None or points is None:
            return JsonResponse({'status': 'error', 'message': 'Missing data fields'})

        # KROK 1: Próbujemy znaleźć Frame'a
        # Najpierw szukamy frame'a dla tego meczu
        try:
            # Szukamy ostatniego frame'a w tym meczu (niezależnie od gracza)
            frame = Frame.objects.filter(match_player__match_id=match_id).latest('frame_number')
        except Frame.DoesNotExist:
            # Fallback: Czasami relacja jest inna, spróbujmy znaleźć po prostu ostatni frame powiązany z meczem
            # (To zależy od Twojej dokładnej struktury Frame <-> Match)
            return JsonResponse({'status': 'error', 'message': 'No active frame found for this match'})

        # KROK 2: Ustalamy, KTÓRY to gracz (1 czy 2?)

        # Podejście A: PROFESJONALNE (Baza danych)
        # Sprawdzamy, czy ten gracz jest przypisany do meczu jako poz. 1 czy 2
        match_player = MatchPlayer.objects.filter(match_id=match_id, player_id=player_id).first()

        target_position = None

        if match_player:
            # Jeśli znaleźliśmy go w bazie, ufamy bazie
            target_position = match_player.position
        else:
            # Podejście B: AWARYJNE / TYMCZASOWE (Stara logika)
            # Jeśli nie ma go w bazie MatchPlayer (np. Temporary Match),
            # zakładamy, że JS wysłał nam po prostu '1' lub '2' jako ID.
            if str(player_id) == '1':
                target_position = 1
            elif str(player_id) == '2':
                target_position = 2

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
            # Jeśli ani baza, ani ID nie pasują
            return JsonResponse({'status': 'error', 'message': f'Cannot identify player position for ID {player_id}'})

        frame.save()
        return JsonResponse({'status': 'success'})

    except Exception as e:
        print(f"Błąd w update_game_data: {e}")
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
        # 1. Sprawdzamy czy mecz istnieje
        match = get_object_or_404(Match, pk=match_id)

        # 2. Sprawdzamy uprawnienia użytkownika (taka sama logika jak w start_game)
        has_access = False

        # A) Mecz tymczasowy (owner=None) -> Każdy może zapisać (zazwyczaj z tej samej sesji)
        if match.owner is None:
            has_access = True
        # B) Mecz publiczny -> Każdy może
        elif match.is_public:
            has_access = True
        # C) Mecz prywatny -> Tylko właściciel
        elif request.user.is_authenticated and match.owner == request.user:
            has_access = True

        if not has_access:
            return JsonResponse({'status': 'error', 'message': 'Permission Denied: You cannot modify this match.'},
                                status=403)

        # 3. Sprawdzamy czy mecz nie jest już zakończony
        # Pobieramy status z modelu
        game_status = match.get_game_status()
        if game_status['is_finished']:
            return JsonResponse({'status': 'error', 'message': 'Match is already finished!'}, status=400)
        # ---------------------------

        winner_id = data.get('winner_id')
        p1_score = data.get('p1_score')
        p2_score = data.get('p2_score')
        # Pobieramy czas (w sekundach), domyślnie 0
        duration_seconds = data.get('duration', 0)

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

        # Odbieramy ilość prób odstawnych
        p1_safeties = data.get('p1_safeties', 0)
        p2_safeties = data.get('p2_safeties', 0)

        # Odbieramy ilość UDANYCH odstawnych
        p1_safe_succ = data.get('p1_safe_success_count', 0)
        p2_safe_succ = data.get('p2_safe_success_count', 0)

        p1_breaks_list = data.get('p1_breaks', [])
        p2_breaks_list = data.get('p2_breaks', [])

        if not all([match_id, winner_id, p1_score is not None, p2_score is not None]):
            return JsonResponse({'status': 'error', 'message': 'Missing data fields'})

        winner = get_object_or_404(Player, pk=winner_id)

        # 1. Próbujemy pobrać graczy z tabeli łączącej
        match_players = MatchPlayer.objects.filter(match=match).order_by('position')

        # --- SEKCJA AUTO-NAPRAWY BRAKUJĄCYCH GRACZY (Dla Meczów Tymczasowych) ---
        if not match_players.exists():
            print(f"Brak MatchPlayer dla meczu {match.id}. Próba naprawy z pól temp...")

            p1_temp = match.temp_player1
            p2_temp = match.temp_player2

            if not p1_temp and match.players.exists():
                all_players = list(match.players.all())
                if len(all_players) >= 2:
                    p1_temp = all_players[0]
                    p2_temp = all_players[1]

            if p1_temp and p2_temp:
                MatchPlayer.objects.create(match=match, player=p1_temp, position=1)
                MatchPlayer.objects.create(match=match, player=p2_temp, position=2)
                match_players = MatchPlayer.objects.filter(match=match).order_by('position')
                print("Naprawiono! Utworzono obiekty MatchPlayer.")
            else:
                return JsonResponse({'status': 'error',
                                     'message': 'CRITICAL: No players found in MatchPlayer table or Match temp fields!'})
        # -------------------------------------------------------------------------

        # 2. Szukamy ostatniego frama
        last_frame = Frame.objects.filter(match_player__in=match_players).order_by('-frame_number').first()

        # --- SEKCJA RATUNKOWA FRAMA: Jeśli nie ma frama, tworzymy go TERAZ ---
        if not last_frame:
            print("Brak aktywnego frama - tworzenie awaryjne Frame 1")
            last_frame = Frame.objects.create(
                match_player=match_players.first(),
                frame_number=1,
                points_scored_player1=0,
                points_scored_player2=0,
                active_player=match_players.first().player
            )
        # ---------------------------------------------------------------

        # --- OBLICZANIE SKUTECZNOŚCI (Pot Success) ---
        # Wzór: Wbite / (Wbite + Pudła). Ignorujemy Safety!

        p1_attempts = p1_pots + p1_misses
        p1_success_rate = 0.0
        if p1_attempts > 0:
            p1_success_rate = round((p1_pots / p1_attempts) * 100, 2)

        p2_attempts = p2_pots + p2_misses
        p2_success_rate = 0.0
        if p2_attempts > 0:
            p2_success_rate = round((p2_pots / p2_attempts) * 100, 2)
        # ---------------------------------------------

        # 3. Zapisz wyniki
        last_frame.points_scored_player1 = p1_score
        last_frame.points_scored_player2 = p2_score
        last_frame.winner = winner

        last_frame.player1_fouls = p1_fouls
        last_frame.player2_fouls = p2_fouls
        last_frame.foul_points_player1 = p1_foul_pts
        last_frame.foul_points_player2 = p2_foul_pts

        # --- ZAPIS SKUTECZNOŚCI I STRZAŁÓW ---
        # Total shots = (Pots + Misses + Safety) -> Tak to wyliczył JS
        last_frame.total_shots_player1 = p1_shots
        last_frame.total_shots_player2 = p2_shots

        last_frame.misses_player1 = p1_misses
        last_frame.misses_player2 = p2_misses

        last_frame.pot_success_percentage_player1 = p1_success_rate
        last_frame.pot_success_percentage_player2 = p2_success_rate

        # --- ZAPIS ODSTAWNYCH (SAFETY) ---
        # Tu przypisujemy to, co odebraliśmy w punkcie 1
        last_frame.safety_shot_player1 = p1_safeties
        last_frame.safety_shot_player2 = p2_safeties

        last_frame.successful_safety_shots_player1 = p1_safe_succ
        last_frame.successful_safety_shots_player2 = p2_safe_succ
        # ---------------------------------

        # --- ZAPIS CZASU GRY ---
        if duration_seconds > 0:
            last_frame.time_duration = timedelta(seconds=duration_seconds)
        # -----------------------

        if last_frame.break_points_player1:
            last_frame.max_break_player1 = max(last_frame.break_points_player1)
        if last_frame.break_points_player2:
            last_frame.max_break_player2 = max(last_frame.break_points_player2)

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

        # 4. Sprawdź czy mecz się skończył (korzystając z nowej logiki w modelu)
        match.update_status_from_frames()
        game_status = match.get_game_status()
        match_over = game_status['is_finished']
        match_winner_obj = game_status['winner']

        # Ustal co wyświetlić w alercie (Imię zwycięzcy lub Remis)
        winner_name = "Unknown"
        if match_over:
            if match_winner_obj:
                winner_name = str(match_winner_obj)
            else:
                winner_name = "Draw"  # To wyświetli się w alercie: "Winner: Draw"

        # Jeśli mecz się NIE skończył, tworzymy nowy frame
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

    # Sprawdzenie uprawnień
    if competition.owner != request.user:
        raise PermissionDenied

    # Pobieramy mecze turnieju (zarówno grupowe jak i pucharowe)
    matches = Match.objects.filter(
        Q(group_stage__competition=competition) |
        Q(knockout_stage__competition=competition)
    ).order_by('date', 'time', 'id')

    # Tworzymy klasę Formsetu
    MatchFormSet = modelformset_factory(Match, form=MassMatchEditForm, extra=0)

    if request.method == 'POST':
        formset = MatchFormSet(request.POST, queryset=matches)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Matches updated successfully.")
            return redirect('competition_detail', pk=competition.id)
    else:
        formset = MatchFormSet(queryset=matches)

    # --- FILTROWANIE SĘDZIÓW ---
    # To jest ważne: Formset domyślnie pokaże wszystkich sędziów z bazy.
    # Musimy ręcznie przefiltrować pole 'referees' w każdym formularzu,
    # żeby pokazywało tylko sędziów użytkownika + publicznych.

    my_referees = Referee.objects.filter(Q(owner=request.user) | Q(is_public=True))

    for form in formset:
        form.fields['referees'].queryset = my_referees

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

    # 2. BAZA GRACZY: Pobieramy WSZYSTKICH Twoich graczy (bez tymczasowych)
    # To jest ta główna zmiana - patrzymy szeroko, na całą bazę.
    all_user_players = set(Player.objects.filter(owner=user, is_temporary=False))

    # Jeśli to pierwszy etap (brak historii etapów), wszyscy Twoi gracze trafiają do 'others'
    if not all_stages:
        return [], [], list(all_user_players)

    # 3. Pobierz ostatni etap
    last_stage = all_stages[-1]

    # Pobierz mecze (zabezpieczenie, gdyby etap nie miał meczów)
    if hasattr(last_stage, 'matches'):
        matches = last_stage.matches.filter(status='FINISHED')
    else:
        matches = []

    # 4. Sortowanie uczestników ostatniego etapu
    winners = set()
    participants = set()  # Wszyscy, którzy grali w ostatnim etapie

    for match in matches:
        for p in match.players.all():
            participants.add(p)
        if match.winner:
            winners.add(match.winner)

    # Przegrani to: Uczestnicy ostatniego etapu MINUS Zwycięzcy
    eliminated = participants - winners

    # Inni to: Wszyscy Twoi gracze z bazy MINUS ci, którzy brali udział w ostatnim etapie
    # (Tutaj wpadną też gracze, których w turnieju jeszcze nie było - Wildcards)
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
    return redirect('competition_detail', pk=competition.id)


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
            # (Żeby mógł ich potem edytować/widzieć)
            for player in match.players.all():
                if player.is_temporary and player.owner is None:
                    player.owner = user
                    player.save()

            del request.session['temp_match_id']

            print(f"Success! Match {match.id} has been assigned to the user {user}.")

        except Match.DoesNotExist:
            pass