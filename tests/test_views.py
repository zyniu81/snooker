from urllib import response

import pytest
from django.urls import reverse
from django.utils import timezone
from mixer.backend.django import mixer
from datetime import datetime, date

from snooker_app.forms import MatchForm, CompetitionForm
from snooker_app.models import Player, Referee, Venue, Match, Competition


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
    url = reverse('add_match')

    player1 = mixer.blend(Player)
    player2 = mixer.blend(Player)
    response = client.post(url, {
        'date': '2024-07-04',
        'time': '15:30:00',
        'number_of_frames': 5,
        'players': [player1.pk, player2.pk]
    })

    assert response.status_code == 302
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


# =======================================================
# =======================================================
# =======================================================
# =======================================================


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
    group_stages = mixer.cycle(3).blend('snooker_app.GroupStage', competition=competition)
    knockout_stages = mixer.cycle(2).blend('snooker_app.KnockoutStage', competition=competition)
    url = reverse('competition_stages', args=[competition.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'competition_stages.html' in [template.name for template in response.templates]
    assert len(response.context['stages']) == 5


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


@pytest.mark.django_db
def test_competition_delete_view(client):
    competition = mixer.blend(Competition)
    url = reverse('delete_competition', args=[competition.pk])
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == reverse('competition_list')
    assert not Competition.objects.filter(pk=competition.pk).exists()
