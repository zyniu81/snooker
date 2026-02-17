import datetime
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from io import StringIO

import openpyxl
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth.views import LoginView
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Avg, Case, Count, F, IntegerField, Max, Q, Sum, When
from django.dispatch import receiver
from django.forms import modelformset_factory
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import (CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView)

from .services import calculate_competition_results, update_career_stats
from .tokens import account_activation_token

from snooker_app.forms import (PlayerForm, PlayerEditForm, RefereeForm, VenueForm,
                               MatchForm, CompetitionForm, AddMatchesToCompetitionForm,
                               GroupStageForm, SignUpForm, KnockoutStageForm, MassMatchEditForm, ExtraMatchForm,
                               SubstitutePlayerForm, GroupAssignmentForm, AddPlayerToGroupForm, KnockoutSwapForm,
                               ImportCodeForm, SelectImportedPlayersForm, MatchFormSetValidating, EquipmentForm,
                               EquipmentPhotoForm, UserUpdateForm, ProfileUpdateForm, TrainingSessionForm)
from snooker_app.models import (Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage,
                                MatchPlayer, Frame, GroupStanding, SharingToken, CompetitionResult, Equipment,
                                EquipmentPhoto, TrainingSession, Group, Announcement, SnookerNews)


# --- HELPER FUNCTIONS ---

def check_ownership(request, obj):
    """
    Checks if the user is the owner of the object.
    If the object is public, only a Superuser can edit it.
    """
    if request.user.is_superuser:
        return True
    if obj.owner == request.user:
        return True
    return False


# --------------------------

@login_required
def player_list(request):
    # Logic: (Mine OR Public) AND (Not Guests)
    players = Player.objects.filter(
        (Q(owner=request.user) | Q(is_public=True)) & Q(is_guest=False)
    ).order_by('-created_at')

    return render(request, 'player_list.html', {'players': players})


@login_required
def add_player(request):
    if request.method == 'POST':
        # CHANGE: Added request.FILES
        form = PlayerForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            player = form.save(commit=False)
            player.owner = request.user

            # Admin creates public players by default (optional)
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

            # --- Conversion Logic (Temporary -> Permanent) ---
            if was_temporary and not is_now_temporary:
                # FIX 1: Using Q for player1/player2
                matches_qs = Match.objects.filter(
                    (Q(player1=saved_player) | Q(player2=saved_player)) & Q(is_temporary=True)
                )

                # FIX 2: Searching opponents via correct relations (matches_as_p1 / matches_as_p2)
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

            # --- Updating names in matches (Cache) ---
            # FIX 3: Here too we use Q for player1/player2
            player_matches = Match.objects.filter(
                Q(player1=saved_player) | Q(player2=saved_player)
            )
            for m in player_matches:
                m.save() # This triggers model.save(), which updates player_names

            return redirect('player_detail', pk=player.pk)
    else:
        form = PlayerEditForm(instance=player, request=request)

    return render(request, 'player_edit.html', {'form': form, 'player': player})


@login_required
def player_detail(request, pk):
    # We can view public or our own
    # If entering a "Guest" (is_guest=True),
    # they technically belong to you (owner=request.user), so this condition works correctly.
    player = get_object_or_404(Player, pk=pk)

    if not (player.is_public or player.owner == request.user):
        raise PermissionDenied("You do not have access to this player.")

    # --- FETCHING MATCH HISTORY (FIXED FOR CLONES) ---
    # We search for matches where:
    # 1. Player is P1 or P2 (standard)
    # 2. Clone of this player is P1 or P2 (new)
    recent_matches = Match.objects.filter(
        Q(player1=player) | Q(player1__cloned_from=player) |
        Q(player2=player) | Q(player2__cloned_from=player)
    ).distinct().order_by('-date', '-time')[:5]
    # -----------------------------------------------

    # --- FETCHING TOURNAMENT RESULTS ---
    comp_results = CompetitionResult.objects.filter(player=player).select_related('competition').order_by(
        '-competition__end_date')

    # Counters for "Trophy Room"
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
         from django.db.models import Q
         return Player.objects.filter(
            Q(owner=self.request.user) | Q(is_temporary=True)
        )


@login_required
def referee_list(request):
    referees = Referee.objects.filter(Q(owner=request.user) | Q(is_public=True))
    return render(request, 'referee_list.html', {'referees': referees})


@login_required
def add_referee(request):
    if request.method == 'POST':
        # Added request.FILES
        form = RefereeForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            referee = form.save(commit=False)
            referee.owner = request.user
            # Optional: Admin creates public by default, but also has a checkbox
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
        messages.error(request, "Permission denied.")
        return redirect('referee_list')

    if request.method == 'POST':
        # Added request.FILES
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
        # ERROR WAS HERE: Added request.FILES
        form = VenueForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            venue = form.save(commit=False)
            venue.owner = request.user

            # This logic is fine if we force public for admin,
            # although admin now has a checkbox in the form.
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
        messages.error(request, "Permission denied.")
        return redirect('venue_list')

    if request.method == 'POST':
        # ERROR WAS HERE: Added request.FILES before instance
        form = VenueForm(request.POST, request.FILES, instance=venue, request=request)
        if form.is_valid():
            form.save()
            # Better to return to details than list after edit
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
    # 1. BASE: Your original query
    matches = Match.objects.filter(owner=request.user).order_by('-date', '-time')

    # 2. Get years for dropdown (before filtering the list!)
    # Method .dates() returns unique dates (years) from QuerySet
    available_years = matches.dates('date', 'year', order='DESC')

    # 3. FILTER: YEAR
    selected_year = request.GET.get('year')
    if selected_year:
        matches = matches.filter(date__year=selected_year)

    # 4. FILTER: STATUS
    selected_status = request.GET.get('status')
    if selected_status:
        matches = matches.filter(status=selected_status)

    return render(request, 'match_list.html', {
        'matches': matches,
        # Pass data to filter form
        'available_years': available_years,
        'selected_year': selected_year,
        'selected_status': selected_status,
    })


@login_required
def add_match(request):
    # 1. Check if returning from import with a specific guest
    guest_id = request.GET.get('guest_id')

    # 2. Build QuerySet of players available in this form
    # Logic: (My Regular Players) OR (That One Specific Guest, if exists)
    # This way you don't normally see guests, but you will see this one now.

    # Base players (Yours, non-temporary)
    base_players = Player.objects.filter(owner=request.user, is_guest=False)

    if guest_id:
        # If guest_id exists, add to pool (ensuring they belong to you)
        specific_guest = Player.objects.filter(owner=request.user, pk=guest_id)
        players_queryset = (base_players | specific_guest).distinct().order_by('last_name')
    else:
        players_queryset = base_players.order_by('last_name')

    if request.method == 'POST':
        form = MatchForm(request.POST, request=request)

        # IMPORTANT: Must override queryset in form fields BEFORE validation.
        # Otherwise Django says "Select a valid choice" because guest is hidden in default form QuerySet.
        form.fields['player1'].queryset = players_queryset
        form.fields['player2'].queryset = players_queryset

        if form.is_valid():
            match = form.save(commit=False)
            match.owner = request.user

            # SAVE MATCH
            match.save()

            # Save referees
            form.save_m2m()

            # Handling temporary players (created manually from input, not code)
            form.create_temp_players_if_needed(match)

            return redirect('match_detail', pk=match.pk)
    else:
        form = MatchForm(request=request)

        # Override queryset so player appears in dropdown
        form.fields['player1'].queryset = players_queryset
        form.fields['player2'].queryset = players_queryset

        # UX: If we have a guest, automatically set as Player 2
        if guest_id:
            form.fields['player2'].initial = guest_id

    return render(request, 'add_match.html', {
        'form': form,
        'guest_id': guest_id  # Pass to template (to handle Import button)
    })


def match_detail(request, pk):
    match = get_object_or_404(Match, pk=pk)

    # --- ACCESS LOGIC ---
    has_access = False
    if match.owner is None:
        has_access = True
    elif match.is_public:
        has_access = True
    elif request.user.is_authenticated and match.owner == request.user:
        has_access = True
    # --- NEW: ALLOW ORIGINAL OWNER (READ ONLY) ---
    elif request.user.is_authenticated:
        if match.player1 and match.player1.cloned_from and match.player1.cloned_from.owner == request.user:
            has_access = True
        elif match.player2 and match.player2.cloned_from and match.player2.cloned_from.owner == request.user:
            has_access = True

    if not has_access:
        if request.user.is_authenticated:
            raise PermissionDenied
        else:
            return redirect(f'{reverse("login")}?next={request.path}')
    # ---------------------

    # Game status
    game_status = match.get_game_status()

    # Get frames
    frames = Frame.objects.filter(match_player__match=match).order_by('frame_number')

    # --- PLAYER DATA PREPARATION ---
    p1_data = None
    if match.player1:
        p1_wins = frames.filter(winner=match.player1).count()
        p1_data = {
            'name': str(match.player1),
            'obj': match.player1,
            'wins': p1_wins
        }

    p2_data = None
    if match.player2:
        p2_wins = frames.filter(winner=match.player2).count()
        p2_data = {
            'name': str(match.player2),
            'obj': match.player2,
            'wins': p2_wins
        }

    # --- BALL COUNT SUMMATION (NOWE) ---
    colors_order = ['red', 'yellow', 'green', 'brown', 'blue', 'pink', 'black']
    p1_ball_totals = {color: 0 for color in colors_order}
    p2_ball_totals = {color: 0 for color in colors_order}

    for frame in frames:
        # We get data from JSONField
        counts = frame.ball_counts or {}

        p1_frame_counts = counts.get('player1', {})
        for color, count in p1_frame_counts.items():
            if color in p1_ball_totals:
                p1_ball_totals[color] += count

        p2_frame_counts = counts.get('player2', {})
        for color, count in p2_frame_counts.items():
            if color in p2_ball_totals:
                p2_ball_totals[color] += count

    context = {
        'match': match,
        'is_finished': game_status['is_finished'],
        'winner': game_status['winner'],
        'frames': frames,
        'p1': p1_data,
        'p2': p2_data,
        'p1_ball_totals': p1_ball_totals,
        'p2_ball_totals': p2_ball_totals,
    }

    return render(request, 'match_detail.html', context)


@login_required
def edit_match(request, pk):
    match = get_object_or_404(Match, pk=pk)
    if match.owner != request.user:
        messages.error(request, "You can only edit your own matches.")
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

    # --- NEW SAFEGUARD ---
    # Instead of def delete(...), use this:
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # BLOCK CONDITION
        if self.object.group_stage or self.object.knockout_stage:
            messages.error(request, "You cannot delete a match that is part of a tournament!")
            # Return to list instead of deleting
            return redirect(self.success_url)

        # If condition not met -> delete
        return self.delete(request, *args, **kwargs)


def start_game(request, pk):
    # Get match
    match = get_object_or_404(Match, pk=pk)

    # --- ACCESS LOGIC ---
    has_access = False
    if match.owner is None:
        has_access = True
    elif match.is_public:
        has_access = True
    elif request.user.is_authenticated and match.owner == request.user:
        has_access = True

    if not has_access:
        if request.user.is_authenticated:
            raise PermissionDenied("Access denied.")
        else:
            return redirect(f'{reverse("login")}?next={request.path}')
    # ----------------------

    status = match.get_game_status()
    if status['is_finished']:
        messages.warning(request, "This match is already finished!")
        return redirect('match_detail', pk=pk)

    # --- PURE LOGIC (No auto-repair) ---
    # Get players ONLY from MatchPlayer table, sorted by position.
    # If empty -> too bad. No guessing.
    match_players = MatchPlayer.objects.filter(match=match).order_by('position')

    # Create Player object list (needed for active_player etc.)
    players_list = [mp.player for mp in match_players]

    # --- FRAME LOGIC ---
    existing_frames = Frame.objects.filter(match_player__in=match_players)
    active_frame_object = None

    # Create Frame 1 only if we have players (to avoid error on empty list)
    if not existing_frames.exists() and match_players.exists():
        active_frame_object = Frame.objects.create(
            match_player=match_players.first(), # This is safe because we have .exists()
            frame_number=1,
            points_scored_player1=0,
            points_scored_player2=0,
            active_player=players_list[0] if players_list else None
        )
    else:
        active_frame_object = existing_frames.last()

    # --- CALCULATING RESULTS ---
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
        'players': player_results, # If match was broken, this will be empty. And that's fine.
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

    # 1. Data fetching (unchanged)
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

    # 2. Bracket View Logic (NEW)
    view_mode = request.GET.get('view', 'list')  # Default list

    for stage in knockout_stages_qs:
        matches = stage.matches.all().order_by('round_number', 'id')

        rounds_map = defaultdict(list)
        stage.third_place_matches = []  # <--- Create list for 3rd place match

        for m in matches:
            if m.round_number < 99:
                # Main tree
                rounds_map[m.round_number].append(m)
            else:
                # 3rd place match (or other specials)
                stage.third_place_matches.append(m)

        # Tree building (unchanged)
        stage.bracket_tree = []
        for r_num in sorted(rounds_map.keys()):
            stage.bracket_tree.append({
                'round_number': r_num,
                'matches': rounds_map[r_num]
            })

    # 3. Merging stages (unchanged)
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


# --- Checking stage order ---
def get_next_stage_order_or_block(competition, request):
    """
    Checks if the previous stage is finished.
    Returns (next_order, error_message).
    If error_message is set, abort action.
    """
    # Get all sorted stages
    stages = competition.get_stages()  # Use method from Competition model

    if not stages:
        return 1, None  # This is the first stage, Order = 1

    last_stage = stages[-1]  # Last added stage

    if not last_stage.is_finished:
        return None, f"You must finish the current stage '{last_stage.name}' before adding a new one."

    return last_stage.order + 1, None


@login_required
def add_matches_to_competition(request, competition_id):
    """
    Creates a single 'Extra Match' within the tournament.
    """
    competition = get_object_or_404(Competition, pk=competition_id)
    if competition.owner != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        form = ExtraMatchForm(request.POST, competition=competition)
        if form.is_valid():
            # 1. Find or create "Extras" stage
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

            # 2. Create match
            match = form.save(commit=False)
            match.owner = request.user
            match.knockout_stage = extra_stage
            match.knockout_name = "Extra Match"

            # Save match.
            # This triggers our "automaton" in models.py which creates MatchPlayer entries.
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
    # Clear session (unchanged)
    if 'temp_match_id' in request.session:
        del request.session['temp_match_id']

    if request.method == 'POST':
        form = MatchForm(request.POST, request=request)
        if form.is_valid():
            # This assigns form data to object (including player1/player2 if selected from list)
            match = form.save(commit=False)

            # Login-dependent settings
            if request.user.is_authenticated:
                match.owner = request.user
                match.is_public = False
            else:
                match.owner = None
                match.is_public = True

            match.is_temporary = True

            # --- PLAYER LOGIC ---
            create_temp = form.cleaned_data.get('create_temporary_players')

            if not request.user.is_authenticated or create_temp:
                # SCENARIO 1: Create new temporary players
                prefix = "Temporary Player"

                # Create Player objects
                p1 = Player.objects.create(first_name=f"{prefix} 1", is_temporary=True, owner=match.owner)
                p2 = Player.objects.create(first_name=f"{prefix} 2", is_temporary=True, owner=match.owner)

                # --- CHANGE: Assign them to seats ---
                match.player1 = p1
                match.player2 = p2

                # Helper fields for cleanup
                match.temp_player1 = p1
                match.temp_player2 = p2

            # --- SAVE ---
            # This triggers code in models.py which automatically creates MatchPlayer!
            match.save()

            # Save referees (ManyToMany relation requires saved match ID)
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

    # 1. Check if stage can be added
    next_order, error_msg = get_next_stage_order_or_block(competition, request)
    if error_msg:
        messages.error(request, error_msg)
        return redirect('competition_detail', pk=competition.id)

    # 2. Form logic
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
            stage.order = next_order  # <--- AUTO ORDER (Forced)
            stage.save()

            # (Rest of player saving and match generation logic - unchanged)
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
        # Pass next_order as initial (for safety, although field is hidden)
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

    # 1. Check if stage can be added
    next_order, error_msg = get_next_stage_order_or_block(competition, request)
    if error_msg:
        messages.error(request, error_msg)
        return redirect('competition_detail', pk=competition.id)

    # 2. Get players (with group qualification logic we did earlier)
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
            # 1. We save the user, but as inactive
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            # 2. Email Sending Logic (New)
            current_site = get_current_site(request)
            subject = 'Activate your Snooker App account'
            message = render_to_string('acc_active_email.html', {
                'user': user,
                'domain': current_site.domain,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': account_activation_token.make_token(user),
            })
            user.email_user(subject, message)

            # --- CLAIMING TEMPORARY MATCH ---
            temp_match_id = request.session.get('temp_match_id')
            if temp_match_id:
                try:
                    match = Match.objects.get(pk=temp_match_id)
                    if match.owner is None:
                        match.owner = user
                        match.is_temporary = False
                        match.is_public = False
                        match.save()

                        players_to_check = [match.player1, match.player2]
                        for player in players_to_check:
                            if player and player.owner is None:
                                player.owner = user
                                player.is_temporary = False
                                player.save()

                        # We clear the session immediately
                        del request.session['temp_match_id']
                except Match.DoesNotExist:
                    pass
            # ---------------------------------------

            # Instead of logging in and redirecting to home, we show an information page
            return render(request, 'registration_pending.html')
        else:
            messages.error(request, "Registration failed. Check for errors below.")
    else:
        form = SignUpForm()
    return render(request, 'register.html', {'form': form})


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        if user.profile.new_email_temp:
            user.email = user.profile.new_email_temp
            user.profile.new_email_temp = None
            user.save()

        user.profile.email_confirmed = True
        user.profile.save()

        # We make sure that the user is active (important for registration)
        if not user.is_active:
            user.is_active = True
            user.save()

        messages.success(request, "E-mail confirmed! You can now log in.")
        return redirect('login')
    else:
        return render(request, 'activation_invalid.html')


def home(request):
    now = timezone.now()

    # We download ads that:
    # 1. They are active (is_active=True)
    # 2. Start date is in the past (they have already started)
    # 3. End date is empty OR in the future (not expired yet)
    announcements = Announcement.objects.filter(
        is_active=True,
        start_date__lte=now
    ).filter(
        models.Q(end_date__isnull=True) | models.Q(end_date__gte=now)
    ).order_by('-start_date')

    # 4. News - 3 latest active news
    latest_news = SnookerNews.objects.filter(is_active=True).order_by('-created_at')[:3]

    return render(request, 'home.html', {
        'announcements': announcements,
        'latest_news': latest_news
    })


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
        # Show only my + public players who are not in this tournament
        available_players = Player.objects.filter(
            (Q(owner=request.user) | Q(is_public=True)) & Q(is_guest=False)
        ).exclude(competitions=competition)

        return render(request, 'add_players_to_competition.html', {
            'competition': competition,
            'available_players': available_players
        })


@login_required
def achievement_list(request):
    # Sort e.g. by highest break descending
    # CHANGE: Added condition & Q(is_guest=False)
    players = Player.objects.filter(
        (Q(owner=request.user) | Q(is_public=True)) & Q(is_guest=False)
    ).order_by('-highest_break')

    # Pass list of players to template (instead of achievements)
    return render(request, 'achievement_list.html', {'players': players})


@csrf_exempt
@require_POST
def gpt_analysis(request):
    # Commented out by request
    return JsonResponse({'error': 'Feature disabled'}, status=503)


@csrf_exempt
@require_POST
def update_game_data(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        match_id = data.get('match_id')
        player_id = data.get('player_id')
        points = data.get('points')

        # Optional: ball color for statistics
        ball_color = data.get('ball_color')

        if match_id is None or player_id is None or points is None:
            return JsonResponse({'status': 'error', 'message': 'Missing data fields'})

        # STEP 1: Try to find the Frame
        try:
            frame = Frame.objects.filter(match_player__match_id=match_id).latest('frame_number')
        except Frame.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'No active frame found for this match'})

        # STEP 2: Determine WHICH player it is (1 or 2?) - HARD DATA ONLY
        match_player = MatchPlayer.objects.filter(match_id=match_id, player_id=player_id).first()

        target_position = None

        if match_player:
            # Trust only the database
            target_position = match_player.position
        else:
            # ZERO TOLERANCE: If player is not in MatchPlayer, it's a critical error.
            # We do not guess, we do not check if ID is "1" or "2".
            return JsonResponse(
                {'status': 'error', 'message': f'Security: Player ID {player_id} is not assigned to Match {match_id}.'})

        # STEP 3: Save points in the correct column
        if target_position == 1:
            frame.points_scored_player1 = (frame.points_scored_player1 or 0) + points
            if frame.break_points_player1 is None: frame.break_points_player1 = []
            frame.break_points_player1.append(points)

        elif target_position == 2:
            frame.points_scored_player2 = (frame.points_scored_player2 or 0) + points
            if frame.break_points_player2 is None: frame.break_points_player2 = []
            frame.break_points_player2.append(points)

        else:
            # This theoretically shouldn't happen if MatchPlayer has position 1 or 2
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

        # --- API SECURITY ---
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

        # Statistics...
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

        # --- NEW: Getting ball counters from JSON ---
        ball_counts_data = data.get('ball_counts', {})

        if not all([match_id, winner_id, p1_score is not None, p2_score is not None]):
            return JsonResponse({'status': 'error', 'message': 'Missing data fields'})

        winner = get_object_or_404(Player, pk=winner_id)

        # 1. Fetch players (PURE LOGIC)
        match_players = MatchPlayer.objects.filter(match=match).order_by('position')

        # --- ZERO TOLERANCE ---
        # If no players in MatchPlayer, abort. Do not force repair.
        if not match_players.exists():
            return JsonResponse({
                'status': 'error',
                'message': 'CRITICAL ERROR: Match data integrity violation. Players not found in MatchPlayer table. Please recreate the match.'
            })

        # 2. Find the last frame
        last_frame = Frame.objects.filter(match_player__in=match_players).order_by('-frame_number').first()

        # --- FRAME RESCUE SECTION ---
        if not last_frame:
            last_frame = Frame.objects.create(
                match_player=match_players.first(),
                frame_number=1,
                points_scored_player1=0,
                points_scored_player2=0,
                active_player=match_players.first().player
            )

        # --- CALCULATING SUCCESS RATES ---
        p1_attempts = p1_pots + p1_misses
        p1_success_rate = 0.0
        if p1_attempts > 0:
            p1_success_rate = round((p1_pots / p1_attempts) * 100, 2)

        p2_attempts = p2_pots + p2_misses
        p2_success_rate = 0.0
        if p2_attempts > 0:
            p2_success_rate = round((p2_pots / p2_attempts) * 100, 2)

        # 3. Save results
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

        # --- NEW: We save ball counters to the database ---
        last_frame.ball_counts = ball_counts_data

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

        # 4. Update status
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

    # 1. Fetch matches (Groups + Knockout)
    # --- IMPORTANT SORTING CHANGE ---
    # Sort by STAGE first, then by GROUP/ROUND, and finally by TIME.
    # This ensures the {% ifchanged %} tag in HTML groups matches nicely with headers.
    matches = (Match.objects.filter(
        Q(group_stage__competition=competition) |
        Q(knockout_stage__competition=competition)
    ).exclude(status='FINISHED') \
    .exclude(player1__isnull=True) \
    .exclude(player2__isnull=True) \
    .order_by(
        'group_stage',  # Group stage first
        'group',  # Then specific group (1, 2, 3...)
        'knockout_stage',  # Then knockout stage
        'round_number',  # Then round number (THIS IS KEY!)
        'date',  # Date only now
        'time'  # And time
    ))

    # Create Formset class
    MatchFormSet = modelformset_factory(
        Match,
        form=MassMatchEditForm,
        formset=MatchFormSetValidating,
        extra=0
        )

    if request.method == 'POST':
        formset = MatchFormSet(request.POST, queryset=matches)
        if formset.is_valid():
            # Save forms
            formset.save()
            messages.success(request, "Matches updated successfully.")
            return redirect('competition_detail', pk=competition.id)
    else:
        formset = MatchFormSet(queryset=matches)

    # --- DROPDOWN FILTERING ---
    my_referees = Referee.objects.filter(Q(owner=request.user) | Q(is_public=True))

    # Get base list of all players in tournament
    all_tournament_players = competition.players.all()

    for form in formset:
        # 1. Referees (unchanged)
        form.fields['referees'].queryset = my_referees

        # 2. Get match instance for this row
        match = form.instance

        # 3. Determine who can be selected in this row
        # Default: All from tournament (for Play-offs)
        allowed_players = all_tournament_players

        # If match belongs to a GROUP -> narrow list to members of that group
        if match.group:
            # Get player IDs from the standings of this specific group
            group_ids = match.group.standings.values_list('player_id', flat=True)
            allowed_players = all_tournament_players.filter(id__in=group_ids)

        # 4. Assign "tailor-made" list to fields
        if 'player1' in form.fields:
            form.fields['player1'].queryset = allowed_players
        if 'player2' in form.fields:
            form.fields['player2'].queryset = allowed_players

    return render(request, 'mass_edit_matches.html', {
        'formset': formset,
        'competition': competition
    })


# --- HELPER FUNCTION IN VIEWS.PY ---

def get_sorted_players_for_stage(competition, user):
    """
    Returns three lists of players:
    1. winners: Winners of the last stage
    2. eliminated: Losers of the last stage
    3. others: All other players of the user (excluding temporary),
       who did not play in the last stage.
    """

    # 1. Find all stages and sort
    group_stages = list(competition.groupstage_stages.all())
    knockout_stages = list(competition.knockoutstage_stages.all())
    all_stages = sorted(group_stages + knockout_stages, key=lambda x: x.order)

    # Get only players who are participants of THIS tournament
    all_user_players = set(competition.players.all())

    # If first stage (no history), all your players go to 'others'
    if not all_stages:
        return [], [], list(all_user_players)

    # 3. Get last stage
    last_stage = all_stages[-1]

    # Get matches
    if hasattr(last_stage, 'matches'):
        matches = last_stage.matches.filter(status='FINISHED')
    else:
        matches = []

    # 4. Sorting participants of the last stage
    winners = set()
    participants = set()  # All who played in the last stage

    for match in matches:
        # Check specific seats
        if match.player1:
            participants.add(match.player1)
        if match.player2:
            participants.add(match.player2)
        # -------------------------------------------------------------

        if match.winner:
            winners.add(match.winner)

    # Eliminated are: Last stage participants MINUS Winners
    eliminated = participants - winners

    # Others are: All your DB players MINUS those who participated in the last stage
    others = all_user_players - participants

    return list(winners), list(eliminated), list(others)


# --- CLOSING STAGES AND TOURNAMENT ---

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

    # Set tournament status to FINISHED
    # (Ensure this field exists in Competition model, if not - add it)
    competition.status = 'FINISHED'
    competition.save()

    messages.success(request, f"Tournament '{competition.name}' has been officially closed! 🏆")
    return redirect('competition_ranking', competition_id=competition.pk)


@receiver(user_logged_in)
def claim_temporary_match(sender, user, request, **kwargs):
    """
    Function runs AUTOMATICALLY after every successful login.
    Checks if a temporary match ID exists in session and assigns it to the user.
    """
    temp_match_id = request.session.get('temp_match_id')

    if temp_match_id:
        try:
            # Find match that has no owner (is guest match)
            match = Match.objects.get(id=temp_match_id, owner__isnull=True)

            # 1. Assign match to user
            match.owner = user
            match.save()

            # 2. Also assign temporary players to this user!
            # Create list of potential players to check
            # (can be None, so we check 'if player' in loop)
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

    # Block for finished stage
    if stage.is_finished:
        messages.error(request, "Cannot substitute players in a finished stage.")
        return redirect('competition_detail', pk=competition.id)

    if request.method == 'POST':
        form = SubstitutePlayerForm(request.POST, stage=stage, owner=request.user)
        if form.is_valid():
            player_out = form.cleaned_data['player_out']
            player_in = form.cleaned_data['player_in']

            # --- SUBSTITUTION OPERATION (Atomic transaction for safety) ---
            with transaction.atomic():
                # 1. Add new player to tournament (if not present)
                competition.players.add(player_in)

                # 2. Swap in STANDINGS (GroupStanding)
                # Find old player entry in this stage
                standing = GroupStanding.objects.filter(
                    group__stage=stage,
                    player=player_out
                ).first()

                if standing:
                    standing.player = player_in
                    standing.save()

                # 3. Swap in MATCHES (Player 1)
                matches_p1 = Match.objects.filter(group_stage=stage, player1=player_out)
                for match in matches_p1:
                    match.player1 = player_in
                    match.save()

                # 4. Swap in MATCHES (Player 2)
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

    # SECURITY LOCK
    if stage.matches.filter(status='FINISHED').exists():
        messages.error(request, "Cannot edit groups because matches have already been played.")
        return redirect('competition_detail', pk=competition.id)

    # Define Formset (Edit table for all players)
    StandingFormSet = modelformset_factory(
        GroupStanding,
        form=GroupAssignmentForm,
        extra=0,  # We don't want automatic empty rows
        can_delete=True  # Enable deletion support
    )
    # We need to pass 'stage' to the form inside formset, so use form_kwargs
    formset_queryset = GroupStanding.objects.filter(group__stage=stage).order_by('group__name', 'player__last_name')

    if request.method == 'POST':
        # Check if this is the add new player action
        if 'add_player_submit' in request.POST:
            add_form = AddPlayerToGroupForm(request.POST, stage=stage, owner=request.user)
            if add_form.is_valid():
                new_player = add_form.cleaned_data['player']
                target_group = add_form.cleaned_data['group']
                competition.players.add(new_player)  # Ensure player is in tournament

                # Create table entry
                GroupStanding.objects.create(
                    group=target_group, player=new_player,
                    matches_played=0, matches_won=0, matches_drawn=0, matches_lost=0,
                    frames_won=0, frames_lost=0, points=0,
                    small_points_scored=0, small_points_conceded=0, highest_break=0
                )
                messages.success(request, f"Added {new_player} to Group {target_group.name}.")
                # Regenerate matches immediately after adding
                stage.regenerate_schedule()
                return redirect('manage_groups', stage_id=stage.id)

        # Check if this is the save group changes action (Formset)
        else:
            formset = StandingFormSet(request.POST, queryset=formset_queryset, form_kwargs={'stage': stage})
            if formset.is_valid():
                formset.save()  # Saves group changes and deletes selected players

                # SCHEDULE REGENERATION
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

    # Get 1st round matches for display (so you see who you are swapping)
    matches_r1 = Match.objects.filter(knockout_stage=stage, round_number=1).order_by('id')

    if request.method == 'POST':
        form = KnockoutSwapForm(request.POST, stage=stage)
        if form.is_valid():
            p1 = form.cleaned_data['player_1']
            p2 = form.cleaned_data['player_2']

            # --- SWAP LOGIC ---
            # We need to find matches where these players are
            # Note: They can be in the same match (host/guest swap) or in different ones

            # Find match for P1
            m1 = matches_r1.filter(player1=p1).first() or matches_r1.filter(player2=p1).first()
            # Find match for P2
            m2 = matches_r1.filter(player1=p2).first() or matches_r1.filter(player2=p2).first()

            if m1 and m2:
                # If it's the same match -> simple side swap
                if m1 == m2:
                    m1.player1, m1.player2 = m1.player2, m1.player1
                    m1.save()
                else:
                    # Different matches -> Cross swap
                    # 1. Where is p1 in m1?
                    if m1.player1 == p1:
                        m1.player1 = p2
                    else:
                        m1.player2 = p2

                    # 2. Where is p2 in m2?
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

    # 1. GET KNOCKOUT STAGE
    # Must find KnockoutStage assigned to this tournament.
    # Using .first(), assuming there is one (standard in tournaments).
    knockout_stage = competition.knockoutstage_stages.first()

    if not knockout_stage:
        messages.error(request, "Knockout stage not found!")
        return redirect('competition_detail', pk=competition.id)

    if request.method == 'POST':
        # CHANGE: Passing 'stage', not 'competition'
        form = SubstitutePlayerForm(request.POST, stage=knockout_stage, owner=request.user)

        if form.is_valid():
            p_out = form.cleaned_data['player_out']
            p_in = form.cleaned_data['player_in']

            with transaction.atomic():
                # A. Update tournament participants list (M2M on Competition model)
                competition.players.remove(p_out)
                competition.players.add(p_in)

                # B. Find matches in knockout stage
                matches_to_fix = Match.objects.filter(
                    knockout_stage=knockout_stage
                ).filter(
                    Q(player1=p_out) | Q(player2=p_out)
                )

                # C. Substitution in matches
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
                        match.save()  # MatchPlayer repair
                        count += 1

                messages.success(request, f"Successfully substituted {p_out} with {p_in} in {count} matches.")
                return redirect('competition_detail', pk=competition.id)
    else:
        # CHANGE: Passing 'stage' here too
        form = SubstitutePlayerForm(stage=knockout_stage, owner=request.user)

    return render(request, 'substitute_player.html', {
        'form': form,
        'competition': competition,
        'stage_name': 'Knockout Stage'
    })


# 1. TOKEN GENERATION (For Guest)
@login_required
def generate_token(request):
    """Generates a 6-digit code valid for 90 seconds and sends it back (e.g., to a modal)."""
    # Remove old user tokens to avoid clutter
    SharingToken.objects.filter(owner=request.user).delete()

    # Generate digits
    new_code = get_random_string(length=6, allowed_chars='0123456789')

    SharingToken.objects.create(
        owner=request.user,
        code=new_code
    )

    # If AJAX request, return JSON, but here simple redirect/message
    # In practice, best as API, but let's keep it simple for now:
    messages.success(request, f"Your Code: {new_code} (Valid for 90 seconds)")
    # Redirect to where they came from (e.g., profile)
    return redirect(request.META.get('HTTP_REFERER', 'player_list'))


# 2. IMPORTING PLAYERS (For Organizer)


@login_required
def import_players_to_competition(request, comp_id):
    competition = get_object_or_404(Competition, pk=comp_id)

    code_form = ImportCodeForm(request.POST or None)
    select_form = None
    token_owner = None

    if request.method == 'POST':
        # --- STEP 1: Code Verification ---
        if 'check_code' in request.POST and code_form.is_valid():
            code = code_form.cleaned_data['code']
            try:
                token = SharingToken.objects.get(code=code)
                if token.is_valid():
                    token_owner = token.owner
                    # Find players of the token owner
                    found_players = Player.objects.filter(owner=token_owner)

                    if not found_players.exists():
                        messages.warning(request, "Code valid, but user has no players.")
                    else:
                        select_form = SelectImportedPlayersForm(found_players=found_players)
                else:
                    code_form.add_error('code', "Code expired.")
            except SharingToken.DoesNotExist:
                code_form.add_error('code', "Invalid code.")

        # --- STEP 2: Import (Cloning as GUEST) ---
        elif 'confirm_import' in request.POST:
            player_ids = request.POST.getlist('selected_players')
            if player_ids:
                source_players = Player.objects.filter(id__in=player_ids)
                count = 0

                for source in source_players:
                    suffix = f" ({source.owner.username})"

                    # Name logic (to be unique and readable)
                    new_last_name = source.last_name + suffix if source.last_name else ""
                    new_first_name = source.first_name
                    new_nickname = source.nickname

                    if not new_last_name:
                        if new_nickname:
                            new_nickname += suffix
                        else:
                            new_first_name += suffix

                    # Check tournament conflict (is this player already here?)
                    # Check by name/surname OR by OneToOne relation with User (if exists)
                    is_conflict = False
                    if source.user:
                        is_conflict = competition.players.filter(user=source.user).exists()

                    # You can add string name check here if you want to be very strict

                    if not is_conflict:
                        # CREATE CLONE-GUEST
                        new_guest = Player.objects.create(
                            owner=request.user,
                            # user=source.user,  <-- REMOVE THIS (Clone cannot be linked to the original User account)
                            cloned_from=source,  # <--- ADDING THIS (Our new bridge)
                            is_guest=True,
                            first_name=source.first_name,
                            # Typo in variables here, better to take straight from source or your variables above
                            last_name=new_last_name,  # Using your suffix logic
                            nickname=new_nickname,  # Using your suffix logic
                            # photo=source.photo
                        )
                        # Add to tournament
                        competition.players.add(new_guest)
                        count += 1

                messages.success(request, f"Imported {count} guests to the tournament.")
                return redirect('competition_detail', pk=competition.id)
            else:
                messages.error(request, "No players selected.")

    return render(request, 'import_players.html', {
        'competition': competition,  # Important for Cancel button
        'code_form': code_form,
        'select_form': select_form,
        'token_owner': token_owner
    })


@login_required
def import_guest_for_match(request):
    """
    Imports guest specifically for a single match.
    On success returns to add_match with parameter ?guest=ID
    """
    code_form = ImportCodeForm(request.POST or None)

    # If GET request (show form)
    if request.method == 'GET':
        return render(request, 'import_players.html', {
            'code_form': code_form,
            'is_match_import': True  # Flag for template
        })

    # If POST request (confirm code)
    if request.method == 'POST':
        if 'check_code' in request.POST and code_form.is_valid():
            code = code_form.cleaned_data['code']
            try:
                token = SharingToken.objects.get(code=code)
                if token.is_valid():
                    # Show selection form (same mechanism as before)
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
                # Take first selected (match is usually 1 vs 1)
                # Loop handles multiple selections, taking the last one as "Active"
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

                            # Create Guest (is_guest=True)
                            new_guest = Player.objects.create(
                                owner=request.user,
                                # user=source.user,  <-- REMOVE THIS
                                cloned_from=source,  # <--- ADD THIS
                                is_guest=True,
                                first_name=new_first_name,
                                last_name=new_last_name,
                                nickname=new_nickname,
                            )
                    last_created_id = new_guest.id

                messages.success(request, "Guest imported for the match.")
                # RETURN TO ADD MATCH WITH PLAYER ID
                return redirect(f"{reverse('add_match')}?guest_id={last_created_id}")
            else:
                messages.error(request, "No players selected.")

    return render(request, 'import_players.html', {'code_form': code_form})


@login_required
def my_global_stats(request):
    """
    Sums statistics from all player 'avatars' (Original + Clones owned by others).
    """
    # Find all player instances linked to your User account
    my_avatars = Player.objects.filter(user=request.user)

    # Aggregate data
    stats = my_avatars.aggregate(
        total_wins=Sum('matches_won'),
        total_matches=Sum('matches_played'),
        global_max_break=Max('highest_break'),
        total_centuries=Sum('centuries_count'),
        total_points=Sum('total_career_points')
    )

    return render(request, 'global_stats.html', {
        'stats': stats,
        'avatars_count': my_avatars.count()  # How many times you were cloned/used
    })


@login_required
def competition_ranking(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    # Optional: Recalculate only if tournament finished or on demand.
    # But for safety, let's always recalculate on entry (or add "Recalculate" button)
    calculate_competition_results(competition)

    results = CompetitionResult.objects.filter(competition=competition).order_by('rank', 'player__last_name')

    return render(request, 'competition_ranking.html', {
        'competition': competition,
        'results': results
    })


@login_required
def player_match_history(request, pk):
    player = get_object_or_404(Player, pk=pk)

    # 1. Fetch ALL matches of the player
    matches_qs = Match.objects.filter(
        Q(player1=player) | Q(player2=player)
    ).order_by('-date', '-time')

    # --- H2H FILTER (Head-to-Head) ---
    opponent_id = request.GET.get('opponent')
    opponent = None
    stats = {}

    if opponent_id:
        opponent = get_object_or_404(Player, pk=opponent_id)
        # Filter only matches with this opponent
        matches_qs = matches_qs.filter(Q(player1=opponent) | Q(player2=opponent))

        # Calculate quick H2H stats
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

    # 2. List of all opponents for dropdown (for filter)
    # Get IDs of all opponents from player's matches
    # This query might be heavy with thousands of players, but OK for now
    p1_ids = Match.objects.filter(player2=player).values_list('player1', flat=True)
    p2_ids = Match.objects.filter(player1=player).values_list('player2', flat=True)
    all_opponent_ids = list(set(list(p1_ids) + list(p2_ids)))

    possible_opponents = Player.objects.filter(id__in=all_opponent_ids).order_by('last_name')

    # --- PAGINATION (LOAD MORE) ---
    paginator = Paginator(matches_qs, 10)  # 10 matches per "page" (click)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 3. If AJAX request (Load More), return only table rows
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render_to_string('partials/match_rows.html', {
            'matches': page_obj,
            'player': player
        }, request=request)

        return JsonResponse({
            'html': html,
            'has_next': page_obj.has_next()
        })

    # 4. Standard page render
    return render(request, 'player_match_history.html', {
        'player': player,
        'matches': page_obj,  # First page
        'possible_opponents': possible_opponents,
        'selected_opponent': opponent,
        'stats': stats
    })


@login_required
def equipment_list(request, player_id):
    player = get_object_or_404(Player, pk=player_id)

    # Split into CURRENT and ARCHIVED equipment
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

            # --- AUTO-ARCHIVING LOGIC ---
            # If new equipment is ACTIVE (no end_date), close old one of same type
            if new_eq.end_date is None:
                old_active = Equipment.objects.filter(
                    player=player,
                    item_type=new_eq.item_type,
                    end_date__isnull=True
                )
                # Set end date of old to start date of new
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

    if request.method == 'POST':
        # If user clicked "Yes, Delete" on confirmation page
        equipment.delete()
        messages.success(request, f"Equipment '{equipment.name}' deleted.")
        return redirect('equipment_list', player_id=player_id)

    # If standard entry (trash icon click) -> show confirmation page
    return render(request, 'equipment/confirm_delete.html', {
        'item': equipment
    })


@login_required
def use_equipment_again(request, pk):
    # 1. Get old equipment from archive
    old_item = get_object_or_404(Equipment, pk=pk)

    # --- NEW: Save list of photos of old item ---
    # Must do this NOW, before resetting old_item ID
    photos_to_copy = list(old_item.photos.all())

    # 2. Archive CURRENT equipment of same type
    current_active = Equipment.objects.filter(
        player=old_item.player,
        item_type=old_item.item_type,
        end_date__isnull=True
    )
    for active in current_active:
        active.end_date = date.today()
        active.save()
        messages.info(request, f"Moved {active.name} to archive.")

    # 3. Create NEW equipment based on old one
    old_item.pk = None
    old_item.start_date = date.today()
    old_item.end_date = None

    # Add reactivation note
    old_item.notes = (old_item.notes or "") + f"\n[Re-activated on {date.today()}]"

    old_item.save()  # At this point old_item is a NEW DB entry with new ID

    # 4. Copy photos
    for photo in photos_to_copy:
        EquipmentPhoto.objects.create(
            equipment=old_item,  # Assign to this new equipment
            image=photo.image,  # Point to same file on disk (save space)
            is_main=photo.is_main  # Keep info if it was main photo
        )

    messages.success(request, f"Welcome back! {old_item.name} is active again (with photos).")
    return redirect('equipment_list', player_id=old_item.player.id)


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
            # 1. Get email from form (the one user just typed)
            new_email = u_form.cleaned_data.get('email')

            # 2. Force get the old email directly from the database for reliable comparison
            from django.contrib.auth.models import User
            db_user = User.objects.get(pk=request.user.pk)
            current_email = db_user.email

            if new_email != current_email:
                # WE SAVE THE USER without changing the email!
                user = u_form.save(commit=False)
                # We restore the old email in the object that goes to the database
                user.email = current_email
                user.save()

                # We save the new email to the temporary field in the profile
                profile = p_form.save(commit=False)
                profile.new_email_temp = new_email
                profile.email_confirmed = False  # Reset verification for the new address
                profile.save()

                # 3. Send confirmation link to the NEW email address
                current_site = get_current_site(request)
                subject = 'Confirm your new email address'
                message = render_to_string('acc_active_email.html', {
                    'user': user,
                    'domain': current_site.domain,
                    'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                    'token': account_activation_token.make_token(user),
                })

                # We explicitly send the email to new_email_temp instead of user.email
                email = EmailMessage(subject, message, to=[new_email])
                email.send()

                messages.warning(request,
                                 f'A confirmation link has been sent to {new_email}. '
                                 f'Please confirm it to change your address.')
            else:
                # If the email hasn't changed, we save everything as usual
                u_form.save()
                p_form.save()
                messages.success(request, 'Your profile has been updated!')

            return redirect('profile_settings')
        else:
            messages.error(request, 'Update failed. Please correct the errors below.')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    context = {'u_form': u_form, 'p_form': p_form}
    return render(request, 'users/profile_settings.html', context)


@login_required
def export_data_excel(request):
    workbook = openpyxl.Workbook()

    # =========================================================
    # SHEET 1: GENERAL STATS (Dashboard)
    # =========================================================
    ws_dash = workbook.active
    ws_dash.title = "General Stats"
    ws_dash.append(['Metric', 'Value'])

    total_matches = Match.objects.filter(owner=request.user, status='FINISHED').count()
    total_players = Player.objects.filter(owner=request.user).count()
    total_tournaments = Competition.objects.filter(owner=request.user).count()

    # Also adding training count to dashboard
    total_trainings = TrainingSession.objects.filter(owner=request.user).count()

    # --- Club Highest Break ---
    all_players = Player.objects.filter(owner=request.user)
    all_breaks_values = []
    for p in all_players:
        val = p.highest_break() if callable(getattr(p, 'highest_break', None)) else p.highest_break
        all_breaks_values.append(val or 0)
    global_max_break = max(all_breaks_values) if all_breaks_values else 0

    ws_dash.append(['Total Finished Matches', total_matches])
    ws_dash.append(['Total Training Sessions', total_trainings])
    ws_dash.append(['Total Players Database', total_players])
    ws_dash.append(['Total Tournaments', total_tournaments])
    ws_dash.append(['Club Highest Break', global_max_break])

    # =========================================================
    # SHEET 2: FULL PLAYER STATISTICS
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

        fastest = p.formatted_fastest_frame() if callable(
            getattr(p, 'formatted_fastest_frame', None)) else p.formatted_fastest_frame
        longest = p.formatted_longest_frame() if callable(
            getattr(p, 'formatted_longest_frame', None)) else p.formatted_longest_frame
        avg_frame = p.formatted_avg_frame() if callable(
            getattr(p, 'formatted_avg_frame', None)) else p.formatted_avg_frame
        ast = p.formatted_avg_shot_time() if callable(
            getattr(p, 'formatted_avg_shot_time', None)) else p.formatted_avg_shot_time

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
    # SHEET 3: TOURNAMENTS ARCHIVE
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
    # SHEET 4: REFEREES
    # =========================================================
    ws_ref = workbook.create_sheet(title="Referees")
    ws_ref.append(['Name', 'License', 'Matches Officiated', 'Last Match Date'])

    referees = Referee.objects.filter(owner=request.user)
    for r in referees:
        ref_matches = Match.objects.filter(owner=request.user, status='FINISHED', referees=r).order_by('-date')
        count = ref_matches.count()
        last_match = ref_matches.first()
        last_date = last_match.date.strftime('%Y-%m-%d') if last_match and last_match.date else "-"
        ws_ref.append([str(r), r.license_number, count, last_date])

    # =========================================================
    # SHEET 5: MATCH HISTORY
    # =========================================================
    ws_matches = workbook.create_sheet(title="Match History")
    ws_matches.append(['Date', 'Player 1', 'Score', 'Player 2', 'Winner'])

    matches = Match.objects.filter(owner=request.user, status='FINISHED').order_by('-date')

    for m in matches:
        date_str = m.date.strftime('%Y-%m-%d') if m.date else ""
        score_str = f"{m.final_score_player1} - {m.final_score_player2}"
        ws_matches.append([date_str, str(m.player1), score_str, str(m.player2), str(m.winner)])

    # =========================================================
    # SHEET 6: TRAINING DIARY (NEW)
    # =========================================================
    ws_train = workbook.create_sheet(title="Training Diary")
    ws_train.append(['Date', 'Type', 'Venue', 'Duration (min)', 'Rating (1-10)', 'Notes'])

    trainings = TrainingSession.objects.filter(owner=request.user).order_by('-date', '-created_at')

    for t in trainings:
        t_date = t.date.strftime('%Y-%m-%d') if t.date else ""
        t_type = t.get_session_type_display()
        t_venue = t.venue.name if t.venue else "Unknown/Private"
        t_rating = f"{t.rating}/10"
        # Shorten notes to 100 chars in Excel to avoid mess
        t_notes = str(t.notes)[:100] + "..." if t.notes and len(str(t.notes)) > 100 else (t.notes or "")

        ws_train.append([t_date, t_type, t_venue, t.duration_minutes, t_rating, t_notes])

    # =========================================================
    # SAVE
    # =========================================================
    now_str = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    filename = f"snooker_report_{now_str}.xlsx"

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    workbook.save(response)
    return response


@user_passes_test(lambda u: u.is_superuser)  # Only for Superuser!
def admin_backup_json(request):
    # Create memory buffer (virtual file)
    output = StringIO()

    # Call dumpdata command (db dump)
    # exclude: skip sessions and admin logs, as they are junk taking up space
    # indent: nice indentation in file (readability)
    call_command(
        'dumpdata',
        exclude=['contenttypes', 'sessions', 'admin.logentry'],
        indent=2,
        stdout=output
    )

    # Rewind buffer to start to read it
    output.seek(0)

    # Prepare file for download
    now_str = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    filename = f"FULL_DB_BACKUP_{now_str}.json"

    response = HttpResponse(output.read(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename={filename}'

    return response


# --- 1. TRAINING LIST ---
class TrainingListView(LoginRequiredMixin, ListView):
    model = TrainingSession
    template_name = 'training_list.html'
    context_object_name = 'sessions'
    paginate_by = 10

    def get_queryset(self):
        # 1. Check if player ID is in URL
        player_id = self.kwargs.get('pk')

        if player_id:
            # If yes: filter trainings ONLY for this player
            self.player = get_object_or_404(Player, pk=player_id, owner=self.request.user)
            return TrainingSession.objects.filter(player=self.player).order_by('-date', '-created_at')
        else:
            # If not (general view): show all user trainings
            self.player = None
            return TrainingSession.objects.filter(owner=self.request.user).order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        # Pass 'player' object to template so buttons work
        context = super().get_context_data(**kwargs)
        context['player'] = getattr(self, 'player', None)
        return context

# --- 2. ADD TRAINING ---
class TrainingCreateView(LoginRequiredMixin, CreateView):
    model = TrainingSession
    form_class = TrainingSessionForm
    template_name = 'training_form.html'

    def get_success_url(self):
        # Redirect to training list of THE player selected in form
        return reverse('player_training_list', kwargs={'pk': self.object.player.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user

        # CHECK IF 'player_id' IS IN URL
        if 'player_id' in self.kwargs:
            # If yes, get player and pass to form
            from .models import Player
            from django.shortcuts import get_object_or_404

            player = get_object_or_404(Player, pk=self.kwargs['player_id'], owner=self.request.user)
            kwargs['preselected_player'] = player

        return kwargs

    def form_valid(self, form):
        # Automatically assign owner (owner = user)
        form.instance.owner = self.request.user
        return super().form_valid(form)

# --- 3. EDIT TRAINING ---
class TrainingUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = TrainingSession
    form_class = TrainingSessionForm
    template_name = 'training_form.html' # Use the same template as for adding

    def get_success_url(self):
        return reverse('player_training_list', kwargs={'pk': self.object.player.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def test_func(self):
        # Security: Only owner can edit their training
        session = self.get_object()
        return session.owner == self.request.user

# --- 4. DELETE TRAINING ---
class TrainingDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = TrainingSession
    template_name = 'training_confirm_delete.html'

    def get_success_url(self):
        # Return to list of player who owned the deleted training
        return reverse('player_training_list', kwargs={'pk': self.object.player.pk})

    def test_func(self):
        # Security: Only owner can delete
        session = self.get_object()
        return session.owner == self.request.user


# --- 5. TRAINING DETAILS (PREVIEW) ---
class TrainingDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = TrainingSession
    template_name = 'training_detail.html'
    context_object_name = 'session'

    def test_func(self):
        # Only owner can view their notes
        session = self.get_object()
        return session.owner == self.request.user


# --- 6. TRAINING STATISTICS (PLAYER DASHBOARD) ---
class TrainingStatsView(LoginRequiredMixin, TemplateView):
    template_name = 'training_stats.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. Get player from URL (PK/ID)
        # Assuming urls.py has: path('player/<int:pk>/stats/', ...)
        player_id = self.kwargs.get('pk')
        player = get_object_or_404(Player, pk=player_id)

        # Optional security: Is this your player?
        # if player.owner != self.request.user: raise PermissionDenied

        # 2. Get filter parameters (Year / Month)
        today = datetime.date.today()
        try:
            selected_year = int(self.request.GET.get('year', today.year))
        except ValueError:
            selected_year = today.year

        try:
            selected_month = int(self.request.GET.get('month', 0))
        except ValueError:
            selected_month = 0

        # 3. Filter QuerySet BY PLAYER (not by User!)
        stats_qs = TrainingSession.objects.filter(player=player, date__year=selected_year)

        # If specific month selected, narrow down
        if selected_month > 0:
            stats_qs = stats_qs.filter(date__month=selected_month)

        # 4. CALCULATIONS (KPI)
        aggregates = stats_qs.aggregate(
            total_minutes=Sum('duration_minutes'),
            avg_rating=Avg('rating'),
            total_sessions=Count('id')
        )

        total_minutes = aggregates['total_minutes'] or 0
        total_hours = round(total_minutes / 60, 1)
        avg_rating = aggregates['avg_rating'] or 0

        # 5. CHART DATA
        focus_data = stats_qs.values('main_focus').annotate(minutes=Sum('duration_minutes')).order_by('-minutes')

        focus_labels = []
        focus_values = []
        focus_dict = dict(TrainingSession.FOCUS_CHOICES)

        for item in focus_data:
            readable_name = focus_dict.get(item['main_focus'], item['main_focus'])
            focus_labels.append(readable_name)
            focus_values.append(item['minutes'])

        # 6. Pass everything to context
        context.update({
            'player': player,  # Pass player to display their name
            'selected_year': selected_year,
            'selected_month': selected_month,
            'years_range': range(2023, today.year + 2),

            'total_hours': total_hours,
            'total_sessions': aggregates['total_sessions'],
            'avg_rating': round(avg_rating, 1),

            'chart_focus_labels': focus_labels,
            'chart_focus_values': focus_values,

            'sessions_list': stats_qs.order_by('-date')
        })

        return context


class CompetitionMatchListPrintView(LoginRequiredMixin, DetailView):
    model = Competition
    template_name = "print/match_list.html"
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. Get matches (use select_related for performance)
        matches_qs = Match.objects.filter(
            Q(group_stage__competition=self.object) |
            Q(knockout_stage__competition=self.object)
        ).select_related('group', 'knockout_stage', 'player1', 'player2').order_by('date', 'time')

        # 2. Convert QuerySet to list and add "nice names"
        matches = []
        for m in matches_qs:
            # Default name (if nothing matches)
            display_name = ""

            if m.group:
                display_name = f"Gr {m.group.name}"

            elif m.knockout_stage:
                # --- ROUND NAMING LOGIC ---

                # A. 3rd place match (usually round 99 or name contains "3rd")
                if m.round_number == 99 or (m.knockout_name and "3rd" in m.knockout_name):
                    display_name = "3rd Place"
                else:
                    # B. Calculate name based on total number of rounds
                    # If tournament has 2 rounds (4 players):
                    # Round 1 (2-1=1) -> 1/2
                    # Round 2 (2-2=0) -> Final

                    total = m.knockout_stage.num_rounds or 0
                    current = m.round_number
                    diff = total - current

                    if diff == 0:
                        display_name = "Final"
                    elif diff == 1:
                        display_name = "1/2"
                    elif diff == 2:
                        display_name = "1/4"
                    elif diff == 3:
                        display_name = "1/8"
                    else:
                        display_name = f"Rd {current}"

            # Attach name to object (as new attribute 'print_stage_name')
            m.print_stage_name = display_name
            matches.append(m)

        context['matches'] = matches
        context['now'] = timezone.now()
        return context


class CompetitionGroupsPrintView(LoginRequiredMixin, DetailView):
    model = Competition
    template_name = "print/groups.html"
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Query: "Get me GroupStage belonging to this tournament (self.object)"
        group_stage = GroupStage.objects.filter(competition=self.object).first()

        if group_stage:
            # If stage found, get its groups
            groups = group_stage.groups.all().prefetch_related(
                'standings__player',
                'matches__player1',
                'matches__player2'
            ).order_by('name')
            context['groups'] = groups
        else:
            context['groups'] = []

        context['now'] = timezone.now()
        return context


class CompetitionBracketPrintView(LoginRequiredMixin, DetailView):
    model = Competition
    template_name = "print/bracket.html"
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        knockout_stage = KnockoutStage.objects.filter(competition=self.object).first()

        rounds_data = []
        match_3rd_place = None

        if knockout_stage:
            # Get matches
            matches = Match.objects.filter(knockout_stage=knockout_stage).order_by('round_number', 'id')

            # Find 3rd place match (assume round 99 or name)
            match_3rd_place = matches.filter(
                Q(round_number=99) | Q(knockout_name__icontains="3rd")
            ).first()

            total_rounds = knockout_stage.num_rounds

            # --- CHANGE: Show max last 5 rounds (i.e., from Last 32 to Final) ---
            # If you want from Last 16, change 4 to 3.
            # If you want from Last 32, leave 4 (because final is 0 'back', so 4 back is 5 rounds)
            start_round = max(1, total_rounds - 3)

            for r in range(start_round, total_rounds + 1):
                # Filter matches only for given round
                current_round_matches = matches.filter(round_number=r)

                # --- NAMING LOGIC (same as schedule) ---
                diff = total_rounds - r
                if diff == 0:
                    round_name = "Final"
                elif diff == 1:
                    round_name = "Semi-Finals (1/2)"
                elif diff == 2:
                    round_name = "Quarter-Finals (1/4)"
                elif diff == 3:
                    round_name = "Last 16 (1/8)"
                else:
                    round_name = f"Round {r}"

                rounds_data.append({
                    'number': r,
                    'name': round_name,  # <--- New field with nice name
                    'matches': current_round_matches
                })

        context['rounds_data'] = rounds_data
        context['match_3rd_place'] = match_3rd_place  # Pass separately to template
        context['now'] = timezone.now()
        return context


class CustomLoginView(LoginView):
    template_name = 'login.html'

    def post(self, request, *args, **kwargs):
        # 1. Check if user (IP) is blocked
        ip = request.META.get('REMOTE_ADDR')
        if cache.get(f'block_ip_{ip}'):
            # If blocked - return error page without checking password
            form = self.get_form()
            form.add_error(None, "Too many failed attempts. Please try again in 5 minutes.")
            return self.render_to_response(self.get_context_data(form=form))

        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        ip = self.request.META.get('REMOTE_ADDR')
        key = f'login_errors_{ip}'
        attempts = cache.get(key, 0) + 1

        cache.set(key, attempts, 300)

        if attempts >= 5:
            cache.set(f'block_ip_{ip}', True, 300)

            # --- Clear standard Django error ("Please enter correct...") ---
            # So user sees only specifics: "Locked"
            if form._errors:
                form._errors.clear()

            form.add_error(None, "Account locked due to multiple failed attempts. Try again in 5 minutes.")

        return super().form_invalid(form)

    def form_valid(self, form):
        # 3. This triggers when you enter CORRECT password
        # Clear error history
        ip = self.request.META.get('REMOTE_ADDR')
        cache.delete(f'login_errors_{ip}')
        cache.delete(f'block_ip_{ip}')
        return super().form_valid(form)

def scoreboard(request):
    """
    Displays the video wall (Scoreboard).
    Data is sent live via JavaScript (BroadcastChannel),
    so this view doesn't need to fetch anything from the database.
    """
    return render(request, 'scoreboard.html')

@login_required
@require_POST
def complete_tutorial(request):
    """AJAX endpoint to disable tutorial for the user."""
    request.user.profile.show_tutorial = False
    request.user.profile.save()
    return JsonResponse({'status': 'ok'})