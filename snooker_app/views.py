from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DeleteView

from snooker_app.forms import PlayerForm, PlayerEditForm, RefereeForm, VenueForm, MatchForm, CompetitionForm
from snooker_app.models import Player, Referee, Venue, Match, Competition


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


# =======================================================
# =======================================================
# =======================================================
# =======================================================


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
    return render(request, 'competition_stages.html', {'competition': competition, 'stages': stages})


def competition_list(request):
    competitions = Competition.objects.all()
    return render(request, 'competition_list.html', {'competitions': competitions})


def competition_detail(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    return render(request, 'competition_detail.html', {'competition': competition})


class CompetitionDeleteView(DeleteView):
    model = Competition
    template_name = 'delete_competition.html'
    success_url = reverse_lazy('competition_list')
