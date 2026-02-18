from django.contrib import admin, messages
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django import forms
from django.shortcuts import render
from django.utils.html import format_html

from .models import (
    Profile, Player, Match, Frame, MatchPlayer, Referee, Venue, Competition, GroupStage,
    KnockoutStage, Ranking, RankingPosition, Announcement, SnookerNews)


# ==================================================
# Sending email to all/selected
# ==================================================
# 1. We register Ads so you can post them
@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'style', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'style')
    search_fields = ('title', 'content')


# 2. Form for entering email content (only in admin's memory)
class SendEmailForm(forms.Form):
    subject = forms.CharField(widget=forms.TextInput(attrs={'size': '60'}))
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 10, 'cols': 60}))


#3. Action Function
def send_email_to_selected(modeladmin, request, queryset):
    # If admin clicked "Send" in intermediate form
    if 'apply' in request.POST:
        form = SendEmailForm(request.POST)
        if form.is_valid():
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']

            count = 0
            for profile in queryset:
                if profile.user.email:
                    # Sending (fail_silently=True so that an error in one email doesn't result in the whole thing being lost)
                    send_mail(
                        subject,
                        message,
                        None,
                        [profile.user.email],
                        fail_silently=True
                    )
                    count += 1

            modeladmin.message_user(request, f"Email sent to {count} users.")
            return HttpResponseRedirect(request.get_full_path())

    # If you just selected users and chose the action -> Show form
    else:
        form = SendEmailForm()

    return render(request, 'send_mass_email.html', {
        'items': queryset,
        'form': form,
        'title': 'Send Email to Selected Users',
        'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
    })

send_email_to_selected.short_description = "Send Email to selected users"


# ==================================================
# 1. PROFILE (SaaS)
# ==================================================
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'account_tier', 'club_name', 'city', 'subscription_end', 'status_icon')
    list_filter = ('account_tier', 'show_tutorial', 'email_confirmed', 'city')
    search_fields = ('user__username', 'user__email', 'club_name', 'phone_main')
    ordering = ('-subscription_end',)
    actions = [send_email_to_selected]

    def status_icon(self, obj):
        color = 'green' if obj.account_tier != 'FREE' else 'gray'
        return format_html(f'<span style="color: {color};">●</span> {obj.account_tier}')

    status_icon.short_description = "Status"


# ==================================================
# 2. MATCH INLINES (Players)
# ==================================================
class MatchPlayerInline(admin.TabularInline):
    model = MatchPlayer
    extra = 0
    fields = ('player', 'position')
    autocomplete_fields = ['player']


# ==================================================
# 3. MAIN MODELS
# ==================================================

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('get_full_name', 'nickname', 'owner', 'matches_won', 'total_career_points', 'is_public')
    list_filter = ('is_public', 'is_temporary', 'owner__username')
    search_fields = ('last_name', 'first_name', 'nickname', 'owner__username')
    ordering = ('-created_at',)

    def get_full_name(self, obj):
        return str(obj)

    get_full_name.short_description = "Full Name"


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'date', 'venue', 'get_status_colored', 'get_referees')

    list_filter = (
        'status',
        'game_variant',
        'allow_draws',
        'venue__name',
        'date',
    )

    search_fields = ('venue__name', 'player_names')
    date_hierarchy = 'date'

    inlines = [MatchPlayerInline]

    fieldsets = (
        ('Configuration', {
            'fields': ('status', 'game_variant', 'date', 'time', 'venue', 'table_number', 'owner')
        }),
        ('Participants', {
            'fields': ('player1', 'player2', 'referees')
        }),
        ('Structure', {
            'fields': ('number_of_frames', 'allow_draws', 'round_number', 'group_name', 'knockout_name')
        }),
        ('Final Score', {
            'fields': ('winner', 'final_score_player1', 'final_score_player2')
        }),
        ('Statistics', {
            'fields': ('total_duration', 'highest_break_frame_p1', 'highest_break_frame_p2', 'longest_pot_streak_p1',
                       'longest_pot_streak_p2'),
            'classes': ('collapse',)
        }),
    )

    def get_status_colored(self, obj):
        colors = {
            'SCHEDULED': 'blue',
            'IN_PROGRESS': 'orange',
            'FINISHED': 'green',
            'ABORTED': 'red',
        }
        color = colors.get(obj.status, 'black')
        return format_html(f'<span style="color: {color}; font-weight: bold;">{obj.get_status_display()}</span>')

    get_status_colored.short_description = "Status"

    def get_referees(self, obj):
        return ", ".join([str(r) for r in obj.referees.all()])

    get_referees.short_description = "Referees"


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'owner', 'is_public', 'tables_count', 'price_per_hour')
    list_filter = ('is_public', 'owner')
    search_fields = ('name', 'address')


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'game_variant', 'get_status_colored', 'owner')
    list_filter = ('status', 'game_variant', 'owner', 'is_public')
    search_fields = ('name',)
    date_hierarchy = 'start_date'

    def get_status_colored(self, obj):
        colors = {
            'SCHEDULED': 'blue',
            'ACTIVE': 'green',
            'FINISHED': 'gray',
        }
        color = colors.get(obj.status, 'black')
        return format_html(f'<span style="color: {color}; font-weight: bold;">{obj.get_status_display()}</span>')

    get_status_colored.short_description = "Status"


@admin.register(Referee)
class RefereeAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'license_number', 'owner')
    list_filter = ('owner',)
    search_fields = ('last_name', 'license_number')


# ==================================================
# 4. RANKINGS
# ==================================================
@admin.register(Ranking)
class RankingAdmin(admin.ModelAdmin):
    list_display = ('name', 'ranking_type', 'owner', 'is_active', 'is_public')
    list_filter = ('is_active', 'is_public', 'ranking_type')
    search_fields = ('name', 'owner__username')


@admin.register(RankingPosition)
class RankingPositionAdmin(admin.ModelAdmin):
    list_display = ('player', 'ranking', 'current_rank', 'points', 'frame_difference')
    list_filter = ('ranking',)
    search_fields = ('player__last_name', 'player__nickname')
    ordering = ('ranking', 'current_rank')


# ==================================================
# Adding news to the home page
# ==================================================
@admin.register(SnookerNews)
class SnookerNewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at', 'is_active', 'external_link')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'short_description')


# ==================================================
# OTHER (Simple Registration)
# ==================================================
admin.site.register(Frame)
admin.site.register(GroupStage)
admin.site.register(KnockoutStage)