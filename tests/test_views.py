from urllib import response

import pytest
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from mixer.backend.django import mixer
from datetime import datetime, date
from django.test import Client

from snooker_app.forms import MatchForm, CompetitionForm, SignUpForm
from snooker_app.models import Player, Referee, Venue, Match, Competition, GroupStage, KnockoutStage, Achievement


@pytest.fixture
def sample_player():
    return mixer.blend(Player)


@pytest.mark.django_db
def test_player_list_view(client):
    url = reverse('player_list')
    response = client.get(url)
    assert response.status_code == 200
    assert 'player_list.html' in [template.name for template in response.templates]


@pytest.mark.django_db
def test_add_player_view(client):
    url = reverse('add_player')

    response = client.post(url, {'first_name': 'John', 'last_name': 'Doe', 'nickname': 'JD'})
    assert response.status_code == 302

    redirected_url = response.url
    redirect_response = client.get(redirected_url)
    assert redirect_response.status_code == 200

    response = client.post(url, {'first_name': 'John', 'last_name': 'Doe', 'nickname': ''})
    assert response.status_code == 302

    redirected_url = response.url
    redirect_response = client.get(redirected_url)
    assert redirect_response.status_code == 200


@pytest.mark.django_db
def test_player_detail_view(client, sample_player):
    url = reverse('player_detail', args=[sample_player.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert sample_player.first_name in str(response.content)


@pytest.mark.django_db
def test_player_edit_view(client, sample_player):
    url = reverse('player_edit', args=[sample_player.pk])

    response = client.post(url, {'first_name': 'Jane', 'last_name': 'Smith', 'nickname': 'JS'})
    assert response.status_code == 302

    updated_player = Player.objects.get(pk=sample_player.pk)
    assert updated_player.first_name == 'Jane'
    assert updated_player.last_name == 'Smith'
    assert updated_player.nickname == 'JS'

    response = client.post(url, {'first_name': '', 'last_name': '', 'nickname': ''})
    assert response.status_code == 302


@pytest.mark.django_db
def test_player_delete_view(client, sample_player):
    url = reverse('player_delete', args=[sample_player.pk])

    response = client.post(url)
    assert response.status_code == 302


@pytest.mark.django_db
def test_player_delete_view_cancel(client, sample_player):
    url = reverse('player_delete', args=[sample_player.pk])

    response = client.get(url)
    assert response.status_code == 200


@pytest.fixture
def sample_referee():
    return mixer.blend(Referee)


@pytest.fixture
def sample_venue():
    return mixer.blend(Venue)


@pytest.mark.django_db
def test_referee_list_view(client):
    url = reverse('referee_list')
    response = client.get(url)
    assert response.status_code == 200
    assert 'referee_list.html' in [template.name for template in response.templates]


@pytest.mark.django_db
def test_add_referee_view(client):
    url = reverse('add_referee')
    response = client.post(url, {'first_name': 'John', 'last_name': 'Doe', 'license_number': '314'})
    assert response.status_code == 302


@pytest.mark.django_db
def test_edit_referee_view(client, sample_referee):
    url = reverse('edit_referee', args=[sample_referee.pk])

    sample_referee.first_name = 'John'
    sample_referee.last_name = 'Doe'
    sample_referee.license_number = '314'
    sample_referee.save()

    new_first_name = 'Jane'
    new_last_name = 'Smith'
    new_license_number = '272'

    response = client.post(url, {'first_name': new_first_name, 'last_name': new_last_name, 'license_number': new_license_number})
    assert response.status_code == 302

    updated_referee = Referee.objects.get(pk=sample_referee.pk)
    assert updated_referee.first_name == new_first_name
    assert updated_referee.last_name == new_last_name
    assert updated_referee.license_number == new_license_number


@pytest.mark.django_db
def test_referee_detail_view(client, sample_referee):
    url = reverse('referee_detail', args=[sample_referee.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert sample_referee.first_name in str(response.content)


@pytest.mark.django_db
def test_delete_referee_view(client, sample_referee):
    url = reverse('delete_referee', args=[sample_referee.pk])
    response = client.post(url)
    assert response.status_code == 302
    with pytest.raises(Referee.DoesNotExist):
        Referee.objects.get(pk=sample_referee.pk)


@pytest.mark.django_db
def test_venue_list_view(client):
    url = reverse('venue_list')
    response = client.get(url)
    assert response.status_code == 200
    assert 'venue_list.html' in [template.name for template in response.templates]


@pytest.mark.django_db
def test_add_venue_view(client):
    url = reverse('add_venue')
    response = client.post(url, {'name': 'Crucible', 'address': 'Shefield', 'capacity': 5000})
    assert response.status_code == 302


@pytest.mark.django_db
def test_edit_venue_view(client, sample_venue):
    url = reverse('edit_venue', args=[sample_venue.pk])

    sample_venue.name = 'Crucible'
    sample_venue.address = 'Shefield'
    sample_venue.capacity = 1000
    sample_venue.save()

    new_name = 'Crucible 2'
    new_address = 'Manchester'
    new_capacity = 2000

    response = client.post(url, {'name': new_name, 'address': new_address, 'capacity': new_capacity})
    assert response.status_code == 302

    updated_venue = Venue.objects.get(pk=sample_venue.pk)
    assert updated_venue.name == new_name
    assert updated_venue.address == new_address
    assert updated_venue.capacity == new_capacity


@pytest.mark.django_db
def test_venue_detail_view(client, sample_venue):
    url = reverse('venue_detail', args=[sample_venue.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert sample_venue.name in str(response.content)


@pytest.mark.django_db
def test_delete_venue_view(client, sample_venue):
    url = reverse('delete_venue', args=[sample_venue.pk])
    response = client.post(url)
    assert response.status_code == 302
    with pytest.raises(Venue.DoesNotExist):
        Venue.objects.get(pk=sample_venue.pk)


@pytest.fixture
def sample_match():
    return mixer.blend(Match)


@pytest.mark.django_db
def test_match_list_view(client):
    match1 = mixer.blend(Match)
    match2 = mixer.blend(Match)

    url = reverse('match_list')
    response = client.get(url)
    assert response.status_code == 200
    assert 'match_list.html' in [template.name for template in response.templates]
    assert len(response.context['matches']) == 2


@pytest.mark.django_db
def test_add_match_view_get(client):
    url = reverse('add_match')
    response = client.get(url)
    assert response.status_code == 200
    assert 'add_match.html' in [template.name for template in response.templates]
    assert isinstance(response.context['form'], MatchForm)


@pytest.mark.django_db
def test_add_match_view_post(client):
    user = User.objects.create_user(username='test_user', password='alfa314159')
    client.login(username='test_user', password='alfa314159')

    player1 = mixer.blend(Player)
    player2 = mixer.blend(Player)
    url = reverse('add_match')
    data = {
        'date': '2024-07-04',
        'time': '15:30:00',
        'number_of_frames': 5,
        'players': [player1.pk, player2.pk]
    }

    response = client.post(url, data)

    assert response.status_code in [200, 302]

    if response.status_code == 302:
        match = Match.objects.get(date='2024-07-04', time='15:30:00')
        assert player1 in match.players.all()
        assert player2 in match.players.all()
        assert match.number_of_frames == 5


@pytest.mark.django_db
def test_match_detail_view(client, sample_match):
    url = reverse('match_detail', args=[sample_match.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'match_detail.html' in [template.name for template in response.templates]
    assert response.context['match'] == sample_match


@pytest.mark.django_db
def test_edit_match_view_get(client, sample_match):
    url = reverse('edit_match', args=[sample_match.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'edit_match.html' in [template.name for template in response.templates]
    assert isinstance(response.context['form'], MatchForm)


@pytest.mark.django_db
def test_match_delete_view(client, sample_match):
    url = reverse('delete_match', args=[sample_match.pk])
    response = client.post(url)
    assert response.status_code == 302
    with pytest.raises(Match.DoesNotExist):
        Match.objects.get(pk=sample_match.pk)


@pytest.mark.django_db
def test_start_game_view_get(client, sample_match):
    url = reverse('start_game', args=[sample_match.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'start_game.html' in [template.name for template in response.templates]
    assert response.context['match'] == sample_match


@pytest.mark.django_db
def test_start_game_view_post(client, sample_match):
    url = reverse('start_game', args=[sample_match.pk])
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == reverse('match_detail', args=[sample_match.pk])


@pytest.mark.django_db
def test_add_competition_view_get(client):
    url = reverse('add_competition')
    response = client.get(url)
    assert response.status_code == 200
    assert 'add_competition.html' in [template.name for template in response.templates]
    assert isinstance(response.context['form'], CompetitionForm)


@pytest.mark.django_db
def test_add_competition_view_post(client):
    url = reverse('add_competition')
    data = {
        'name': 'World Championship',
        'start_date': '2024-06-15',
        'end_date': '2024-07-15',
        'competition_type': 'Finals',
        'is_group_stage': False,
        'is_knockout': True
    }
    response = client.post(url, data)
    assert response.status_code == 302
    assert Competition.objects.filter(name='World Championship').exists()


@pytest.mark.django_db
def test_edit_competition_view_get(client):
    competition = mixer.blend(Competition)
    url = reverse('edit_competition', args=[competition.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'edit_competition.html' in [template.name for template in response.templates]
    assert isinstance(response.context['form'], CompetitionForm)


@pytest.mark.django_db
def test_edit_competition_view_post(client):
    start_date = date(2024, 6, 15)
    end_date = date(2024, 7, 15)
    competition = mixer.blend(Competition, name='Old Name', start_date=start_date, end_date=end_date)
    url = reverse('edit_competition', args=[competition.pk])
    new_name = 'New Name'
    data = {
        'name': new_name,
        'start_date': '2024-08-15',
        'end_date': '2024-09-15',
        'competition_type': competition.competition_type,
        'is_group_stage': competition.is_group_stage,
        'is_knockout': competition.is_knockout
    }
    response = client.post(url, data)
    assert response.status_code == 302
    competition.refresh_from_db()
    assert competition.name == new_name
    assert competition.start_date == date(2024, 8, 15)
    assert competition.end_date == date(2024, 9, 15)


@pytest.mark.django_db
def test_competition_stages_view(client):
    competition = mixer.blend(Competition)

    group_stage1 = mixer.blend(GroupStage, competition=competition)
    group_stage2 = mixer.blend(GroupStage, competition=competition)
    group_stage3 = mixer.blend(GroupStage, competition=competition)

    knockout_stage1 = mixer.blend(KnockoutStage, competition=competition)
    knockout_stage2 = mixer.blend(KnockoutStage, competition=competition)

    url = reverse('competition_stages', args=[competition.pk])
    response = client.get(url)

    assert response.status_code == 200
    assert 'competition_stages.html' in [template.name for template in response.templates]
    assert 'competition' in response.context
    assert 'stages_with_matches' in response.context

    expected_num_stages = 5
    assert len(response.context['stages_with_matches']) == expected_num_stages

    assert any(group_stage1 == stage_match['stage'] for stage_match in response.context['stages_with_matches'])
    assert any(group_stage2 == stage_match['stage'] for stage_match in response.context['stages_with_matches'])
    assert any(group_stage3 == stage_match['stage'] for stage_match in response.context['stages_with_matches'])
    assert any(knockout_stage1 == stage_match['stage'] for stage_match in response.context['stages_with_matches'])
    assert any(knockout_stage2 == stage_match['stage'] for stage_match in response.context['stages_with_matches'])



@pytest.mark.django_db
def test_competition_list_view(client):
    competition = mixer.cycle(3).blend(Competition)
    url = reverse('competition_list')
    response = client.get(url)
    assert response.status_code == 200
    assert 'competition_list.html' in [template.name for template in response.templates]
    assert len(response.context['competitions']) == 3


@pytest.mark.django_db
def test_competition_detail_view(client):
    competition = mixer.blend(Competition)
    url = reverse('competition_detail', args=[competition.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'competition_detail.html' in [template.name for template in response.templates]
    assert response.context['competition'] == competition
    add_players_url = reverse('add_players_to_competition', kwargs={'pk': competition.pk})
    assert add_players_url in response.content.decode()


@pytest.mark.django_db
def test_competition_delete_view(client):
    competition = mixer.blend(Competition)
    url = reverse('delete_competition', args=[competition.pk])
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == reverse('competition_list')
    assert not Competition.objects.filter(pk=competition.pk).exists()


# =======================================================
# =======================================================
# =======================================================
# =======================================================


@pytest.mark.django_db
def test_add_matches_to_competition_get(client):
    competition = mixer.blend(Competition)
    url = reverse('add_matches_to_competition', args=[competition.id])
    response = client.get(url)
    assert response.status_code == 200
    assert 'add_matches_to_competition.html' in [template.name for template in response.templates]
    assert response.context['competition'] == competition


@pytest.mark.django_db
def test_add_matches_to_competition_post(client):
    competition = mixer.blend(Competition)
    player1 = mixer.blend(Player)
    player2 = mixer.blend(Player)
    player3 = mixer.blend(Player)
    player4 = mixer.blend(Player)


    match1 = mixer.blend(Match)
    match1.players.add(player1, player2)
    match1.save()

    match2 = mixer.blend(Match)
    match2.players.add(player3, player4)
    match2.save()

    stage = mixer.blend(GroupStage, competition=competition)

    data = {
        'matches': [match1.id, match2.id],
        f'stage_{match1.id}': stage.id,
        f'stage_{match2.id}': stage.id,
    }

    url = reverse('add_matches_to_competition', args=[competition.id])
    response = client.post(url, data)

    assert response.status_code == 302
    assert response.url == reverse('competition_detail', args=[competition.id])
    assert match1 in competition.matches.all()
    assert match2 in competition.matches.all()


# @pytest.mark.django_db
# def test_create_temporary_match_get(client):
#     url = reverse('create_temporary_match')
#     response = client.get(url)
#     assert response.status_code == 200
#     assert 'create_temporary_match.html' in [template.name for template in response.templates]
#     assert isinstance(response.context['form'], MatchForm)
#
#
# @pytest.mark.django_db
# def test_create_temporary_match_post(client):
#     form_data = {
#         'date': '2024-07-15',
#         'time': '12:00:00',
#         'number_of_frames': 5,
#     }
#
#     url = reverse('create_temporary_match')
#     response = client.post(url, form_data)
#     assert response.status_code == 302
#
#     match = Match.objects.get(date='2024-07-15', time='12:00:00')
#     assert match.is_temporary
#     assert 'Player' in match.temp_player1.name
#     assert 'Player' in match.temp_player2.name


@pytest.mark.django_db
def test_create_group_stage_get(client):
    competition = mixer.blend(Competition)
    player = mixer.blend(Player)
    competition.players.add(player)
    url = reverse('create_group_stage', args=[competition.id])
    response = client.get(url)
    assert response.status_code == 200
    assert 'create_group_stage.html' in [template.name for template in response.templates]
    assert response.context['competition'] == competition


@pytest.mark.django_db
def test_create_group_stage_post(client):
    competition = mixer.blend(Competition)
    player = mixer.cycle(4).blend(Player, competition=competition)
    mixer.cycle(5).blend(GroupStage, competition=competition)
    data = {
        'num_groups': 2,
        'players_per_group': 2,
        'matches_per_pair': 2,
        'default_frames': 5
    }
    url = reverse('create_group_stage', args=[competition.id])
    response = client.post(url, data)

    assert response.status_code == 302

    if competition.players.count() < data['num_groups']* data['players_per_group']:
        expected_url = reverse('add_players_to_competition', args=[competition.id])
    else:
        expected_url = reverse('competition_detail', args=[competition.id])

    assert response.url == expected_url
    assert GroupStage.objects.filter(competition=competition).exists()


@pytest.mark.django_db
def test_create_knockout_stage_get(client):
    competition = mixer.blend(Competition)
    url = reverse('create_knockout_stage', args=[competition.id])
    response = client.get(url)
    assert response.status_code == 200
    assert 'create_knockout_stage.html' in [template.name for template in response.templates]
    assert response.context['competition'] == competition


@pytest.mark.django_db
def test_create_knockout_stage_post(client):
    competition = mixer.blend(Competition)
    data = {
        'num_rounds': 3,
        'frames_per_match': 5,
    }
    url = reverse('create_knockout_stage', args=[competition.id])
    response = client.post(url, data)
    assert response.status_code == 302
    assert response.url == reverse('competition_detail', args=[competition.id])
    assert KnockoutStage.objects.filter(competition=competition).exists()


@pytest.mark.django_db
def test_register_get(client):
    url = reverse('register')
    response = client.get(url)
    assert response.status_code == 200
    assert 'register.html' in [template.name for template in response.templates]
    assert isinstance(response.context['form'], SignUpForm)


@pytest.mark.django_db
def test_register_post(client):
    data = {
        'username': 'testuser',
        'email': 'test@example.com',
        'password1': 'testpassword123',
        'password2': 'testpassword123'
    }
    url = reverse('register')
    response = client.post(url, data)
    assert response.status_code == 302
    assert response.url == reverse('home')


@pytest.mark.django_db
def test_user_settings_get(client):
    user = mixer.blend(User)
    client.force_login(user)

    url = reverse('user_settings')
    response = client.get(url)
    assert response.status_code == 200
    assert 'user_settings.html' in [template.name for template in response.templates]
    assert isinstance(response.context['form'], PasswordChangeForm)


@pytest.mark.django_db
def test_user_settings_post(client):
    user = mixer.blend(User)
    user.set_password('testpassword123')
    user.save()
    client.force_login(user)
    data = {
        'old_password': 'testpassword123',
        'new_password1': 'newpassword123',
        'new_password2': 'newpassword123'
    }

    url = reverse('user_settings')
    response = client.post(url, data)

    assert response.status_code == 302
    assert response.url == reverse('login')


@pytest.mark.django_db
def test_delete_user(client):
    user = mixer.blend(User)
    client.force_login(user)
    url = reverse('delete_user')
    response = client.delete(url)
    assert response.status_code == 200
    assert 'delete_user.html' in [template.name for template in response.templates]


@pytest.mark.django_db
def test_delete_user_post(client):
    user = mixer.blend(User)
    client.force_login(user)
    url = reverse('delete_user')
    response = client.post(url)
    assert response.status_code == 302
    assert not User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_custom_logout(client):
    user = mixer.blend(User)
    user.set_password('testpassword123')
    user.save()
    client.force_login(user)
    url = reverse('logout')
    response = client.get(url)
    assert response.status_code == 302
    assert response.url == reverse('login')
    assert '_auth_user_id' not in client.session


@pytest.mark.django_db
def test_add_players_to_competition_get(client):
    competition = mixer.blend(Competition)
    url = reverse('add_players_to_competition', args=[competition.id])
    response = client.get(url)
    assert response.status_code == 200
    assert 'add_players_to_competition.html' in [template.name for template in response.templates]
    assert response.context['competition'] == competition


@pytest.mark.django_db
def test_add_players_to_competition_post(client):
    competition = mixer.blend(Competition)
    player1 = mixer.blend(Player)
    player2 = mixer.blend(Player)
    data = {
        'players': [player1.id, player2.id]
    }

    url = reverse('add_players_to_competition', args=[competition.id])
    response = client.post(url, data)
    assert response.status_code == 302
    assert response.url == reverse('competition_detail', args=[competition.id])
    assert player1 in competition.players.all()
    assert player2 in competition.players.all()


@pytest.fixture
def sample_achievements():
    return mixer.cycle(5).blend(Achievement)


@pytest.mark.django_db
def test_achievement_list_view_table_content(sample_player):
    achievement1 = Achievement.objects.create(
        player=sample_player,
        tournaments_won=2,
        matches_won=10,
        frames_won=50,
        frames_lost=20,
        fastest_frame_won=None,
        longest_frame_won=None,
        consecutive_frames_won=3,
        consecutive_matches_won=4
    )

    client = Client()
    url = reverse('achievement_list')
    response = client.get(url)

    assert response.status_code == 200
    assert f'<td>{sample_player}</td>' in str(response.content)
    assert f'<td>{achievement1.tournaments_won}</td>' in str(response.content)
    assert f'<td>{achievement1.matches_won}</td>' in str(response.content)
    assert f'<td>{achievement1.frames_won}</td>' in str(response.content)
    assert f'<td>{achievement1.frames_lost}</td>' in str(response.content)
    assert f'<td>{achievement1.fastest_frame_won}</td>' in str(response.content)
    assert f'<td>{achievement1.longest_frame_won}</td>' in str(response.content)
    assert f'<td>{achievement1.consecutive_frames_won}</td>' in str(response.content)
    assert f'<td>{achievement1.consecutive_matches_won}</td>' in str(response.content)
