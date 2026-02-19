from django.contrib import admin
from .models import EmailAccount, AirlineRule, Flight, FlightGroup


@admin.register(FlightGroup)
class FlightGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_auto_generated', 'created_at')
    list_filter = ('is_auto_generated',)
    search_fields = ('name', 'user__username')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(EmailAccount)
class EmailAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'email_address', 'provider', 'user', 'is_active', 'last_synced_at')
    list_filter = ('provider', 'is_active')
    search_fields = ('name', 'email_address', 'user__username')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(AirlineRule)
class AirlineRuleAdmin(admin.ModelAdmin):
    list_display = ('airline_name', 'airline_code', 'user', 'is_builtin', 'is_active', 'priority')
    list_filter = ('is_builtin', 'is_active')
    search_fields = ('airline_name', 'airline_code')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = (
        'flight_number', 'airline_name', 'departure_airport',
        'arrival_airport', 'departure_datetime', 'status', 'user',
    )
    list_filter = ('status', 'airline_code', 'is_manually_added')
    search_fields = ('flight_number', 'booking_reference', 'user__username')
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'departure_datetime'
