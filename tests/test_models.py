from datetime import timedelta, date, time

import pytest
from snooker_app.models import Player, Match, Referee, MatchPlayer
from django.core.exceptions import ValidationError


@pytest.mark.django_db
class TestPlayerModel:
    def test_create_player(self):
        player = Player.objects.create(
            first_name='John',
            last_name='Doe',
            nickname='JD',
            highest_break=147,
            avg_shot_time=timedelta(seconds=25),
            pot_success_percentage=85.5,
            avg_shots_per_match=45.0,
            avg_fouls_per_match=2.0,
            avg_foul_points_per_match=4.0
        )

        assert player.first_name == 'John'
        assert player.last_name == 'Doe'
        assert player.nickname == 'JD'
        assert player.highest_break == 147
        assert player.avg_shot_time.total_seconds() == 25
        assert player.pot_success_percentage == 85.5
        assert player.avg_shots_per_match == 45.0
        assert player.avg_fouls_per_match == 2.0
        assert player.avg_foul_points_per_match == 4.0
        assert str(player) == 'John "JD" Doe'

    def test_player_set(self):
        player = Player.objects.create(
            first_name='John',
            last_name='Doe'
        )
        assert str(player) == 'John Doe'


@pytest.mark.django_db
class TestMatchModel:
    def test_create_match(self):
        player1 = Player.objects.create(first_name='John', last_name='Doe')
        player2 = Player.objects.create(first_name='Jane', last_name='Smith')

        match = Match.objects.create(
            date='2024-07-01',
            time='15:30:00',
            number_of_frames=5
        )

        match.players.add(player1, player2)

        match.refresh_from_db()

        assert match.date == date(2024, 7, 1)
        assert match.time == time(15, 30)
        assert match.number_of_frames == 5
        assert str(match) == "Match on 2024-07-01 at 15:30:00"
        assert set(match.players.all()) == {player1, player2}

    def test_clean_method(self):
        player1 = Player.objects.create(first_name='John', last_name='Doe')
        player2 = Player.objects.create(first_name='Jane', last_name='Smith')

        match = Match(date='2024-07-01', time='15:30:00', number_of_frames=0)
        with pytest.raises(ValidationError, match="The number of frames must be greater than zero."):
            match.clean()

        match.number_of_frames = 5
        match.save()
        match.players.set([player1])
        with pytest.raises(ValidationError, match="A match must have at least two players."):
            match.clean()

        match.players.set([player1, player2])
        match.clean()

    def test_save_method(self):
        player1 = Player.objects.create(first_name='John', last_name='Doe')
        player2 = Player.objects.create(first_name='Jane', last_name='Smith')
        referee = Referee.objects.create(first_name='Ref', last_name='One')

        match = Match.objects.create(
            date='2024-07-01',
            time='15:30:00',
            number_of_frames=5
        )
        match.players.set([player1, player2])
        match.referees.set([referee])
        match.save()

        assert match.player_names == 'John Doe, Jane Smith'
        assert match.referee_names == 'Ref One'


@pytest.mark.django_db
class TestMatchPlayerModel:
    def test_create_match_player(self):
        player = Player.objects.create(first_name='John', last_name='Doe')
        match = Match.objects.create(
            date='2024-07-01',
            time='15:30:00',
            number_of_frames=5
        )
        match_player = MatchPlayer.objects.create(
            match=match,
            player=player,
            position=1,
            points_scored=50,
            max_break=100,
            fouls=3,
            foul_points=12,
            avg_shot_time='00:00:30',
            attempts=10,
            successful_pots=7
        )
        assert match_player.points_scored == 50
        assert match_player.max_break == 100
        assert match_player.fouls == 3
        assert match_player.foul_points == 12
        assert match_player.avg_shot_time.total_seconds() == 30
        assert match_player.attempts == 10
        assert match_player.successful_pots == 7
        assert match_player.pot_success_percentage == 70.0
        assert match_player.total_points == 62
        assert str(match_player) == 'John Doe in Match on 2024-07-01 at 15:30:00 (Position: First)'
