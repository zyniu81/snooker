"""
URL configuration for snooker_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from snooker_app import views
from snooker_app.views import PlayerDeleteView, VenueDeleteView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('players/', views.player_list, name='player_list'),
    path('players/add/', views.add_player, name='add_player'),
    path('players/<int:pk>/', views.player_detail, name='player_detail'),
    path('players/<int:pk>/edit/', views.player_edit, name='player_edit'),
    path('player/<int:pk>/delete/', PlayerDeleteView.as_view(), name='player_delete'),
    path('referees/', views.referee_list, name='referee_list'),
    path('referees/add/', views.add_referee, name='add_referee'),
    path('referees/<int:pk>/edit/', views. edit_referee, name='edit_referee'),
    path('referees/<int:pk>/delete/', views.delete_referee, name='delete_referee'),
    path('referees/<int:pk>/', views.referee_detail, name='referee_detail'),
    path('venues/', views.venue_list, name='venue_list'),
    path('venues/add/', views.add_venue, name='add_venue'),
    path('venues/edit/<int:pk>/', views.edit_venue, name='edit_venue'),
    path('venues/delete/<int:pk>/', VenueDeleteView.as_view(), name='delete_venue'),
    path('venues/<int:pk>', views.venue_detail, name='venue_detail'),
    path('matches/', views.match_list, name='match_list'),
    path('match/add/', views.add_match, name='add_match'),
    path('match/<int:pk>/', views.match_detail, name='match_detail'),
    path('match/<int:pk>/edit/', views.edit_match, name='edit_match'),
    path('match/<int:pk>/delete/', views.MatchDeleteView.as_view(), name='delete_match'),
    path('match/<int:pk>/start/', views.start_game, name='start_game'),
    path('competitions/', views.competition_list, name='competition_list'),
    path('competitions/add/', views.add_competition, name='add_competition'),
    path('competitions/<int:pk>', views.competition_detail, name='competition_detail'),
    path('competitions/<int:pk>/edit/', views.edit_competition, name='edit_competition'),
    path('competitions/<int:pk>/delete/', views.CompetitionDeleteView.as_view(), name='delete_competition'),
    path('competitions/<int:pk>/stages/', views.competition_stages, name='competition_stages'),
    path('competitions/<int:competition_id>/add-matches/', views.add_matches_to_competition,
         name='add_matches_to_competition'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('register/', views.register, name='register'),
    path('user/settings/', views.user_settings, name='user_settings'),
    path('user/delete/', views.delete_user, name='delete_user'),
    path('', views.home, name='home'),
    path('competitions/<int:competition_id>/create-group-stage/', views.create_group_stage,
         name='create_group_stage'),
    path('competitions/<int:competition_id>/create-knockout-stage/', views.create_knockout_stage,
         name='create_knockout_stage'),
    path('competitions/<int:pk>/add-players/', views.add_players_to_competition,
         name='add_players_to_competition'),
    path('achievements/', views.achievement_list, name='achievement_list'),
    path('gpt-analysis/', views.gpt_analysis, name='gpt_analysis'),
    path('matches/temporary/create/', views.create_temporary_match, name='create_temporary_match'),
    path('update_game/', views.update_game_data, name='update-game-data'),
    path('set_active_player/', views.set_active_player, name='set_active_player'),
    path('save_frame_result/', views.save_frame_result, name='save_frame_result'),
    path('update_player_stats/', views.update_player_stats, name='update_player_stats'),
    path('competitions/<int:competition_id>/mass-edit/', views.mass_edit_matches, name='mass_edit_matches'),
    path('end-group-stage/<int:stage_id>/', views.end_group_stage, name='end_group_stage'),
    path('end-knockout-stage/<int:stage_id>/', views.end_knockout_stage, name='end_knockout_stage'),
    path('end-competition/<int:competition_id>/', views.end_competition, name='end_competition'),
    path('stage/<int:stage_id>/substitute/', views.substitute_player, name='substitute_player'),
    path('stage/<int:stage_id>/manage-groups/', views.manage_groups, name='manage_groups'),
    path('stage/<int:stage_id>/manage-knockout/', views.manage_knockout, name='manage_knockout'),
    path('generate-token/', views.generate_token, name='generate_token'),
    path('competition/<int:comp_id>/import/', views.import_players_to_competition,
         name='import_players_to_competition'),
    path('match/import-guest/', views.import_guest_for_match, name='import_guest_for_match'),
    path('competition/<int:competition_id>/ranking/', views.competition_ranking, name='competition_ranking'),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)