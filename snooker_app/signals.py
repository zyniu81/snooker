from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist  # <--- IMPORTANT IMPORT
from .models import Match, MatchPlayer, GroupStanding, Competition, GroupStage, KnockoutStage


def recalculate_group_standings(group):
    """
    Resets and recalculates the table for a specific group based on finished matches.
    Fetches scoring rules (win/draw) from the stage (GroupStage).
    """
    # Safeguard: If group has no assigned stage (orphan), stop
    try:
        stage = group.stage
    except ObjectDoesNotExist:
        return

    # 1. Get scoring settings from Stage
    pts_win = stage.points_for_win
    pts_draw = stage.points_for_draw
    pts_loss = stage.points_for_loss

    # 2. Get all table rows for this group (to update them)
    standings = {s.player_id: s for s in group.standings.all()}

    # 3. RESET statistics to zero (to avoid double counting)
    for s in standings.values():
        s.matches_played = 0
        s.matches_won = 0
        s.matches_drawn = 0
        s.matches_lost = 0
        s.frames_won = 0
        s.frames_lost = 0
        s.points = 0
        s.small_points_scored = 0
        s.small_points_conceded = 0
        s.highest_break = 0
        # We do not reset is_qualified manually

    # 4. Get FINISHED matches in this group
    finished_matches = group.matches.filter(status='FINISHED')

    for match in finished_matches:
        # Get players and their results from Match model
        mps = list(match.matchplayer_set.all().order_by('position'))
        if len(mps) < 2:
            continue

        p1 = mps[0].player
        p2 = mps[1].player

        if p1.id not in standings or p2.id not in standings:
            continue

        s1 = standings[p1.id]
        s2 = standings[p2.id]

        # -- CALCULATING STATISTICS --

        # Matches played
        s1.matches_played += 1
        s2.matches_played += 1

        # Frames
        f1 = match.final_score_player1
        f2 = match.final_score_player2

        s1.frames_won += f1
        s1.frames_lost += f2
        s2.frames_won += f2
        s2.frames_lost += f1

        # Points (Small Points)
        sp1 = match.total_points_player1
        sp2 = match.total_points_player2

        s1.small_points_scored += sp1
        s1.small_points_conceded += sp2

        s2.small_points_scored += sp2
        s2.small_points_conceded += sp1

        # Highest Break in Group
        if match.highest_break_p1 > s1.highest_break:
            s1.highest_break = match.highest_break_p1
        if match.highest_break_p2 > s2.highest_break:
            s2.highest_break = match.highest_break_p2

        # Match Points (Win/Draw/Loss)
        if f1 > f2:
            s1.matches_won += 1
            s1.points += pts_win
            s2.matches_lost += 1
            s2.points += pts_loss
        elif f2 > f1:
            s2.matches_won += 1
            s2.points += pts_win
            s1.matches_lost += 1
            s1.points += pts_loss
        else:
            # Draw
            s1.matches_drawn += 1
            s1.points += pts_draw
            s2.matches_drawn += 1
            s2.points += pts_draw

    # 5. Save everything to database
    GroupStanding.objects.bulk_update(standings.values(), [
        'matches_played', 'matches_won', 'matches_drawn', 'matches_lost',
        'frames_won', 'frames_lost', 'points',
        'small_points_scored', 'small_points_conceded', 'highest_break'
    ])


def update_records(match):
    """
    Checks if a break record for the Stage or Tournament was set in the match.
    """
    breaks = []
    if match.highest_break_p1 > 0:
        mp1 = match.matchplayer_set.filter(position=1).first()
        if mp1: breaks.append((match.highest_break_p1, mp1.player))

    if match.highest_break_p2 > 0:
        mp2 = match.matchplayer_set.filter(position=2).first()
        if mp2: breaks.append((match.highest_break_p2, mp2.player))

    if not breaks:
        return

    # Get context safely
    try:
        stage = match.get_stage()
    except ObjectDoesNotExist:
        return

    competition = stage.competition if stage else None

    for points, player in breaks:
        # 1. STAGE Record
        if stage and points > stage.highest_break_points:
            stage.highest_break_points = points
            stage.highest_break_player = player
            stage.save()

        # 2. TOURNAMENT Record
        if competition and points > competition.highest_break_points:
            competition.highest_break_points = points
            competition.highest_break_player = player
            competition.save()


@receiver(post_save, sender=Match)
def match_post_save_handler(sender, instance, created, raw=False,  **kwargs):
    """
    Main signal. Triggers after saving a match.
    """

    if raw:
        return

    # 1. If group match -> Recalculate table for this group
    if instance.group:
        transaction.on_commit(lambda: recalculate_group_standings(instance.group))

    # 2. Check records (Max Break)
    if instance.status == 'FINISHED':
        transaction.on_commit(lambda: update_records(instance))


# --- THERE WAS AN ERROR HERE ---
@receiver(post_delete, sender=Match)
def match_post_delete_handler(sender, instance, **kwargs):
    """
    Handles match deletion.
    Must be robust against situations where the entire Tournament is deleted (Group disappears too).
    """
    try:
        # Try to get the group.
        # If deleting concurrently (Tournament -> Group -> Match),
        # the Group no longer exists in DB at this point.
        # Django raises ObjectDoesNotExist when accessing instance.group
        if instance.group:
            recalculate_group_standings(instance.group)

    except ObjectDoesNotExist:
        # If group doesn't exist, it means it was deleted earlier,
        # or we are deleting the whole tournament. In both cases - no need to recalculate.
        # Just ignore the error.
        pass


@receiver(post_save, sender=Match)
def advance_knockout_winner(sender, instance, created, raw=False, **kwargs):

    if raw:
        return
    """
    Automatically advances the winner to the next round in the knockout bracket.
    """
    # Only act on finished knockout matches that have a winner
    if not instance.knockout_stage or not instance.is_finished or not instance.winner:
        return

    stage = instance.knockout_stage
    current_round = instance.round_number

    # --- MAIN LOGIC: ADVANCE TO NEXT ROUND ---

    # 1. Get all matches of THIS round, sorted by ID (creation order)
    current_round_matches = Match.objects.filter(
        knockout_stage=stage,
        round_number=current_round
    ).order_by('id')

    # 2. Check which match in sequence is our finished match (index 0, 1, 2...)
    matches_list = list(current_round_matches)
    try:
        current_match_index = matches_list.index(instance)
    except ValueError:
        return  # Something weird, match not in list

    # 3. Calculate target: Next round, Match at index (our_index // 2)
    next_round = current_round + 1
    target_match_index = current_match_index // 2

    # Get matches of NEXT round
    next_round_matches = Match.objects.filter(
        knockout_stage=stage,
        round_number=next_round
    ).order_by('id')

    # If target exists (i.e. not the final)
    if target_match_index < len(next_round_matches):
        target_match = next_round_matches[target_match_index]

        # Even index (0, 2...) goes to Player 1 (Top of bracket)
        # Odd index (1, 3...) goes to Player 2 (Bottom of bracket)
        if current_match_index % 2 == 0:
            target_match.player1 = instance.winner
        else:
            target_match.player2 = instance.winner

        target_match.save()

    # --- ADDITIONAL LOGIC: 3RD PLACE MATCH ---
    # If this is Semi-final (penultimate round) and we have a 3rd place match
    total_rounds = stage.num_rounds
    if stage.has_third_place_match and current_round == (total_rounds - 1):
        # Find loser
        loser = instance.player1 if instance.winner == instance.player2 else instance.player2

        if loser:
            # Look for 3rd place match (has special round_number=99 or name)
            third_place_match = Match.objects.filter(
                knockout_stage=stage,
                knockout_name="3rd Place Match"
            ).first()

            if third_place_match:
                if current_match_index % 2 == 0:
                    third_place_match.player1 = loser
                else:
                    third_place_match.player2 = loser
                third_place_match.save()