from django.db.models import Sum, Min, Max, Avg
from .models import Player, MatchPlayer, Frame
from datetime import timedelta


def update_career_stats(player):
    """
    Przelicza statystyki gracza na podstawie historii meczów.
    POPRAWKA: Pobiera framy przez relację match_player__match.
    """

    # 1. Znajdź zakończone mecze tego gracza
    match_participations = MatchPlayer.objects.filter(player=player, match__status='FINISHED').select_related('match')

    # Sortujemy mecze chronologicznie
    matches = sorted([mp.match for mp in match_participations], key=lambda x: x.created_at)

    matches_played_count = len(matches)

    # --- ZMIENNE GLOBALNE KARIERY ---
    career_matches_won = 0
    career_matches_lost = 0

    career_deciders_played = 0
    career_deciders_won = 0
    career_whitewashes = 0

    career_frames_won = 0
    career_frames_lost = 0
    career_total_points = 0

    # Technika
    career_total_pots = 0
    career_total_misses = 0
    career_total_safe_succ = 0
    career_total_safe_attempts = 0
    career_total_time = timedelta(0)
    career_total_shots_time = 0

    # Breaki
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

    # --- GŁÓWNA PĘTLA PO MECZACH ---
    for m in matches:
        # 1. Ustal kim był gracz w tym meczu (P1 czy P2?)
        is_p1 = (m.player1 == player)
        is_p2 = (m.player2 == player)

        if not is_p1 and not is_p2:
            continue

        # 2. Wynik meczu
        is_winner = (m.winner == player)
        p1_score, p2_score = m.get_real_score()
        frames_played_in_match = p1_score + p2_score

        # --- Streaks (Mecze) ---
        if is_winner:
            career_matches_won += 1
            current_match_streak += 1
            if current_match_streak > max_match_streak:
                max_match_streak = current_match_streak
        else:
            career_matches_lost += 1
            current_match_streak = 0

        # --- Decidery ---
        if frames_played_in_match == m.number_of_frames and m.number_of_frames >= 3:
            career_deciders_played += 1
            if is_winner:
                career_deciders_won += 1

        # --- Whitewashes ---
        if is_winner:
            opponent_score = p2_score if is_p1 else p1_score
            if opponent_score == 0:
                career_whitewashes += 1

        # --- ANALIZA FRAMÓW ---
        # POPRAWKA TUTAJ: Zamiast m.frame_set.all(), szukamy framów, które należą do tego meczu
        # przechodząc przez relację match_player__match
        match_frames = Frame.objects.filter(match_player__match=m).order_by('frame_number')

        for f in match_frames:
            # -- Zwycięstwo we framie --
            if f.winner == player:
                career_frames_won += 1
                current_frame_streak += 1
                if current_frame_streak > max_frame_streak:
                    max_frame_streak = current_frame_streak
            else:
                career_frames_lost += 1
                current_frame_streak = 0

                # -- Pobieranie danych --
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

            # -- Sumowanie --
            career_total_points += pts
            career_total_pots += pots
            career_total_misses += misses
            career_total_safe_succ += safe_succ
            career_total_safe_attempts += safe_total
            if time_shot:
                career_total_time += time_shot
            career_total_shots_time += total_shots

            # -- Analiza Breaków --
            for b in breaks:
                if b > career_highest_break:
                    career_highest_break = b

                # Liczniki 147 / 100 / 50 (Rozłączne)
                if b >= 147:
                    career_max_breaks += 1
                    career_centuries += 1  # 147 liczymy też jako setkę (zgodnie z życzeniem)
                elif b >= 100:
                    career_centuries += 1
                elif b >= 50:
                    career_fifties += 1

                # Histogram "Kubełkowy" (Tylko najwyższy próg)
                # Np. break 64 -> bucket 60. Zapisujemy tylko w 60+.
                if b >= 10:
                    bucket = (b // 10) * 10  # Dzielenie całkowite: 64//10 = 6 -> *10 = 60
                    # Zabezpieczenie, żeby nie wyszło więcej niż 140
                    if bucket > 140:
                        bucket = 140
                    career_break_histogram[f"{bucket}+"] += 1

    # --- OBLICZENIA KOŃCOWE ---
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

    # --- ZAPIS ---
    player.matches_played = matches_played_count
    player.matches_won = career_matches_won
    player.matches_lost = career_matches_lost

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

    # --- NOWE: ANALIZA CZASU FRAMÓW (Min/Max/Avg) ---
    # Bierzemy framy tylko z zakończonych meczów tego gracza
    # Wykluczamy framy, które nie mają czasu (null) lub trwają 0 sekund
    time_stats = Frame.objects.filter(match_player__match__in=matches).exclude(time_duration=None).aggregate(
        shortest=Min('time_duration'),
        longest=Max('time_duration'),
        average=Avg('time_duration')
    )

    player.fastest_frame_time = time_stats['shortest']
    player.longest_frame_time = time_stats['longest']
    player.avg_frame_time = time_stats['average']

    player.save()