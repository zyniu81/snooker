from django.db.models import Sum, Min, Max, Avg
from .models import Player, MatchPlayer, Frame, CompetitionResult, KnockoutStage, GroupStage, Match
from datetime import timedelta
from django.db import transaction


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


def calculate_competition_results(competition):
    """
    Główna funkcja generująca ranking turnieju (CompetitionResult).
    Obsługuje hybrydy (Grupy -> Puchar) i sam Puchar.
    """

    # 1. Wyczyść stare wyniki (żeby nie było dubli przy przeliczaniu)
    CompetitionResult.objects.filter(competition=competition).delete()

    # Zbiór ID graczy, którzy już mają przydzielone miejsce (żeby nie dać im gorszego z wcześniejszego etapu)
    processed_player_ids = set()

    # 2. Pobierz etapy i ODWRÓĆ kolejność (zaczynamy od Finału, kończymy na Kwalifikacjach)
    stages = competition.get_stages()  # To Twoja metoda sorted()
    reversed_stages = list(reversed(stages))

    with transaction.atomic():
        for stage in reversed_stages:

            # --- SCENARIUSZ A: PUCHAR (KNOCKOUT) ---
            if isinstance(stage, KnockoutStage):
                process_knockout_stage(competition, stage, processed_player_ids)

            # --- SCENARIUSZ B: GRUPY (GROUP STAGE) ---
            elif isinstance(stage, GroupStage):
                process_group_stage(competition, stage, processed_player_ids)


def process_knockout_stage(competition, stage, processed_players):
    """
    Analizuje drabinkę.
    W Twoim modelu: round_number rośnie (1=1/4, 2=1/2, 3=Finał).
    """
    # Sprawdź czy był mecz o 3 miejsce (round_number=99)
    third_place_match = Match.objects.filter(
        knockout_stage=stage,
        round_number=99,
        status='FINISHED'
    ).first()

    if third_place_match and third_place_match.winner:
        # Zwycięzca meczu o 3 miejsce
        create_result(competition, third_place_match.winner, 'THIRD_PLACE', 3, processed_players)
        # Przegrany meczu o 3 miejsce -> 4 miejsce
        loser = third_place_match.player1 if third_place_match.winner == third_place_match.player2 else third_place_match.player2
        create_result(competition, loser, 'FOURTH_PLACE', 4, processed_players)

    # Iterujemy od Finału w dół (np. runda 3, potem 2, potem 1)
    # stage.num_rounds to np. 3 (dla ćwierćfinałów)
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
                # ZWYCIĘZCA TURNIEJU (lub tego etapu)
                create_result(competition, match.winner, 'WINNER', 1, processed_players)
                # FINALISTA (2 miejsce)
                create_result(competition, loser, 'RUNNER_UP', 2, processed_players)
            else:
                # PRZEGRANI W WCZEŚNIEJSZYCH RUNDACH
                # Obliczanie miejsca:
                # Finał (Runda Max) = miejsca 1-2
                # Półfinał (Runda Max-1) = miejsca 3-4 (czyli rank 3)
                # Ćwierćfinał (Runda Max-2) = miejsca 5-8 (czyli rank 5)
                # Last 16 = miejsca 9-16 (czyli rank 9)

                rounds_from_final = stage.num_rounds - r
                # Wzór: rank = 2^(rounds_from_final) + 1
                # np. półfinał (1 runda od finału): 2^1 + 1 = 3
                # np. ćwierćfinał (2 rundy od finału): 2^2 + 1 = 5
                rank = (2 ** rounds_from_final) + 1

                # Ustalenie nazwy etapu (Last 16, Last 32)
                # Last X to po prostu rank * 2 - 2 (matematyka drabinki jest piękna)
                # Ale prościej:
                # Półfinał -> Top 4
                # Ćwierćfinał -> Top 8
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
    Analizuje grupy. Daje wyniki tym, którzy NIE wyszli z grup (nie są w processed_players).
    """
    for group in stage.groups.all():
        # Sortujemy: punkty malejąco, bilans, itd.
        standings = group.standings.all()

        position_in_group = 1
        for standing in standings:
            player = standing.player

            # Jeśli gracz nie został przetworzony (czyli nie awansował wyżej w hierarchii turnieju)
            if player.id not in processed_players:
                # Obliczamy "wirtualny rank". Trudno o globalny rank w grupach,
                # więc damy odległy (np. 100 + pozycja w grupie)
                rank = 100 + position_in_group

                create_result(
                    competition,
                    player,
                    'GROUP_STAGE',
                    rank,
                    processed_players,
                    detail_number=position_in_group  # Tu zapiszemy które miejsce zajął w grupie
                )

            position_in_group += 1


def create_result(competition, player, result_code, rank, processed_set, detail_number=None):
    if not player: return
    if player.id in processed_set: return  # Już ma lepszy wynik

    CompetitionResult.objects.create(
        competition=competition,
        player=player,
        result=result_code,
        rank=rank,
        detail_number=detail_number
    )
    processed_set.add(player.id)