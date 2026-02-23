<script lang="ts">
	import LocationCard from '$lib/components/cards/LocationCard.svelte';
	import FlightCard from '$lib/components/cards/FlightCard.svelte';
	import type { Flight } from '$lib/types';
	import type { PageData } from './$types';
	import { t } from 'svelte-i18n';

	// Icons
	import FlagCheckeredVariantIcon from '~icons/mdi/flag-checkered-variant';
	import Airplane from '~icons/mdi/airplane';
	import AirplaneTakeoff from '~icons/mdi/airplane-takeoff';
	import CityVariantOutline from '~icons/mdi/city-variant-outline';
	import MapMarkerStarOutline from '~icons/mdi/map-marker-star-outline';
	import CalendarClock from '~icons/mdi/calendar-clock';
	import Plus from '~icons/mdi/plus';
	import ClockOutline from '~icons/mdi/clock-outline';
	import AirportIcon from '~icons/mdi/airport';

	export let data: PageData;

	const user = data.user;
	const recentAdventures = data.props.adventures;
	const stats = data.props.stats;
	const upcomingFlights: Flight[] = data.props.upcomingFlights || [];
	const flightStats = data.props.flightStats;

	// Calculate completion percentage
	$: completionPercentage =
		stats.visited_country_count > 0 ? Math.round((stats.visited_country_count / 195) * 100) : 0;

	function formatDuration(minutes: number): string {
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}
</script>

<svelte:head>
	<title>Dashboard | AdventureLog</title>
	<meta name="description" content="Home dashboard for AdventureLog." />
</svelte:head>

<div class="min-h-screen bg-gradient-to-br from-base-200 via-base-100 to-base-200">
	<div class="container mx-auto px-6 py-8">
		<!-- Welcome Section -->
		<div class="welcome-section mb-12">
			<div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
				<div>
					<div class="flex items-center gap-4 mb-4">
						<div>
							<h1 class="text-4xl lg:text-5xl font-bold bg-clip-text text-primary">
								{$t('dashboard.welcome_back')}, {user?.first_name
									? `${user.first_name}`
									: user?.username}!
							</h1>
							<p class="text-lg text-base-content/60 mt-2">
								{#if stats.location_count > 0}
									{$t('dashboard.welcome_text_1')}
									<span class="font-semibold text-primary">{stats.location_count}</span>
									{$t('dashboard.welcome_text_2')}
								{:else}
									{$t('dashboard.welcome_text_3')}
								{/if}
							</p>
						</div>
					</div>
				</div>

				<!-- Quick Action -->
				<div class="flex flex-col sm:flex-row gap-3">
					<a
						href="/locations"
						class="btn btn-primary btn-lg gap-2 shadow-lg hover:shadow-xl transition-all duration-300"
					>
						<Plus class="w-5 h-5" />
						{$t('map.add_location')}
					</a>
					<a href="/worldtravel" class="btn btn-outline btn-lg gap-2">
						<FlagCheckeredVariantIcon class="w-5 h-5" />
						{$t('home.explore_world')}
					</a>
				</div>
			</div>
		</div>

		<!-- Stats Grid -->
		<div
			class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-8 mb-12"
		>
			<!-- Countries Visited -->
			<div
				class="stat-card card bg-gradient-to-br from-primary/10 to-primary/5 shadow-xl border border-primary/20 hover:shadow-2xl transition-all duration-300"
			>
				<div class="card-body p-6">
					<div class="flex items-center justify-between">
						<div class="flex-1">
							<div class="stat-title text-primary/70 font-medium">
								{$t('dashboard.countries_visited')}
							</div>
							<div class="stat-value text-3xl font-bold text-primary">
								{stats.visited_country_count}
							</div>
							<div class="stat-desc text-primary/60 mt-2">
								<div class="flex items-center justify-between">
									<span class="font-medium">{completionPercentage}% {$t('home.of_world')}</span>
								</div>
								<progress
									class="progress progress-primary w-full mt-1"
									value={stats.visited_country_count}
									max="195"
								></progress>
							</div>
						</div>
						<div class="p-4 bg-primary/20 rounded-2xl">
							<FlagCheckeredVariantIcon class="w-8 h-8 text-primary" />
						</div>
					</div>
				</div>
			</div>

			<!-- Regions Visited -->
			<div
				class="stat-card card bg-gradient-to-br from-success/10 to-success/5 shadow-xl border border-success/20 hover:shadow-2xl transition-all duration-300"
			>
				<div class="card-body p-6">
					<div class="flex items-center justify-between">
						<div>
							<div class="stat-title text-success/70 font-medium">
								{$t('dashboard.total_visited_regions')}
							</div>
							<div class="stat-value text-3xl font-bold text-success">
								{stats.visited_region_count}
							</div>
						</div>
						<div class="p-4 bg-success/20 rounded-2xl">
							<MapMarkerStarOutline class="w-8 h-8 text-success" />
						</div>
					</div>
				</div>
			</div>

			<!-- Cities Visited -->
			<div
				class="stat-card card bg-gradient-to-br from-info/10 to-info/5 shadow-xl border border-info/20 hover:shadow-2xl transition-all duration-300"
			>
				<div class="card-body p-6">
					<div class="flex items-center justify-between">
						<div>
							<div class="stat-title text-info/70 font-medium">
								{$t('dashboard.total_visited_cities')}
							</div>
							<div class="stat-value text-3xl font-bold text-info">{stats.visited_city_count}</div>
						</div>
						<div class="p-4 bg-info/20 rounded-2xl">
							<CityVariantOutline class="w-8 h-8 text-info" />
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Flight Stats Row -->
		{#if flightStats && flightStats.total_flights > 0}
			<div class="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-12">
				<div
					class="stat-card card bg-gradient-to-br from-secondary/10 to-secondary/5 shadow-xl border border-secondary/20 hover:shadow-2xl transition-all duration-300"
				>
					<div class="card-body p-6">
						<div class="flex items-center justify-between">
							<div>
								<div class="stat-title text-secondary/70 font-medium">Total Flights</div>
								<div class="stat-value text-3xl font-bold text-secondary">
									{flightStats.total_flights}
								</div>
							</div>
							<div class="p-4 bg-secondary/20 rounded-2xl">
								<Airplane class="w-8 h-8 text-secondary" />
							</div>
						</div>
					</div>
				</div>

				<div
					class="stat-card card bg-gradient-to-br from-accent/10 to-accent/5 shadow-xl border border-accent/20 hover:shadow-2xl transition-all duration-300"
				>
					<div class="card-body p-6">
						<div class="flex items-center justify-between">
							<div>
								<div class="stat-title text-accent/70 font-medium">Time in the Air</div>
								<div class="stat-value text-3xl font-bold text-accent">
									{flightStats.total_duration_hours}h
								</div>
							</div>
							<div class="p-4 bg-accent/20 rounded-2xl">
								<ClockOutline class="w-8 h-8 text-accent" />
							</div>
						</div>
					</div>
				</div>

				<div
					class="stat-card card bg-gradient-to-br from-warning/10 to-warning/5 shadow-xl border border-warning/20 hover:shadow-2xl transition-all duration-300"
				>
					<div class="card-body p-6">
						<div class="flex items-center justify-between">
							<div>
								<div class="stat-title text-warning/70 font-medium">Airports Visited</div>
								<div class="stat-value text-3xl font-bold text-warning">
									{flightStats.unique_airports_count}
								</div>
							</div>
							<div class="p-4 bg-warning/20 rounded-2xl">
								<AirportIcon class="w-8 h-8 text-warning" />
							</div>
						</div>
					</div>
				</div>
			</div>
		{/if}

		<!-- Upcoming Flights Section -->
		{#if upcomingFlights.length > 0}
			<div class="mb-8">
				<div class="flex items-center justify-between mb-6">
					<div class="flex items-center gap-3">
						<div class="p-2 bg-secondary/10 rounded-xl">
							<AirplaneTakeoff class="w-6 h-6 text-secondary" />
						</div>
						<div>
							<h2 class="text-3xl font-bold">Upcoming Flights</h2>
							<p class="text-base-content/60">Your next adventures in the sky</p>
						</div>
					</div>
					<a href="/flights" class="btn btn-ghost gap-2">
						{$t('dashboard.view_all')}
						{#if flightStats}
							<span class="badge badge-secondary">{flightStats.total_flights}</span>
						{/if}
					</a>
				</div>

				<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
					{#each upcomingFlights as flight}
						<FlightCard {flight} readOnly />
					{/each}
				</div>
			</div>
		{/if}

		<!-- Recent Adventures Section -->
		{#if recentAdventures.length > 0}
			<div class="mb-8">
				<div class="flex items-center justify-between mb-6">
					<div class="flex items-center gap-3">
						<div class="p-2 bg-primary/10 rounded-xl">
							<CalendarClock class="w-6 h-6 text-primary" />
						</div>
						<div>
							<h2 class="text-3xl font-bold">{$t('dashboard.recent_adventures')}</h2>
							<p class="text-base-content/60">{$t('home.latest_travel_experiences')}</p>
						</div>
					</div>
					<a href="/locations" class="btn btn-ghost gap-2">
						{$t('dashboard.view_all')}
						<span class="badge badge-primary">{stats.location_count}</span>
					</a>
				</div>

				<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
					{#each recentAdventures as adventure}
						<div class="adventure-card">
							<LocationCard {adventure} readOnly user={null} />
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Empty State - only if no adventures AND no flights -->
		{#if recentAdventures.length === 0 && upcomingFlights.length === 0 && (!flightStats || flightStats.total_flights === 0)}
			<div
				class="empty-state card bg-gradient-to-br from-base-100 to-base-200 shadow-2xl border border-base-300"
			>
				<div class="card-body p-12 text-center">
					<div class="flex justify-center mb-6">
						<div class="p-6 bg-primary/10 rounded-3xl">
							<Airplane class="w-16 h-16 text-primary" />
						</div>
					</div>

					<h2
						class="text-3xl font-bold mb-4 bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent"
					>
						{$t('dashboard.no_recent_adventures')}
					</h2>
					<p class="text-lg text-base-content/60 mb-8 max-w-md mx-auto leading-relaxed">
						{$t('dashboard.document_some_adventures')}
					</p>

					<div class="flex flex-col sm:flex-row gap-4 justify-center">
						<a
							href="/locations"
							class="btn btn-primary btn-lg gap-2 shadow-lg hover:shadow-xl transition-all duration-300"
						>
							<Plus class="w-5 h-5" />
							{$t('map.add_location')}
						</a>
						<a href="/worldtravel" class="btn btn-outline btn-lg gap-2">
							<FlagCheckeredVariantIcon class="w-5 h-5" />
							{$t('home.explore_world')}
						</a>
					</div>
				</div>
			</div>
		{/if}
	</div>
</div>
