from django.contrib import admin
from .models import (
    Player, Match, Frame, MatchPlayer,
    Referee, Venue, Competition,
    GroupStage, KnockoutStage
)

admin.site.register(Player)
admin.site.register(Match)
admin.site.register(Frame)
admin.site.register(MatchPlayer)
admin.site.register(Referee)
admin.site.register(Venue)
admin.site.register(Competition)
admin.site.register(GroupStage)
admin.site.register(KnockoutStage)