from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import DeleteView
from django.contrib import messages
from django.db.models import Count, Sum, F, Case, When, IntegerField
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm

from snooker_app.forms import (PlayerForm, PlayerEditForm, RefereeForm, VenueForm,
                               MatchForm, CompetitionForm, AddMatchesToCompetitionForm,
                               GroupStageForm, SignUpForm, KnockoutStageForm)
from snooker_app.models import (Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage,
                                TemporaryPlayer, MatchPlayer, Achievement)

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


def delete_venue(request, pk):
    venue = get_object_or_404(Venue, pk=pk)
    if request.method == 'POST':
        venue.delete()
        return redirect('venue_list')

    return render(request, 'delete_venue.html', {'venue': venue})


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


def match_detail(request, match_id):
    match = get_object_or_404(Match, pk=match_id)
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


def start_game(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    players = match.players.all()
    if request.method == 'POST':
        return redirect('match_detail', match_id=match_id)

    context = {
        'match': match,
        'players': players,
        'match_id': match_id
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
                played=Count('match'),
                won=Sum(Case(When(points_scored__gt=F('match__matchplayer__points_scored'), then=1), default=0,
                             output_field=IntegerField())),
                drawn=Sum(Case(When(points_scored=F('match__matchplayer__points__scored'), then=1), default=0,
                               output_field=IntegerField())),
                frames_won=Sum('points_scored'),
                frames_lost=Sum('match__matchplayer__points_scored') - Sum('points_scored')
            )
            stats['player'] = player
            stats['points'] = stats['won'] * 3 + stats['drawn']
            player_stats.append(stats)

        player_stats.sort(key=lambda x: (x['points'], x['frames_won'] - x['frames_lost']), reverse=True)

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
        form = MatchForm(request.POST)
        if form.is_valid():
            temp_player1 = TemporaryPlayer.objects.create(name=f'Player {TemporaryPlayer.objects.count() + 1}')
            temp_player2 = TemporaryPlayer.objects.create(name=f'Player {TemporaryPlayer.objects.count() + 2}')
            match = form.save(commit=False)
            match.temp_player1 = temp_player1
            match.temp_player2 = temp_player2
            match.is_temporary = True
            match.save()
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


# =======================================================
# =======================================================
# =======================================================
# =======================================================

def achievement_list(request):
    achievements = Achievement.objects.all()
    context = {
        'achievements': achievements
    }
    return render(request, 'achievement_list.html', context)
