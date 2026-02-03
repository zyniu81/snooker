from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist  # <--- WAŻNY IMPORT
from .models import Match, MatchPlayer, GroupStanding, Competition, GroupStage, KnockoutStage


def recalculate_group_standings(group):
    """
    Resetuje i przelicza tabelę dla konkretnej grupy na podstawie zakończonych meczów.
    Pobiera zasady punktacji (win/draw) z etapu (GroupStage).
    """
    # Zabezpieczenie: Jeśli grupa nie ma przypisanego etapu (sierota), przerwij
    try:
        stage = group.stage
    except ObjectDoesNotExist:
        return

    # 1. Pobierz ustawienia punktacji z Etapu
    pts_win = stage.points_for_win
    pts_draw = stage.points_for_draw
    pts_loss = stage.points_for_loss

    # 2. Pobierz wszystkie wiersze tabeli dla tej grupy (żeby je zaktualizować)
    standings = {s.player_id: s for s in group.standings.all()}

    # 3. ZRESETUJ statystyki do zera (żeby nie dodawać dubli)
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
        # Nie resetujemy is_qualified ręcznie

    # 4. Pobierz ZAKOŃCZONE mecze w tej grupie
    finished_matches = group.matches.filter(status='FINISHED')

    for match in finished_matches:
        # Pobierz graczy i ich wyniki z modelu Match
        mps = list(match.matchplayer_set.all().order_by('position'))
        if len(mps) < 2:
            continue

        p1 = mps[0].player
        p2 = mps[1].player

        if p1.id not in standings or p2.id not in standings:
            continue

        s1 = standings[p1.id]
        s2 = standings[p2.id]

        # -- LICZENIE STATYSTYK --

        # Mecze rozegrane
        s1.matches_played += 1
        s2.matches_played += 1

        # Frame'y
        f1 = match.final_score_player1
        f2 = match.final_score_player2

        s1.frames_won += f1
        s1.frames_lost += f2
        s2.frames_won += f2
        s2.frames_lost += f1

        # Małe Punkty
        sp1 = match.total_points_player1
        sp2 = match.total_points_player2

        s1.small_points_scored += sp1
        s1.small_points_conceded += sp2

        s2.small_points_scored += sp2
        s2.small_points_conceded += sp1

        # Najwyższy Break w Grupie
        if match.highest_break_p1 > s1.highest_break:
            s1.highest_break = match.highest_break_p1
        if match.highest_break_p2 > s2.highest_break:
            s2.highest_break = match.highest_break_p2

        # Punkty meczowe (Win/Draw/Loss)
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
            # Remis
            s1.matches_drawn += 1
            s1.points += pts_draw
            s2.matches_drawn += 1
            s2.points += pts_draw

    # 5. Zapisz wszystko w bazie
    GroupStanding.objects.bulk_update(standings.values(), [
        'matches_played', 'matches_won', 'matches_drawn', 'matches_lost',
        'frames_won', 'frames_lost', 'points',
        'small_points_scored', 'small_points_conceded', 'highest_break'
    ])


def update_records(match):
    """
    Sprawdza, czy w meczu padł rekord breaka dla Etapu lub Turnieju.
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

    # Pobieramy kontekst bezpiecznie
    try:
        stage = match.get_stage()
    except ObjectDoesNotExist:
        return

    competition = stage.competition if stage else None

    for points, player in breaks:
        # 1. Rekord ETAPU
        if stage and points > stage.highest_break_points:
            stage.highest_break_points = points
            stage.highest_break_player = player
            stage.save()

        # 2. Rekord TURNIEJU
        if competition and points > competition.highest_break_points:
            competition.highest_break_points = points
            competition.highest_break_player = player
            competition.save()


@receiver(post_save, sender=Match)
def match_post_save_handler(sender, instance, created, raw=False,  **kwargs):
    """
    Główny sygnał. Uruchamia się po zapisaniu meczu.
    """

    if raw:
        return

    # 1. Jeśli to mecz grupowy -> Przelicz tabelę tej grupy
    if instance.group:
        transaction.on_commit(lambda: recalculate_group_standings(instance.group))

    # 2. Sprawdź rekordy (Max Break)
    if instance.status == 'FINISHED':
        transaction.on_commit(lambda: update_records(instance))


# --- TU BYŁ BŁĄD ---
@receiver(post_delete, sender=Match)
def match_post_delete_handler(sender, instance, **kwargs):
    """
    Obsługa usunięcia meczu.
    Musi być odporna na sytuację, gdy usuwamy cały Turniej (wtedy Grupa też znika).
    """
    try:
        # Próbujemy pobrać grupę.
        # Jeśli usuwamy kaskadowo (Turniej -> Grupa -> Mecz),
        # to w tym momencie Grupa już nie istnieje w bazie.
        # Django rzuci wyjątek ObjectDoesNotExist przy próbie dostępu do instance.group
        if instance.group:
            recalculate_group_standings(instance.group)

    except ObjectDoesNotExist:
        # Jeśli grupa nie istnieje, to znaczy, że albo została usunięta wcześniej,
        # albo usuwamy cały turniej. W obu przypadkach - nie musimy nic przeliczać.
        # Po prostu ignorujemy błąd.
        pass


@receiver(post_save, sender=Match)
def advance_knockout_winner(sender, instance, created, raw=False, **kwargs):

    if raw:
        return
    """
    Automatycznie przesuwa zwycięzcę do następnej rundy w drabince pucharowej.
    """
    # Działamy tylko dla zakończonych meczów pucharowych, które mają zwycięzcę
    if not instance.knockout_stage or not instance.is_finished or not instance.winner:
        return

    stage = instance.knockout_stage
    current_round = instance.round_number

    # --- LOGIKA GŁÓWNA: AWANS DO NASTĘPNEJ RUNDY ---

    # 1. Pobieramy wszystkie mecze TEJ rundy, posortowane po ID (kolejność tworzenia)
    current_round_matches = Match.objects.filter(
        knockout_stage=stage,
        round_number=current_round
    ).order_by('id')

    # 2. Sprawdzamy, którym meczem z kolei jest nasz zakończony mecz (indeks 0, 1, 2...)
    matches_list = list(current_round_matches)
    try:
        current_match_index = matches_list.index(instance)
    except ValueError:
        return  # Coś dziwnego, meczu nie ma na liście

    # 3. Obliczamy cel: Następna runda, Mecz o indeksie (nasz_indeks // 2)
    next_round = current_round + 1
    target_match_index = current_match_index // 2

    # Pobieramy mecze NASTĘPNEJ rundy
    next_round_matches = Match.objects.filter(
        knockout_stage=stage,
        round_number=next_round
    ).order_by('id')

    # Jeśli cel istnieje (czyli nie jest to finał)
    if target_match_index < len(next_round_matches):
        target_match = next_round_matches[target_match_index]

        # Parzysty indeks (0, 2...) idzie na Player 1 (Góra drabinki)
        # Nieparzysty indeks (1, 3...) idzie na Player 2 (Dół drabinki)
        if current_match_index % 2 == 0:
            target_match.player1 = instance.winner
        else:
            target_match.player2 = instance.winner

        target_match.save()

    # --- LOGIKA DODATKOWA: MECZ O 3 MIEJSCE ---
    # Jeśli to Półfinał (przedostatnia runda) i mamy mecz o 3 miejsce
    total_rounds = stage.num_rounds
    if stage.has_third_place_match and current_round == (total_rounds - 1):
        # Znajdź przegranego
        loser = instance.player1 if instance.winner == instance.player2 else instance.player2

        if loser:
            # Szukamy meczu o 3 miejsce (ma specjalny round_number=99 lub nazwę)
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