<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import TrashCanOutline from '~icons/mdi/trash-can-outline';
	import type { Collection, Flight, User, CollectionItineraryItem } from '$lib/types';
	import { addToast } from '$lib/toasts';
	import { t } from 'svelte-i18n';
	import DeleteWarning from '../DeleteWarning.svelte';
	import Airplane from '~icons/mdi/airplane';
	import AirplaneTakeoff from '~icons/mdi/airplane-takeoff';
	import AirplaneLanding from '~icons/mdi/airplane-landing';
	import DotsHorizontal from '~icons/mdi/dots-horizontal';
	import CalendarRemove from '~icons/mdi/calendar-remove';
	import Launch from '~icons/mdi/launch';
	import Globe from '~icons/mdi/globe';
	import { goto } from '$app/navigation';

	let isActionsMenuOpen = false;
	let actionsMenuRef: HTMLDivElement | null = null;
	const ACTIONS_CLOSE_EVENT = 'card-actions-close';
	const handleCloseEvent = () => (isActionsMenuOpen = false);

	function handleDocumentClick(event: MouseEvent) {
		if (!isActionsMenuOpen) return;
		const target = event.target as Node | null;
		if (actionsMenuRef && target && !actionsMenuRef.contains(target)) {
			isActionsMenuOpen = false;
		}
	}

	function closeAllMenus() {
		window.dispatchEvent(new CustomEvent(ACTIONS_CLOSE_EVENT));
	}

	onMount(() => {
		document.addEventListener('click', handleDocumentClick);
		window.addEventListener(ACTIONS_CLOSE_EVENT, handleCloseEvent);
		return () => {
			document.removeEventListener('click', handleDocumentClick);
			window.removeEventListener(ACTIONS_CLOSE_EVENT, handleCloseEvent);
		};
	});

	const dispatch = createEventDispatcher();

	export let flight: Flight;
	export let user: User | null = null;
	export let collection: Collection | null = null;
	export let readOnly: boolean = false;
	export let itineraryItem: CollectionItineraryItem | null = null;

	function formatDateTime(iso: string): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return d.toLocaleDateString(undefined, {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatDuration(minutes: number | null): string {
		if (!minutes) return '';
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		return `${h}h ${m}m`;
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

	let isWarningModalOpen: boolean = false;

	async function deleteFlight() {
		let res = await fetch(`/api/flights/${flight.id}`, {
			method: 'DELETE',
			headers: { 'Content-Type': 'application/json' }
		});
		if (!res.ok) {
			addToast('error', $t('flights.flight_delete_error') || 'Failed to delete flight');
		} else {
			addToast('info', $t('flights.flight_deleted') || 'Flight deleted');
			isWarningModalOpen = false;
			dispatch('delete', flight.id);
		}
	}

	async function removeFromItinerary() {
		let itineraryItemId = itineraryItem?.id;
		let res = await fetch(`/api/itineraries/${itineraryItemId}`, {
			method: 'DELETE'
		});
		if (res.ok) {
			addToast('info', $t('itinerary.item_remove_success'));
			dispatch('removeFromItinerary', itineraryItem);
		} else {
			addToast('error', $t('itinerary.item_remove_error'));
		}
	}
</script>

{#if isWarningModalOpen}
	<DeleteWarning
		title={$t('flights.delete_flight') || 'Delete Flight'}
		button_text="Delete"
		description={$t('flights.flight_delete_confirm') || 'Are you sure you want to delete this flight?'}
		is_warning={false}
		on:close={() => (isWarningModalOpen = false)}
		on:confirm={deleteFlight}
	/>
{/if}

<div
	class="card w-full max-w-md bg-base-300 shadow hover:shadow-md transition-all duration-200 border border-base-300 group"
	aria-label="flight-card"
>
	<!-- Header with airplane icon -->
	<div class="relative overflow-hidden rounded-t-2xl bg-gradient-to-r from-primary/10 to-primary/5 p-4">
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-2">
				<Airplane class="w-6 h-6 text-primary" />
				<span class="font-bold text-lg">{flight.flight_number}</span>
				{#if flight.airline_name}
					<span class="text-sm text-base-content/60">{flight.airline_name}</span>
				{/if}
			</div>
			<span class="badge {statusBadgeClass(flight.status)} badge-sm">
				{flight.status}
			</span>
		</div>
	</div>

	<div class="card-body p-4 space-y-3 min-w-0">
		<!-- Header with actions -->
		<div class="flex items-start justify-between gap-3">
			<div class="flex-1 min-w-0"></div>

			<div class="flex items-center gap-2">
				<button
					class="btn btn-sm p-1 text-base-content"
					aria-label="open-details"
					on:click={() => goto('/flights')}
				>
					<Launch class="w-4 h-4" />
				</button>

				{#if !readOnly && user && (collection?.user === user.uuid || collection?.shared_with?.includes(user.uuid))}
					<div
						class="dropdown dropdown-end relative z-50"
						class:dropdown-open={isActionsMenuOpen}
						bind:this={actionsMenuRef}
					>
						<button
							type="button"
							class="btn btn-square btn-sm p-1 text-base-content"
							aria-haspopup="menu"
							on:click|stopPropagation={() => {
								if (isActionsMenuOpen) {
									isActionsMenuOpen = false;
									return;
								}
								closeAllMenus();
								isActionsMenuOpen = true;
							}}
						>
							<DotsHorizontal class="w-5 h-5" />
						</button>
						<ul
							tabindex="-1"
							class="dropdown-content menu bg-base-100 rounded-box z-[9999] w-52 p-2 shadow-lg border border-base-300"
						>
							{#if itineraryItem && itineraryItem.id}
								{#if !itineraryItem.is_global}
									<li>
										<button
											on:click={() => {
												isActionsMenuOpen = false;
												dispatch('moveToGlobal', { type: 'flight', id: flight.id });
											}}
											class="flex items-center gap-2"
										>
											<Globe class="w-4 h-4" />
											{$t('itinerary.move_to_trip_context') || 'Move to Trip Context'}
										</button>
									</li>
								{/if}
								<li>
									<button
										on:click={() => {
											isActionsMenuOpen = false;
											removeFromItinerary();
										}}
										class="text-error flex items-center gap-2"
									>
										<CalendarRemove class="w-4 h-4 text-error" />
										{#if itineraryItem.is_global}
											{$t('itinerary.remove_from_trip_context') || 'Remove from Trip Context'}
										{:else}
											{$t('itinerary.remove_from_itinerary')}
										{/if}
									</button>
								</li>
								<div class="divider my-1"></div>
							{/if}
							<li>
								<button
									class="text-error flex items-center gap-2"
									on:click={() => {
										isActionsMenuOpen = false;
										isWarningModalOpen = true;
									}}
								>
									<TrashCanOutline class="w-4 h-4" />
									{$t('adventures.delete')}
								</button>
							</li>
						</ul>
					</div>
				{/if}
			</div>
		</div>

		<!-- Route display: DEP → ARR -->
		<div class="bg-base-200 rounded-lg px-3 py-3">
			<div class="flex items-center gap-2">
				<div class="text-center flex-shrink-0">
					<div class="font-bold text-xl">{flight.departure_airport}</div>
					{#if flight.departure_city}
						<div class="text-xs text-base-content/50">{flight.departure_city}</div>
					{/if}
				</div>
				<div class="flex-1 flex flex-col items-center">
					{#if flight.duration_minutes}
						<div class="text-xs text-base-content/40">
							{formatDuration(flight.duration_minutes)}
						</div>
					{/if}
					<div class="w-full flex items-center gap-1">
						<div class="h-px bg-base-300 flex-1"></div>
						<Airplane class="text-primary text-sm" />
						<div class="h-px bg-base-300 flex-1"></div>
					</div>
				</div>
				<div class="text-center flex-shrink-0">
					<div class="font-bold text-xl">{flight.arrival_airport}</div>
					{#if flight.arrival_city}
						<div class="text-xs text-base-content/50">{flight.arrival_city}</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Departure / Arrival times -->
		<div class="flex flex-col gap-2">
			<div class="flex items-center gap-2 text-sm">
				<AirplaneTakeoff class="w-4 h-4 text-base-content/60" />
				<span class="text-base-content">{formatDateTime(flight.departure_datetime)}</span>
			</div>
			<div class="flex items-center gap-2 text-sm">
				<AirplaneLanding class="w-4 h-4 text-base-content/60" />
				<span class="text-base-content">{formatDateTime(flight.arrival_datetime)}</span>
			</div>
		</div>

		<!-- Extra details -->
		<div class="flex flex-wrap items-center gap-2 text-sm">
			{#if flight.booking_reference}
				<span class="badge badge-ghost badge-sm">Ref: {flight.booking_reference}</span>
			{/if}
			{#if flight.seat}
				<span class="badge badge-ghost badge-sm">Seat {flight.seat}</span>
			{/if}
			{#if flight.cabin_class}
				<span class="badge badge-ghost badge-sm">{flight.cabin_class}</span>
			{/if}
		</div>
	</div>
</div>
