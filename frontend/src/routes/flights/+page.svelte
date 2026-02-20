<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import type { Flight, FlightGroup, EmailAccount, FlightStats } from '$lib/types';

	import Airplane from '~icons/mdi/airplane';
	import AirplaneTakeoff from '~icons/mdi/airplane-takeoff';
	import AirplaneLanding from '~icons/mdi/airplane-landing';
	import Email from '~icons/mdi/email-outline';
	import Plus from '~icons/mdi/plus';
	import Delete from '~icons/mdi/delete-outline';
	import Sync from '~icons/mdi/sync';
	import Clock from '~icons/mdi/clock-outline';
	import SeatRecline from '~icons/mdi/seat-recline-normal';
	import Ticket from '~icons/mdi/ticket-outline';

	export let data: any;

	let flights: Flight[] = data.props.flights;
	let flightGroups: FlightGroup[] = data.props.flightGroups;
	let emailAccounts: EmailAccount[] = data.props.emailAccounts;
	let stats: FlightStats | null = data.props.stats;

	let activeTab: 'flights' | 'emails' = 'flights';
	// 'upcoming' shows future flights; 'history' shows completed/cancelled
	let flightView: 'upcoming' | 'history' = 'upcoming';
	let viewMode: 'trips' | 'all' = 'trips';
	let showAddFlightModal = false;
	let showAddEmailModal = false;
	let syncing: string | null = null;
	let expandedGroups: Set<string> = new Set();
	let connectionTested = false;
	let testingConnection = false;
	let connectionTestMessage = '';

	async function handleTestConnection() {
		const form = document.querySelector('#emailAccountForm') as HTMLFormElement | null;
		if (!form) return;
		const formData = new FormData(form);
		testingConnection = true;
		connectionTestMessage = '';
		try {
			const res = await fetch('?/testEmailConnection', {
				method: 'POST',
				body: formData
			});
			const result = await res.json();
			// SvelteKit form action responses are wrapped in { type, status, data }
			const actionData = result?.data ? JSON.parse(result.data) : result;
			// Handle various response shapes from SvelteKit enhance
			if (actionData?.[0]?.success) {
				connectionTested = true;
				connectionTestMessage = actionData[0].message || 'Connection successful!';
			} else if (actionData?.success) {
				connectionTested = true;
				connectionTestMessage = actionData.message || 'Connection successful!';
			} else {
				connectionTested = false;
				connectionTestMessage = actionData?.[0]?.error || actionData?.error || 'Connection failed. Please check your settings.';
			}
		} catch (e) {
			connectionTested = false;
			connectionTestMessage = 'Connection test failed. Please check your settings.';
		} finally {
			testingConnection = false;
		}
	}

	$: upcomingFlights = flights
		.filter((f) => f.status === 'upcoming')
		.sort((a, b) => new Date(a.departure_datetime).getTime() - new Date(b.departure_datetime).getTime());
	$: historyFlights = flights
		.filter((f) => f.status !== 'upcoming')
		.sort((a, b) => new Date(b.departure_datetime).getTime() - new Date(a.departure_datetime).getTime());
	$: displayedFlights = flightView === 'upcoming' ? upcomingFlights : historyFlights;

	$: upcomingSortedGroups = [...flightGroups]
		.filter((g) => g.flights && g.flights.some((f: Flight) => f.status === 'upcoming'))
		.sort((a, b) => {
			const aDate = a.start_date ? new Date(a.start_date).getTime() : 0;
			const bDate = b.start_date ? new Date(b.start_date).getTime() : 0;
			return aDate - bDate; // Soonest trip first
		});
	$: historySortedGroups = [...flightGroups]
		.filter((g) => !g.flights || g.flights.every((f: Flight) => f.status !== 'upcoming'))
		.sort((a, b) => {
			const aDate = a.start_date ? new Date(a.start_date).getTime() : 0;
			const bDate = b.start_date ? new Date(b.start_date).getTime() : 0;
			return bDate - aDate; // Most recent first
		});
	$: sortedGroups = flightView === 'upcoming' ? upcomingSortedGroups : historySortedGroups;

	function toggleGroup(id: string) {
		if (expandedGroups.has(id)) {
			expandedGroups.delete(id);
		} else {
			expandedGroups.add(id);
		}
		expandedGroups = expandedGroups;
	}

	function formatDuration(minutes: number | null): string {
		if (!minutes) return '—';
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		return `${h}h ${m}m`;
	}

	function formatDateTime(iso: string): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return d.toLocaleDateString(undefined, {
			weekday: 'short',
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatDate(iso: string | null): string {
		if (!iso) return 'Never';
		const d = new Date(iso);
		return d.toLocaleDateString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function statusBadgeClass(status: string): string {
		switch (status) {
			case 'upcoming':
				return 'badge-info';
			case 'completed':
				return 'badge-success';
			case 'cancelled':
				return 'badge-error';
			default:
				return 'badge-ghost';
		}
	}

	/**
	 * Group sorted flights into journey legs.
	 * Consecutive flights with < 24h gap (arrival → next departure) are in the same leg.
	 */
	function groupIntoLegs(sortedFlights: Flight[]): Flight[][] {
		if (sortedFlights.length === 0) return [];
		const legs: Flight[][] = [[sortedFlights[0]]];
		for (let i = 1; i < sortedFlights.length; i++) {
			const prevArrival = new Date(sortedFlights[i - 1].arrival_datetime).getTime();
			const currDeparture = new Date(sortedFlights[i].departure_datetime).getTime();
			const gapHours = (currDeparture - prevArrival) / (1000 * 60 * 60);
			if (gapHours >= 0 && gapHours <= 24) {
				legs[legs.length - 1].push(sortedFlights[i]);
			} else {
				legs.push([sortedFlights[i]]);
			}
		}
		return legs;
	}

	/** Build a route summary string for a leg, e.g. "ARN → FRA (4h) → GRU" */
	function legRouteSummary(leg: Flight[]): string {
		if (leg.length === 0) return '';
		let route = leg[0].departure_airport;
		for (let i = 0; i < leg.length; i++) {
			if (i > 0) {
				// Add layover duration between previous arrival and this departure
				const prevArrival = new Date(leg[i - 1].arrival_datetime).getTime();
				const currDeparture = new Date(leg[i].departure_datetime).getTime();
				const gapMs = currDeparture - prevArrival;
				const gapHours = Math.floor(gapMs / (1000 * 60 * 60));
				const gapMinutes = Math.round((gapMs % (1000 * 60 * 60)) / (1000 * 60));
				const layoverStr = gapMinutes > 0 ? `${gapHours}h${gapMinutes}m` : `${gapHours}h`;
				route += ` (${layoverStr} layover)`;
			}
			route += ` → ${leg[i].arrival_airport}`;
		}
		return route;
	}

	function cabinLabel(cabin: string): string {
		const map: Record<string, string> = {
			economy: 'Economy',
			premium_economy: 'Premium Economy',
			business: 'Business',
			first: 'First'
		};
		return map[cabin] || cabin || '—';
	}
</script>

<svelte:head>
	<title>Flights | AdventureLog</title>
</svelte:head>

<div class="max-w-7xl mx-auto px-4 py-8">
	<!-- Header -->
	<div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
		<div>
			<h1 class="text-3xl font-bold flex items-center gap-2">
				<Airplane class="text-primary" />
				Flights
			</h1>
			<p class="text-base-content/60 mt-1">Track your flights from email or add them manually</p>
		</div>
	</div>

	<!-- Stats Cards -->
	{#if stats}
		<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
			<div class="stat bg-base-200 rounded-box p-4">
				<div class="stat-title">Total Flights</div>
				<div class="stat-value text-primary">{stats.total_flights}</div>
			</div>
			<div class="stat bg-base-200 rounded-box p-4">
				<div class="stat-title">Flight Hours</div>
				<div class="stat-value text-secondary">{stats.total_duration_hours}</div>
			</div>
			<div class="stat bg-base-200 rounded-box p-4">
				<div class="stat-title">Airlines</div>
				<div class="stat-value text-accent">{stats.unique_airlines.length}</div>
			</div>
			<div class="stat bg-base-200 rounded-box p-4">
				<div class="stat-title">Airports</div>
				<div class="stat-value">{stats.unique_airports_count}</div>
			</div>
		</div>
	{/if}

	<!-- Tabs -->
	<div role="tablist" class="tabs tabs-box mb-6">
		<button
			role="tab"
			class="tab {activeTab === 'flights' ? 'tab-active' : ''}"
			on:click={() => (activeTab = 'flights')}
		>
			<Airplane class="mr-1" /> My Flights
		</button>
		<button
			role="tab"
			class="tab {activeTab === 'emails' ? 'tab-active' : ''}"
			on:click={() => (activeTab = 'emails')}
		>
			<Email class="mr-1" /> Email Accounts
		</button>
	</div>

	<!-- ===================== FLIGHTS TAB ===================== -->
	{#if activeTab === 'flights'}
		<!-- Upcoming / History sub-tabs -->
		<div role="tablist" class="tabs tabs-bordered mb-4">
			<button
				role="tab"
				class="tab {flightView === 'upcoming' ? 'tab-active font-semibold' : ''}"
				on:click={() => (flightView = 'upcoming')}
			>
				Upcoming
				{#if upcomingFlights.length > 0}
					<span class="badge badge-sm badge-primary ml-1">{upcomingFlights.length}</span>
				{/if}
			</button>
			<button
				role="tab"
				class="tab {flightView === 'history' ? 'tab-active font-semibold' : ''}"
				on:click={() => (flightView = 'history')}
			>
				History
				{#if historyFlights.length > 0}
					<span class="badge badge-sm badge-ghost ml-1">{historyFlights.length}</span>
				{/if}
			</button>
		</div>

		<div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
			<div class="flex gap-2 items-center">
				<!-- View mode toggle -->
				<div class="join">
					<button
						class="join-item btn btn-sm {viewMode === 'trips' ? 'btn-active' : ''}"
						on:click={() => (viewMode = 'trips')}
					>
						By Trip
					</button>
					<button
						class="join-item btn btn-sm {viewMode === 'all' ? 'btn-active' : ''}"
						on:click={() => (viewMode = 'all')}
					>
						All Flights
					</button>
				</div>
			</div>
			<div class="flex gap-2">
				<button class="btn btn-primary btn-sm" on:click={() => (showAddFlightModal = true)}>
					<Plus /> Add Flight
				</button>
			</div>
		</div>

		<!-- ===== TRIPS VIEW ===== -->
		{#if viewMode === 'trips'}
			{#if sortedGroups.length === 0}
				<div class="text-center py-16">
					<Airplane class="mx-auto text-5xl text-base-content/20 mb-4" />
					<h2 class="text-xl font-semibold text-base-content/50">
						{flightView === 'upcoming' ? 'No upcoming trips' : 'No past trips'}
					</h2>
					<p class="text-base-content/40 mt-2">
						{flightView === 'upcoming'
							? 'Add flights and click "Auto-group" to organize them into trips.'
							: 'Your completed trips will appear here.'}
					</p>
				</div>
			{:else}
				<div class="grid gap-4">
					{#each sortedGroups as group (group.id)}
						{@const isExpanded = expandedGroups.has(group.id)}
						{@const groupFlights = [...group.flights].sort(
							(a, b) => new Date(a.departure_datetime).getTime() - new Date(b.departure_datetime).getTime()
						)}
						<div class="card card-border bg-base-100 shadow-sm">
							<!-- Trip Header (clickable) -->
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<div
								class="card-body p-4 sm:p-5 cursor-pointer hover:bg-base-200/50 transition-colors"
								on:click={() => toggleGroup(group.id)}
							>
								<div class="flex items-center gap-3">
									<div class="grow">
										<div class="font-bold text-lg">{group.name}</div>
										<div class="text-sm text-base-content/60 flex flex-wrap items-center gap-2">
											{#if group.start_date}
												<span class="flex items-center gap-1">
													<Clock class="text-xs" />
													{formatDate(group.start_date)}
												</span>
											{/if}
											<span class="badge badge-sm badge-outline">
												{group.flight_count} flight{group.flight_count !== 1 ? 's' : ''}
											</span>
										</div>
									</div>

									<!-- Expand indicator -->
									<div class="text-base-content/30 text-lg transition-transform {isExpanded ? 'rotate-180' : ''}">
										▼
									</div>
								</div>
							</div>

							<!-- Expanded: Flight list grouped by journey legs -->
							{#if isExpanded}
								<div class="border-t border-base-200">
									<div class="p-3 sm:p-4 grid gap-4">
										{#each groupIntoLegs(groupFlights) as leg, legIdx}
											<!-- Journey leg route summary -->
											<div class="flex items-center gap-2 text-sm font-semibold text-primary">
												<Airplane class="text-xs" />
												<span>{legRouteSummary(leg)}</span>
											</div>

											<!-- Individual flights within this leg -->
											{#each leg as flight, i}
												<div class="flex flex-col lg:flex-row lg:items-center gap-3 p-3 bg-base-200/30 rounded-box ml-4">
													<!-- Flight number & airline -->
													<div class="min-w-[120px]">
														<div class="font-bold">{flight.flight_number}</div>
														<div class="text-xs text-base-content/60">
															{flight.airline_name || flight.airline_code || ''}
														</div>
														<span class="badge {statusBadgeClass(flight.status)} badge-xs mt-1">
															{flight.status}
														</span>
													</div>

													<!-- Route -->
													<div class="flex items-center gap-2 grow">
														<div class="text-center">
															<div class="font-bold text-lg">{flight.departure_airport}</div>
															<div class="text-xs text-base-content/50">{flight.departure_city}</div>
															<div class="text-xs text-base-content/60">{formatDateTime(flight.departure_datetime)}</div>
														</div>
														<div class="flex-1 flex flex-col items-center">
															<div class="text-xs text-base-content/40">
																{formatDuration(flight.duration_minutes)}
															</div>
															<div class="w-full flex items-center gap-1">
																<div class="h-px bg-base-300 flex-1"></div>
																<Airplane class="text-primary text-sm" />
																<div class="h-px bg-base-300 flex-1"></div>
															</div>
														</div>
														<div class="text-center">
															<div class="font-bold text-lg">{flight.arrival_airport}</div>
															<div class="text-xs text-base-content/50">{flight.arrival_city}</div>
															<div class="text-xs text-base-content/60">{formatDateTime(flight.arrival_datetime)}</div>
														</div>
													</div>

													<!-- Details -->
													<div class="flex flex-wrap gap-2 text-xs text-base-content/60 min-w-[100px]">
														{#if flight.booking_reference}
															<div class="flex items-center gap-1">
																<Ticket class="text-xs" />{flight.booking_reference}
															</div>
														{/if}
														{#if flight.seat}
															<div class="flex items-center gap-1">
																<SeatRecline class="text-xs" />{flight.seat}
															</div>
														{/if}
														{#if flight.cabin_class}
															<div>{cabinLabel(flight.cabin_class)}</div>
														{/if}
													</div>

													<!-- Delete -->
													<form
														method="POST"
														action="?/deleteFlight"
														use:enhance={() => {
															return async ({ result }) => {
																if (result.type === 'success') {
																	await invalidateAll();
																	flights = data.props.flights;
																	flightGroups = data.props.flightGroups;
																	stats = data.props.stats;
																}
															};
														}}
													>
														<input type="hidden" name="id" value={flight.id} />
														<button class="btn btn-ghost btn-xs btn-square" title="Delete flight">
															<Delete class="text-error" />
														</button>
													</form>
												</div>

												<!-- Layover indicator within the same leg -->
												{#if i < leg.length - 1}
													{@const gap = new Date(leg[i + 1].departure_datetime).getTime() - new Date(flight.arrival_datetime).getTime()}
													{@const gapHours = Math.floor(gap / (1000 * 60 * 60))}
													{@const gapMinutes = Math.round((gap % (1000 * 60 * 60)) / (1000 * 60))}
													{#if gapHours > 0 || gapMinutes > 0}
														<div class="flex items-center gap-2 px-4 py-1 ml-4">
															<div class="h-px bg-base-300 flex-1"></div>
															<span class="text-xs text-base-content/30 flex items-center gap-1">
																<Clock class="text-xs" />
																{gapMinutes > 0 ? `${gapHours}h ${gapMinutes}m` : `${gapHours}h`} layover in {flight.arrival_airport}
															</span>
															<div class="h-px bg-base-300 flex-1"></div>
														</div>
													{/if}
												{/if}
											{/each}

											<!-- Separator between legs -->
											{#if legIdx < groupIntoLegs(groupFlights).length - 1}
												<div class="divider my-0"></div>
											{/if}
										{/each}
									</div>

									<!-- Group actions -->
									<div class="flex justify-end p-3 border-t border-base-200">
										<form
											method="POST"
											action="?/deleteFlightGroup"
											use:enhance={() => {
												return async ({ result }) => {
													if (result.type === 'success') {
														await invalidateAll();
														flightGroups = data.props.flightGroups;
														flights = data.props.flights;
													}
												};
											}}
										>
											<input type="hidden" name="id" value={group.id} />
											<button class="btn btn-ghost btn-xs text-error" title="Ungroup flights">
												<Delete class="text-xs" /> Ungroup
											</button>
										</form>
									</div>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}

		<!-- ===== ALL FLIGHTS VIEW ===== -->
		{:else}
			{#if displayedFlights.length === 0}
				<div class="text-center py-16">
					<Airplane class="mx-auto text-5xl text-base-content/20 mb-4" />
					<h2 class="text-xl font-semibold text-base-content/50">
						{flightView === 'upcoming' ? 'No upcoming flights' : 'No past flights'}
					</h2>
					<p class="text-base-content/40 mt-2">
						{flightView === 'upcoming'
							? 'Connect an email account to scan for flights, or add one manually.'
							: 'Your completed flights will appear here.'}
					</p>
				</div>
			{:else}
				<div class="grid gap-4">
					{#each displayedFlights as flight}
						<div class="card card-border bg-base-100 shadow-sm">
							<div class="card-body p-4 sm:p-6">
								<div class="flex flex-col lg:flex-row lg:items-center gap-4">
									<!-- Airline & Flight Number -->
									<div class="min-w-[140px]">
										<div class="font-bold text-lg">{flight.flight_number}</div>
										<div class="text-sm text-base-content/60">
											{flight.airline_name || flight.airline_code || 'Unknown Airline'}
										</div>
										<span class="badge {statusBadgeClass(flight.status)} badge-sm mt-1">
											{flight.status}
										</span>
									</div>

									<!-- Route -->
									<div class="flex items-center gap-3 grow">
										<div class="text-center">
											<div class="font-bold text-xl">{flight.departure_airport}</div>
											<div class="text-xs text-base-content/50">{flight.departure_city}</div>
											<div class="text-xs text-base-content/60 mt-1">
												{formatDateTime(flight.departure_datetime)}
											</div>
											{#if flight.departure_terminal}
												<div class="text-xs">T{flight.departure_terminal}</div>
											{/if}
										</div>

										<div class="flex-1 flex flex-col items-center">
											<div class="text-xs text-base-content/40 mb-1">
												{formatDuration(flight.duration_minutes)}
											</div>
											<div class="w-full flex items-center gap-1">
												<AirplaneTakeoff class="text-primary text-sm" />
												<div class="h-px bg-base-300 flex-1"></div>
												<Airplane class="text-primary" />
												<div class="h-px bg-base-300 flex-1"></div>
												<AirplaneLanding class="text-primary text-sm" />
											</div>
										</div>

										<div class="text-center">
											<div class="font-bold text-xl">{flight.arrival_airport}</div>
											<div class="text-xs text-base-content/50">{flight.arrival_city}</div>
											<div class="text-xs text-base-content/60 mt-1">
												{formatDateTime(flight.arrival_datetime)}
											</div>
											{#if flight.arrival_terminal}
												<div class="text-xs">T{flight.arrival_terminal}</div>
											{/if}
										</div>
									</div>

									<!-- Details -->
									<div class="flex flex-wrap gap-3 text-sm text-base-content/60 min-w-[150px]">
										{#if flight.booking_reference}
											<div class="flex items-center gap-1" title="Booking Reference">
												<Ticket class="text-xs" />
												{flight.booking_reference}
											</div>
										{/if}
										{#if flight.seat}
											<div class="flex items-center gap-1" title="Seat">
												<SeatRecline class="text-xs" />
												{flight.seat}
											</div>
										{/if}
										{#if flight.cabin_class}
											<div>{cabinLabel(flight.cabin_class)}</div>
										{/if}
									</div>

									<!-- Actions -->
									<div class="flex gap-2">
										<form
											method="POST"
											action="?/deleteFlight"
											use:enhance={() => {
												return async ({ result }) => {
													if (result.type === 'success') {
														flights = flights.filter((f) => f.id !== flight.id);
													}
												};
											}}
										>
											<input type="hidden" name="id" value={flight.id} />
											<button class="btn btn-ghost btn-sm btn-square" title="Delete">
												<Delete class="text-error" />
											</button>
										</form>
									</div>
								</div>

								{#if flight.notes}
									<div class="mt-2 text-sm text-base-content/50 border-t border-base-200 pt-2">
										{flight.notes}
									</div>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
	{/if}

	<!-- ===================== EMAIL ACCOUNTS TAB ===================== -->
	{#if activeTab === 'emails'}
		<div class="flex justify-between items-center mb-4">
			<h2 class="text-lg font-semibold">Connected Email Accounts</h2>
			<button class="btn btn-primary btn-sm" on:click={() => (showAddEmailModal = true)}>
				<Plus /> Connect Email
			</button>
		</div>

		{#if emailAccounts.length === 0}
			<div class="text-center py-16">
				<Email class="mx-auto text-5xl text-base-content/20 mb-4" />
				<h2 class="text-xl font-semibold text-base-content/50">No email accounts connected</h2>
				<p class="text-base-content/40 mt-2">
					Connect your Gmail, Outlook, or other email to automatically scan for flight
					confirmations.
				</p>
			</div>
		{:else}
			<div class="grid gap-4 md:grid-cols-2">
				{#each emailAccounts as account}
					<div class="card card-border bg-base-100 shadow-sm">
						<div class="card-body p-4">
							<div class="flex items-start justify-between">
								<div>
									<h3 class="font-bold">{account.name}</h3>
									<p class="text-sm text-base-content/60">{account.email_address}</p>
									<div class="flex gap-2 mt-2">
										<span class="badge badge-sm badge-outline">{account.provider}</span>
										<span
											class="badge badge-sm {account.is_active ? 'badge-success' : 'badge-error'}"
										>
											{account.is_active ? 'Active' : 'Inactive'}
										</span>
									</div>
									<div class="text-xs text-base-content/40 mt-2 flex items-center gap-1">
										<Clock class="text-xs" />
										Last synced: {formatDate(account.last_synced_at)}
									</div>
									<div class="text-xs text-base-content/40">
										{account.flight_count} flight(s) found
									</div>
								</div>
								<div class="flex gap-1">
									<form
										method="POST"
										action="?/syncEmailAccount"
										use:enhance={() => {
											syncing = account.id;
											return async ({ result }) => {
												syncing = null;
												if (result.type === 'success') {
													await invalidateAll();
													flights = data.props.flights;
													flightGroups = data.props.flightGroups;
													emailAccounts = data.props.emailAccounts;
													stats = data.props.stats;
												}
											};
										}}
									>
										<input type="hidden" name="id" value={account.id} />
										<button
											class="btn btn-ghost btn-sm btn-square"
											title="Sync now"
											disabled={syncing === account.id}
										>
											<Sync class={syncing === account.id ? 'animate-spin' : ''} />
										</button>
									</form>
									<form
										method="POST"
										action="?/deleteEmailAccount"
										use:enhance={() => {
											return async ({ result }) => {
												if (result.type === 'success') {
													emailAccounts = emailAccounts.filter((a) => a.id !== account.id);
												}
											};
										}}
									>
										<input type="hidden" name="id" value={account.id} />
										<button class="btn btn-ghost btn-sm btn-square" title="Delete">
											<Delete class="text-error" />
										</button>
									</form>
								</div>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}

	<!-- ===================== EMAIL ACCOUNTS TAB (continued) ===================== -->
</div>

<!-- ===================== ADD FLIGHT MODAL ===================== -->
{#if showAddFlightModal}
	<dialog class="modal modal-open" on:close={() => (showAddFlightModal = false)}>
		<div class="modal-box max-w-2xl">
			<h3 class="font-bold text-lg mb-4">Add Flight Manually</h3>
			<form
				method="POST"
				action="?/createFlight"
				use:enhance={() => {
					return async ({ result }) => {
						if (result.type === 'success') {
							showAddFlightModal = false;
							await invalidateAll();
							flights = data.props.flights;
							stats = data.props.stats;
						}
					};
				}}
			>
				<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Flight Number *</legend>
						<input
							type="text"
							name="flight_number"
							class="input input-sm w-full"
							placeholder="e.g. LA 1234"
							required
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Airline Name</legend>
						<input
							type="text"
							name="airline_name"
							class="input input-sm w-full"
							placeholder="e.g. LATAM Airlines"
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Airline Code</legend>
						<input
							type="text"
							name="airline_code"
							class="input input-sm w-full"
							placeholder="e.g. LA"
							maxlength="10"
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Booking Reference</legend>
						<input
							type="text"
							name="booking_reference"
							class="input input-sm w-full"
							placeholder="e.g. ABC123"
						/>
					</fieldset>

					<div class="divider sm:col-span-2 my-0">Departure</div>

					<fieldset class="fieldset">
						<legend class="fieldset-legend">Airport Code *</legend>
						<input
							type="text"
							name="departure_airport"
							class="input input-sm w-full"
							placeholder="e.g. GRU"
							maxlength="10"
							required
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">City</legend>
						<input
							type="text"
							name="departure_city"
							class="input input-sm w-full"
							placeholder="e.g. São Paulo"
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Date & Time *</legend>
						<input
							type="datetime-local"
							name="departure_datetime"
							class="input input-sm w-full"
							required
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Terminal / Gate</legend>
						<div class="flex gap-2">
							<input
								type="text"
								name="departure_terminal"
								class="input input-sm w-full"
								placeholder="Terminal"
							/>
							<input
								type="text"
								name="departure_gate"
								class="input input-sm w-full"
								placeholder="Gate"
							/>
						</div>
					</fieldset>

					<div class="divider sm:col-span-2 my-0">Arrival</div>

					<fieldset class="fieldset">
						<legend class="fieldset-legend">Airport Code *</legend>
						<input
							type="text"
							name="arrival_airport"
							class="input input-sm w-full"
							placeholder="e.g. SCL"
							maxlength="10"
							required
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">City</legend>
						<input
							type="text"
							name="arrival_city"
							class="input input-sm w-full"
							placeholder="e.g. Santiago"
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Date & Time *</legend>
						<input
							type="datetime-local"
							name="arrival_datetime"
							class="input input-sm w-full"
							required
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Terminal / Gate</legend>
						<div class="flex gap-2">
							<input
								type="text"
								name="arrival_terminal"
								class="input input-sm w-full"
								placeholder="Terminal"
							/>
							<input
								type="text"
								name="arrival_gate"
								class="input input-sm w-full"
								placeholder="Gate"
							/>
						</div>
					</fieldset>

					<div class="divider sm:col-span-2 my-0">Passenger & Seat</div>

					<fieldset class="fieldset">
						<legend class="fieldset-legend">Passenger Name</legend>
						<input
							type="text"
							name="passenger_name"
							class="input input-sm w-full"
							placeholder="e.g. John Doe"
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Seat</legend>
						<input type="text" name="seat" class="input input-sm w-full" placeholder="e.g. 14A" />
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Cabin Class</legend>
						<select name="cabin_class" class="select select-sm w-full">
							<option value="">—</option>
							<option value="economy">Economy</option>
							<option value="premium_economy">Premium Economy</option>
							<option value="business">Business</option>
							<option value="first">First</option>
						</select>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Status</legend>
						<select name="status" class="select select-sm w-full">
							<option value="upcoming">Upcoming</option>
							<option value="completed">Completed</option>
							<option value="cancelled">Cancelled</option>
						</select>
					</fieldset>

					<fieldset class="fieldset sm:col-span-2">
						<legend class="fieldset-legend">Notes</legend>
						<textarea
							name="notes"
							class="textarea textarea-sm w-full"
							placeholder="Any additional notes..."
							rows="2"
						></textarea>
					</fieldset>
				</div>

				<div class="modal-action">
					<button type="button" class="btn btn-ghost" on:click={() => (showAddFlightModal = false)}>
						Cancel
					</button>
					<button type="submit" class="btn btn-primary">Add Flight</button>
				</div>
			</form>
		</div>
		<form method="dialog" class="modal-backdrop">
			<button on:click={() => (showAddFlightModal = false)}>close</button>
		</form>
	</dialog>
{/if}

<!-- ===================== ADD EMAIL ACCOUNT MODAL ===================== -->
{#if showAddEmailModal}
	<dialog class="modal modal-open" on:close={() => (showAddEmailModal = false)}>
		<div class="modal-box max-w-lg">
			<h3 class="font-bold text-lg mb-4">Connect Email Account</h3>
			<form
				id="emailAccountForm"
				method="POST"
				action="?/createEmailAccount"
				use:enhance={() => {
					return async ({ result }) => {
						if (result.type === 'success') {
							showAddEmailModal = false;
							connectionTested = false;
							connectionTestMessage = '';
							await invalidateAll();
							emailAccounts = data.props.emailAccounts;
						}
					};
				}}
				on:input={() => { connectionTested = false; connectionTestMessage = ''; }}
			>
				<div class="flex flex-col gap-4">
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Account Name *</legend>
						<input
							type="text"
							name="name"
							class="input input-sm w-full"
							placeholder="My Gmail"
							required
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Email Address *</legend>
						<input
							type="email"
							name="email_address"
							class="input input-sm w-full"
							placeholder="you@gmail.com"
							required
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Provider *</legend>
						<select name="provider" class="select select-sm w-full" id="emailProvider"
							on:change={() => { connectionTested = false; connectionTestMessage = ''; }}
						>
							<option value="gmail">Gmail (IMAP)</option>
							<option value="outlook">Outlook (IMAP)</option>
							<option value="imap">Generic IMAP</option>
							<option value="tuta">Tuta (Tutanota)</option>
						</select>
					</fieldset>

					<div class="divider my-0">IMAP Settings</div>
					<p class="text-xs text-base-content/50">
						For Gmail: use an
						<a
							href="https://support.google.com/accounts/answer/185833"
							class="link link-primary"
							target="_blank">App Password</a
						>. Host: imap.gmail.com, Port: 993
					</p>

					<div class="grid grid-cols-2 gap-3">
						<fieldset class="fieldset">
							<legend class="fieldset-legend">IMAP Host</legend>
							<input
								type="text"
								name="imap_host"
								class="input input-sm w-full"
								placeholder="imap.gmail.com"
							/>
						</fieldset>
						<fieldset class="fieldset">
							<legend class="fieldset-legend">IMAP Port</legend>
							<input type="number" name="imap_port" class="input input-sm w-full" value="993" />
						</fieldset>
					</div>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">IMAP Username</legend>
						<input
							type="text"
							name="imap_username"
							class="input input-sm w-full"
							placeholder="Leave blank to use email address"
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Password / App Password</legend>
						<input
							type="password"
							name="imap_password"
							class="input input-sm w-full"
							placeholder="App password"
						/>
					</fieldset>
					<label class="label cursor-pointer justify-start gap-2">
						<input type="checkbox" name="use_ssl" class="checkbox checkbox-sm" checked />
						<span>Use SSL</span>
					</label>

					<div class="divider my-0">Tuta Settings (if applicable)</div>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Tuta Username</legend>
						<input
							type="text"
							name="tuta_user"
							class="input input-sm w-full"
							placeholder="user@tuta.com"
						/>
					</fieldset>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Tuta Password</legend>
						<input
							type="password"
							name="tuta_password"
							class="input input-sm w-full"
							placeholder="Tuta password"
						/>
					</fieldset>

					<!-- Test connection result -->
					{#if connectionTestMessage}
						<div class="alert {connectionTested ? 'alert-success' : 'alert-error'} py-2 text-sm">
							{connectionTestMessage}
						</div>
					{/if}
				</div>

				<div class="modal-action">
					<button type="button" class="btn btn-ghost" on:click={() => { showAddEmailModal = false; connectionTested = false; connectionTestMessage = ''; }}>
						Cancel
					</button>
					<button
						type="button"
						class="btn btn-outline btn-info"
						disabled={testingConnection}
						on:click={handleTestConnection}
					>
						{#if testingConnection}
							<Sync class="animate-spin" /> Testing...
						{:else}
							Test Connection
						{/if}
					</button>
					<button type="submit" class="btn btn-primary" disabled={!connectionTested}>Connect</button>
				</div>
			</form>
		</div>
		<form method="dialog" class="modal-backdrop">
			<button on:click={() => { showAddEmailModal = false; connectionTested = false; connectionTestMessage = ''; }}>close</button>
		</form>
	</dialog>
{/if}

