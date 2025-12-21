from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView
from django.contrib import messages
from django.db.models import Count, Sum, F, Case, When, IntegerField
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from datetime import timedelta

import os
from openai import OpenAI
import sys
import json

from snooker_app.forms import (PlayerForm, PlayerEditForm, RefereeForm, VenueForm,
                               MatchForm, CompetitionForm, AddMatchesToCompetitionForm,
                               GroupStageForm, SignUpForm, KnockoutStageForm)
from snooker_app.models import (Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage,
                                MatchPlayer, Achievement, Frame)

# Create your views here.


def player_list(request):
    players = Player.objects.all()
    return render(request, 'player_list.html', {'players': players})


def add_player(request):
    if request.method == 'POST':
        form = PlayerForm(request.POST)
        if form.is_valid():
            player = form.save()
            return redirect('player_list')
    else:
        form = PlayerForm()

    return render(request, 'add_player.html', {'form': form})


def player_detail(request, pk):
    player = get_object_or_404(Player, pk=pk)
    return render(request, 'player_detail.html', {'player': player})


def player_edit(request, pk):
    player = get_object_or_404(Player, pk=pk)
    if request.method == 'POST':
        form = PlayerEditForm(request.POST, instance=player)
        if form.is_valid():
            form.save()
            return redirect('player_list')
    else:
        form = PlayerEditForm(instance=player)

    return render(request, 'player_edit.html', {'form': form, 'player': player})


class PlayerDeleteView(DeleteView):
    model = Player
    template_name = 'player_delete.html'
    success_url = reverse_lazy('player_list')

    def get_object(self, queryset=None):
        return get_object_or_404(Player, pk=self.kwargs['pk'])


def referee_list(request):
    referees = Referee.objects.all()
    return render(request, 'referee_list.html', {'referees': referees})


def add_referee(request):
    if request.method == 'POST':
        form = RefereeForm(request.POST)
        if form.is_valid():
            referee = form.save()
            return redirect('referee_list')
    else:
        form = RefereeForm()

    return render(request, 'add_referee.html', {'form': form})


def edit_referee(request, pk):
    referee = get_object_or_404(Referee, pk=pk)
    if request.method == 'POST':
        form = RefereeForm(request.POST, instance=referee)
        if form.is_valid():
            form.save()
            return redirect('referee_list')
    else:
        form = RefereeForm(instance=referee)

    return render(request, 'edit_referee.html', {'form': form, 'referee': referee})


class RefereeDeleteView(DeleteView):
    model = Referee
    template_name = 'delete_referee.html'
    success_url = reverse_lazy('referee_list')

    def get_object(self, queryset=None):
        return get_object_or_404(Referee, pk=self.kwargs['pk'])


def delete_referee(request, pk):
    referee = get_object_or_404(Referee, pk=pk)
    if request.method == 'POST':
        referee.delete()
        return redirect('referee_list')

    return render(request, 'delete_referee.html', {'referee': referee})


def referee_detail(request, pk):
    referee = get_object_or_404(Referee, pk=pk)
    return render(request, 'referee_detail.html', {'referee': referee})


def venue_list(request):
    venues = Venue.objects.all()
    return render(request, 'venue_list.html', {'venues': venues})


def add_venue(request):
    if request.method == 'POST':
        form = VenueForm(request.POST)
        if form.is_valid():
            venue = form.save()
            return redirect('venue_list')
    else:
        form = VenueForm()

    return render(request, 'add_venue.html', {'form': form})


def edit_venue(request, pk):
    venue = get_object_or_404(Venue, pk=pk)
    form = VenueForm(request.POST, instance=venue)
    if form.is_valid():
        form.save()
        return redirect('venue_list')
    else:
        form = VenueForm(instance=venue)

    return render(request, 'edit_venue.html', {'form': form, 'venue': venue})


class VenueDeleteView(DeleteView):
    model = Venue
    template_name = 'delete_venue.html'
    success_url = reverse_lazy('venue_list')


# def delete_venue(request, pk):
#     venue = get_object_or_404(Venue, pk=pk)
#     if request.method == 'POST':
#         venue.delete()
#         return redirect('venue_list')
#
#     return render(request, 'delete_venue.html', {'venue': venue})


def venue_detail(request, pk):
    venue = get_object_or_404(Venue, pk=pk)
    return render(request, 'venue_detail.html', {'venue': venue})


def match_list(request):
    matches = Match.objects.all()
    return render(request, 'match_list.html', {'matches': matches})


def add_match(request):
    form = None

    if request.method == 'POST':
        form = MatchForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('match_list')
    else:
        form = MatchForm()

    return render(request, 'add_match.html', {'form': form})


def match_detail(request, pk):
    match = get_object_or_404(Match, pk=pk)
    return render(request, 'match_detail.html', {'match': match})


def edit_match(request, pk):
    match = get_object_or_404(Match, pk=pk)
    if request.method == 'POST':
        form = MatchForm(request.POST, instance=match)
        if form.is_valid():
            form.save()
            return redirect('match_detail', pk=pk)

    else:
        form = MatchForm(instance=match)

    return render(request, 'edit_match.html', {'form': form, 'match': match})


class MatchDeleteView(DeleteView):
    model = Match
    template_name = 'delete_match.html'
    success_url = reverse_lazy('match_list')

    def get_object(self, queryset=None):
        return get_object_or_404(Match, pk=self.kwargs['pk'])


def start_game(request, pk):
    match = get_object_or_404(Match, pk=pk)

    # 1. Pobieramy graczy (To co naprawiliśmy wcześniej)
    match_players = MatchPlayer.objects.filter(match=match).order_by('position')

    players_list = [mp.player for mp in match_players]
    if not players_list:
        players_list = match.players.all()

    # --- NOWOŚĆ: AUTO-CREATE FRAME 1 ---
    # Sprawdzamy, czy ten mecz ma już jakieś framy
    # Używamy filter na match_players, bo Frame jest podpięty pod MatchPlayer
    existing_frames = Frame.objects.filter(match_player__in=match_players)

    if not existing_frames.exists() and match_players.exists():
        # Jeśli nie ma framów, tworzymy Frame nr 1
        Frame.objects.create(
            match_player=match_players.first(),  # Przypisujemy do pierwszego gracza (techniczny wymóg bazy)
            frame_number=1,
            points_scored_player1=0,
            points_scored_player2=0,
            active_player=players_list[0] if players_list else None
        )
        print(f"Utworzono Frame 1 dla meczu {match.id}")
    # -----------------------------------

    # 2. Reszta kodu bez zmian (liczenie statystyk)
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
        # Możemy przekazać ID obecnego frama, jeśli potrzebne
        'current_frame': existing_frames.last() if existing_frames.exists() else None
    }

    return render(request, 'start_game.html', context)


def add_competition(request):
    if request.method == 'POST':
        form = CompetitionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('competition_list')
    else:
        form = CompetitionForm()

    return render(request, 'add_competition.html', {'form': form})


def edit_competition(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    if request.method == 'POST':
        form = CompetitionForm(request.POST, instance=competition)
        if form.is_valid():
            form.save()
            return redirect('competition_detail', pk=pk)
    else:
        form = CompetitionForm(instance=competition)

    return render(request, 'edit_competition.html', {'form': form, 'competition': competition})


def competition_stages(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    group_stages = competition.groupstage_stages.all()
    knockout_stages = competition.knockoutstage_stages.all()
    stages = list(group_stages) + list(knockout_stages)

    stages_with_matches = []
    for stage in stages:
        if isinstance(stage, GroupStage):
            matches = stage.matches.all()
        else:
            matches = stage.matches.all()
        stages_with_matches.append({
            'stage': stage,
            'matches': matches
        })

    return render(request, 'competition_stages.html', {
        'competition': competition,
        'stages_with_matches': stages_with_matches
    })


def competition_list(request):
    competitions = Competition.objects.all()
    return render(request, 'competition_list.html', {'competitions': competitions})


def competition_detail(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
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


def add_matches_to_competition(request, competition_id):
    competition = get_object_or_404(Competition, id=competition_id)
    group_stages = competition.groupstage_stages.all()
    knockout_stages = competition.knockoutstage_stages.all()

    if request.method == 'POST':
        form = AddMatchesToCompetitionForm(request.POST, competition=competition)
        if form.is_valid():
            selected_matches = form.cleaned_data['matches']
            for match in selected_matches:
                stage_id = request.POST.get(f'stage_{match.id}')
                if stage_id:
                    group_stage = group_stages.filter(id=stage_id).first()
                    knockout_stage = knockout_stages.filter(id=stage_id).first()
                    if group_stage:
                        match.group_stage = group_stage
                    elif knockout_stage:
                        match.knockout_stage = knockout_stage
                    match.save()
            competition.matches.add(*selected_matches)
            messages.success(request, "Matches successfully added to the competition.")
            return redirect('competition_detail', pk=competition.id)
    else:
        form = AddMatchesToCompetitionForm(competition=competition)

    stages = list(group_stages) + list(knockout_stages)

    return render(request, 'add_matches_to_competition.html', {
        'form': form,
        'competition': competition,
        'stages': stages
    })


def create_temporary_match(request):
    if request.method == 'POST':
        form = MatchForm(request.POST, request=request)
        if form.is_valid():
            match = form.save(commit=True)

            return redirect('match_detail', pk=match.pk)
    else:
        form = MatchForm()

    return render(request, 'create_temporary_match.html', {'form': form})


def create_group_stage(request, competition_id):
    competition = get_object_or_404(Competition, id=competition_id)

    if competition.players.count() == 0:
        messages.error(request, "Please add players to the competition before creating a group stage.")
        return redirect('add_players_to_competition', pk=competition.id)

    if request.method == 'POST':
        form = GroupStageForm(request.POST)
        if form.is_valid():
            group_stage = form.save(commit=False)
            group_stage.competition = competition
            group_stage.save()
            group_stage.create_groups_and_matches(form.cleaned_data['default_frames'])
            return redirect('competition_detail', pk=competition.id)
    else:
        form = GroupStageForm()

    return render(request, 'create_group_stage.html', {'form': form, 'competition': competition})


def create_knockout_stage(request, competition_id):
    competition = get_object_or_404(Competition, id=competition_id)

    if request.method == 'POST':
        form = KnockoutStageForm(request.POST)
        if form.is_valid():
            knockout_stage = form.save(commit=False)
            knockout_stage.competition = competition
            knockout_stage.save()
            knockout_stage.create_knockout_matches()
            return redirect('competition_detail', pk=competition.id)

    else:
        form = KnockoutStageForm()

    return render(request, 'create_knockout_stage.html', {'form': form, 'competition': competition})


def register(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful.")
            return redirect('home')
        else:
            messages.error(request, "Registration failed. Please correct the errors below.")

    else:
        form = SignUpForm()
    return render(request, 'register.html', {'form': form})


def home(request):
    return render(request, 'home.html')


@login_required
def user_settings(request):
    user = request.user

    if request.method == 'POST':
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was successfully updated!")
            return redirect('login')
        else:
            messages.error(request, 'Please correct the error below.')

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


def add_players_to_competition(request, pk):
    competition = get_object_or_404(Competition, id=pk)
    if request.method == 'POST':
        player_ids = request.POST.getlist('players')
        players = Player.objects.filter(id__in=player_ids)
        competition.players.add(*players)
        return redirect('competition_detail', pk=competition.id)
    else:
        available_players = Player.objects.exclude(competitions=competition)
        return render(request, 'add_players_to_competition.html', {
            'competition': competition,
            'available_players': available_players
        })


def achievement_list(request):
    achievements = Achievement.objects.all()
    context = {
        'achievements': achievements
    }
    return render(request, 'achievement_list.html', context)


client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


@csrf_exempt
@require_POST
def gpt_analysis(request):
    api_key = os.getenv('OPENAI_API_KEY')
    print(f"OPENAI API KEY in view: {'SET' if api_key else 'NOT SET'}", file=sys.stderr)

    if not api_key:
        print("No OpenAI API key found.", file=sys.stderr)
        return JsonResponse({'error': 'No OpenAI API key found.'}, status=500)

    try:
        print("Attempting to create ChatCompletion", file=sys.stderr)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                 "content": "You are a snooker expert. Analyze recent results and provide a short analysis."},
                {"role": "user", "content": "Give a brief analysis of recent snooker results."}
            ]
        )
        analysis = response.choices[0].message.content
        print("ChatCompletion successful", file=sys.stderr)
        return JsonResponse({'analysis': analysis})
    except Exception as e:
        print(f"Error in gpt_analysis: {str(e)}", file=sys.stderr)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def update_game_data(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        match_id = data.get('match_id')
        player_id = data.get('player_id')
        points = data.get('points')
        ball_color = data.get('ball_color')

        if match_id is None or player_id is None or points is None or ball_color is None:
            return JsonResponse({'status': 'error', 'message': 'Missing data fileds'})

        match_player = MatchPlayer.objects.filter(match_id=match_id, player_id=player_id).first()

        if not match_player:
            return JsonResponse({'status': 'error', 'message': 'Match or player not found'})

        frame = Frame.objects.filter(match_player=match_player).latest('frame_number')

        if player_id == 1:
            frame.points_scored_player1 = (frame.points_scored_player1 or 0) + points
        else:
            frame.points_scored_player2 = (frame.points_scored_player2 or 0) + points

        if player_id == 1:
            frame.break_points_player1.append(points)
        else:
            frame.break_points_player2.append(points)

        frame.save()

        return JsonResponse({'status': 'success'})
    except Exception as e:
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


@csrf_exempt
@require_POST
def save_frame_result(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        p1_score = data.get('p1_score')
        p2_score = data.get('p2_score')
        # Pobieramy czas (w sekundach), domyślnie 0
        duration_seconds = data.get('duration', 0)

        if not all([match_id, winner_id, p1_score is not None, p2_score is not None]):
            return JsonResponse({'status': 'error', 'message': 'Missing data fields'})

        match = get_object_or_404(Match, pk=match_id)
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

        # 3. Zapisz wyniki
        last_frame.points_scored_player1 = p1_score
        last_frame.points_scored_player2 = p2_score
        last_frame.winner = winner

        # --- ZAPIS CZASU GRY ---
        if duration_seconds > 0:
            last_frame.time_duration = timedelta(seconds=duration_seconds)
        # -----------------------

        if last_frame.break_points_player1:
            last_frame.max_break_player1 = max(last_frame.break_points_player1)
        if last_frame.break_points_player2:
            last_frame.max_break_player2 = max(last_frame.break_points_player2)

        last_frame.save()

        # 4. Sprawdź czy mecz się skończył
        frames_needed = (match.number_of_frames // 2) + 1

        p1_mp = match_players.filter(position=1).first()
        if not p1_mp: p1_mp = match_players.first()
        p1_obj = p1_mp.player

        p1_wins = Frame.objects.filter(match_player__in=match_players, winner=p1_obj).count()
        total_frames_played = Frame.objects.filter(match_player__in=match_players, winner__isnull=False).count()
        p2_wins = total_frames_played - p1_wins

        match_over = False
        winner_name = str(winner)

        if p1_wins >= frames_needed or p2_wins >= frames_needed:
            match_over = True
        else:
            # TWORZYMY NOWY FRAME
            new_frame_number = last_frame.frame_number + 1
            Frame.objects.create(
                match_player=match_players.first(),
                frame_number=new_frame_number,
                points_scored_player1=0,
                points_scored_player2=0
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

