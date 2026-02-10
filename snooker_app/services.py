from django.db.models import Sum, Min, Max, Avg, Q
from .models import Player, MatchPlayer, Frame, CompetitionResult, KnockoutStage, GroupStage, Match
from datetime import timedelta
from django.db import transaction


def update_career_stats(player):
    """
    Recalculates player statistics based on match history.
    SUPPORTS CLONES: Counts own matches and matches played by clones of this player.
    """

    # 1. Find finished matches of this player AND their clones
    # We use Q to fetch matches where player=player OR player__cloned_from=player
    match_participations = MatchPlayer.objects.filter(
        Q(player=player) | Q(player__cloned_from=player),
        match__status='FINISHED'
    ).select_related('match')

    # Sort matches chronologically
    matches = sorted([mp.match for mp in match_participations], key=lambda x: x.created_at)

    matches_played_count = len(matches)

    # --- CAREER GLOBAL VARIABLES ---
    career_matches_won = 0
    career_matches_lost = 0

    career_deciders_played = 0
    career_deciders_won = 0
    career_whitewashes = 0

    career_frames_won = 0
    career_frames_lost = 0
    career_total_points = 0

    # Technique
    career_total_pots = 0
    career_total_misses = 0
    career_total_safe_succ = 0
    career_total_safe_attempts = 0
    career_total_time = timedelta(0)
    career_total_shots_time = 0

    # Breaks
    career_centuries = 0
    career_fifties = 0
    career_max_breaks = 0
    career_highest_break = 0
    career_break_histogram = {f"{i}+": 0 for i in range(10, 150, 10)}

    # Streaks
    current_match_streak = 0
    max_match_streak = 0
    current_frame_streak = 0
    max_frame_streak = 0

    # --- MAIN MATCH LOOP ---
    for m in matches:
        # 1. Determine who the player was in this match (P1 or P2?)
        # NOTE: Here we also check if P1/P2 is a clone of our player
        is_p1 = (m.player1 == player) or (getattr(m.player1, 'cloned_from', None) == player)
        is_p2 = (m.player2 == player) or (getattr(m.player2, 'cloned_from', None) == player)

        if not is_p1 and not is_p2:
            continue

        # 2. Match Result
        # Check if the winner is the player OR their clone
        winner_is_me = (m.winner == player) or (getattr(m.winner, 'cloned_from', None) == player)

        p1_score, p2_score = m.get_real_score()
        frames_played_in_match = p1_score + p2_score

        # --- Streaks (Matches) ---
        if winner_is_me:
            career_matches_won += 1
            current_match_streak += 1
            if current_match_streak > max_match_streak:
                max_match_streak = current_match_streak
        else:
            career_matches_lost += 1
            current_match_streak = 0

        # --- Deciders ---
        if frames_played_in_match == m.number_of_frames and m.number_of_frames >= 3:
            career_deciders_played += 1
            if winner_is_me:
                career_deciders_won += 1

        # --- Whitewashes ---
        if winner_is_me:
            opponent_score = p2_score if is_p1 else p1_score
            if opponent_score == 0:
                career_whitewashes += 1

        # --- FRAME ANALYSIS ---
        match_frames = Frame.objects.filter(match_player__match=m).order_by('frame_number')

        for f in match_frames:
            # -- Frame Victory --
            # Here too we must check if the player OR their clone won
            frame_winner_is_me = (f.winner == player) or (getattr(f.winner, 'cloned_from', None) == player)

            if frame_winner_is_me:
                career_frames_won += 1
                current_frame_streak += 1
                if current_frame_streak > max_frame_streak:
                    max_frame_streak = current_frame_streak
            else:
                career_frames_lost += 1
                current_frame_streak = 0

            # -- Fetching Data --
            # is_p1 was determined above considering clones, so it is OK here
            if is_p1:
                pts = f.points_scored_player1 or 0
                pots = f.potted_balls_player1 or 0
                misses = f.misses_player1 or 0
                safe_succ = f.successful_safety_shots_player1 or 0
                safe_total = f.safety_shot_player1 or 0
                time_shot = f.time_shots_player1 or timedelta(0)
                total_shots = f.total_shots_player1 or 0
                breaks = f.break_points_player1 or []
            else:  # is_p2
                pts = f.points_scored_player2 or 0
                pots = f.potted_balls_player2 or 0
                misses = f.misses_player2 or 0
                safe_succ = f.successful_safety_shots_player2 or 0
                safe_total = f.safety_shot_player2 or 0
                time_shot = f.time_shots_player2 or timedelta(0)
                total_shots = f.total_shots_player2 or 0
                breaks = f.break_points_player2 or []

            # -- Summation --
            career_total_points += pts
            career_total_pots += pots
            career_total_misses += misses
            career_total_safe_succ += safe_succ
            career_total_safe_attempts += safe_total
            if time_shot:
                career_total_time += time_shot
            career_total_shots_time += total_shots

            # -- Break Analysis --
            for b in breaks:
                if b > career_highest_break:
                    career_highest_break = b

                # Counters 147 / 100 / 50 (Disjoint)
                if b >= 147:
                    career_max_breaks += 1
                    career_centuries += 1
                elif b >= 100:
                    career_centuries += 1
                elif b >= 50:
                    career_fifties += 1

                # "Bucket" Histogram (Highest threshold only)
                # E.g. break 64 -> bucket 60. We record only in 60+.
                if b >= 10:
                    bucket = (b // 10) * 10  # Integer division: 64//10 = 6 -> *10 = 60
                    # Safeguard against values over 140
                    if bucket > 140:
                        bucket = 140
                    career_break_histogram[f"{bucket}+"] += 1

    # --- FINAL CALCULATIONS ---
    career_total_attempts = career_total_pots + career_total_misses

    global_pot_success = 0.0
    if career_total_attempts > 0:
        global_pot_success = round((career_total_pots / career_total_attempts) * 100, 2)

    global_safety_success = 0.0
    if career_total_safe_attempts > 0:
        global_safety_success = round((career_total_safe_succ / career_total_safe_attempts) * 100, 2)

    avg_shot_time = None
    if career_total_shots_time > 0:
        avg_shot_time = career_total_time / career_total_shots_time

    # --- SAVING ---
    player.matches_played = matches_played_count
    player.matches_won = career_matches_won
    player.matches_lost = career_matches_lost
    # ... rest of assignments unchanged ...
    player.deciders_played = career_deciders_played
    player.deciders_won = career_deciders_won
    player.whitewashes_count = career_whitewashes

    player.consecutive_matches_won = max_match_streak
    player.current_match_streak = current_match_streak

    player.frames_played = career_frames_won + career_frames_lost
    player.frames_won = career_frames_won
    player.frames_lost = career_frames_lost

    player.consecutive_frames_won = max_frame_streak
    player.current_frame_streak = current_frame_streak

    player.total_career_points = career_total_points
    player.global_pot_success = global_pot_success
    player.global_safety_success = global_safety_success
    player.avg_shot_time = avg_shot_time

    player.highest_break = career_highest_break
    player.centuries_count = career_centuries
    player.fifties_count = career_fifties
    player.max_breaks_count = career_max_breaks
    player.career_break_stats = career_break_histogram

    # --- NEW: FRAME TIME ANALYSIS ---
    time_stats = Frame.objects.filter(match_player__match__in=matches).exclude(time_duration=None).aggregate(
        shortest=Min('time_duration'),
        longest=Max('time_duration'),
        average=Avg('time_duration')
    )

    player.fastest_frame_time = time_stats['shortest']
    player.longest_frame_time = time_stats['longest']
    player.avg_frame_time = time_stats['average']

    player.save()

    # --- TRIGGER FOR ORIGINAL ---
    # If we update a clone, we must also update the original
    if player.cloned_from:
        update_career_stats(player.cloned_from)


def calculate_competition_results(competition):
    """
    Main function generating tournament ranking (CompetitionResult).
    Supports hybrids (Groups -> Knockout) and Knockout only.
    """

    # 1. Clear old results (to avoid duplicates during recalculation)
    CompetitionResult.objects.filter(competition=competition).delete()

    # Set of player IDs who already have an assigned place (to prevent giving them a worse one from an earlier stage)
    processed_player_ids = set()

    # 2. Get stages and REVERSE order (start from Final, end at Qualifiers)
    stages = competition.get_stages()  # This is your sorted() method
    reversed_stages = list(reversed(stages))

    with transaction.atomic():
        for stage in reversed_stages:

            # --- SCENARIO A: KNOCKOUT (CUP) ---
            if isinstance(stage, KnockoutStage):
                process_knockout_stage(competition, stage, processed_player_ids)

            # --- SCENARIO B: GROUP STAGE ---
            elif isinstance(stage, GroupStage):
                process_group_stage(competition, stage, processed_player_ids)


def process_knockout_stage(competition, stage, processed_players):
    """
    Analyzes the bracket.
    In your model: round_number increases (1=1/4, 2=1/2, 3=Final).
    """
    # Check if there was a 3rd place match (round_number=99)
    third_place_match = Match.objects.filter(
        knockout_stage=stage,
        round_number=99,
        status='FINISHED'
    ).first()

    if third_place_match and third_place_match.winner:
        # Winner of 3rd place match
        create_result(competition, third_place_match.winner, 'THIRD_PLACE', 3, processed_players)
        # Loser of 3rd place match -> 4th place
        loser = third_place_match.player1 if third_place_match.winner == third_place_match.player2 else third_place_match.player2
        create_result(competition, loser, 'FOURTH_PLACE', 4, processed_players)

    # Iterate from Final downwards (e.g. round 3, then 2, then 1)
    # stage.num_rounds is e.g. 3 (for quarter-finals)
    for r in range(stage.num_rounds, 0, -1):
        matches = Match.objects.filter(
            knockout_stage=stage,
            round_number=r,
            status='FINISHED'
        )

        is_final = (r == stage.num_rounds)

        for match in matches:
            if not match.winner: continue

            loser = match.player1 if match.winner == match.player2 else match.player2

            if is_final:
                # TOURNAMENT WINNER (or this stage winner)
                create_result(competition, match.winner, 'WINNER', 1, processed_players)
                # RUNNER-UP (2nd place)
                create_result(competition, loser, 'RUNNER_UP', 2, processed_players)
            else:
                # LOSERS IN EARLIER ROUNDS
                # Calculating rank:
                # Final (Max Round) = ranks 1-2
                # Semi-final (Max Round-1) = ranks 3-4 (i.e. rank 3)
                # Quarter-final (Max Round-2) = ranks 5-8 (i.e. rank 5)
                # Last 16 = ranks 9-16 (i.e. rank 9)

                rounds_from_final = stage.num_rounds - r
                # Formula: rank = 2^(rounds_from_final) + 1
                # e.g. semi-final (1 round from final): 2^1 + 1 = 3
                # e.g. quarter-final (2 rounds from final): 2^2 + 1 = 5
                rank = (2 ** rounds_from_final) + 1

                # Determine stage name (Last 16, Last 32)
                # Last X is simply rank * 2 - 2 (bracket math is beautiful)
                # But simpler:
                # Semi-final -> Top 4
                # Quarter-final -> Top 8
                # Last 16 -> Top 16
                top_x = 2 ** (rounds_from_final + 1)

                create_result(
                    competition,
                    loser,
                    'KNOCKOUT_ROUND',
                    rank,
                    processed_players,
                    detail_number=top_x
                )


def process_group_stage(competition, stage, processed_players):
    """
    Analyzes groups. Assigns results to those who did NOT advance from groups (are not in processed_players).
    """
    for group in stage.groups.all():
        # Sort: points descending, balance, etc.
        standings = group.standings.all()

        position_in_group = 1
        for standing in standings:
            player = standing.player

            # If player has not been processed (i.e. didn't advance higher in tournament hierarchy)
            if player.id not in processed_players:
                # Calculate "virtual rank". Hard to get global rank in groups,
                # so we give a distant one (e.g. 100 + position in group)
                rank = 100 + position_in_group

                create_result(
                    competition,
                    player,
                    'GROUP_STAGE',
                    rank,
                    processed_players,
                    detail_number=position_in_group  # Here we record which place they took in the group
                )

            position_in_group += 1


def create_result(competition, player, result_code, rank, processed_set, detail_number=None):
    if not player: return
    if player.id in processed_set: return  # Already has a better result

    CompetitionResult.objects.create(
        competition=competition,
        player=player,
        result=result_code,
        rank=rank,
        detail_number=detail_number
    )
    processed_set.add(player.id)