<script lang="ts">
	import { onMount } from 'svelte';
	import FullMap from '$lib/components/map/FullMap.svelte';
	import { GeoJSON, LineLayer, Marker } from 'svelte-maplibre';
	import Airplane from '~icons/mdi/airplane';
	import { t } from 'svelte-i18n';

	type GeoJSONFeatureCollection = {
		type: 'FeatureCollection';
		features: any[];
	};

	let routesGeoJson: GeoJSONFeatureCollection = { type: 'FeatureCollection', features: [] };
	let airportsGeoJson: GeoJSONFeatureCollection = { type: 'FeatureCollection', features: [] };
	let loading = true;
	let error = '';

	onMount(async () => {
		try {
			const res = await fetch('/api/flights/flights/routes/');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			routesGeoJson = data.routes || { type: 'FeatureCollection', features: [] };
			airportsGeoJson = data.airports || { type: 'FeatureCollection', features: [] };
		} catch (e: any) {
			error = e.message || 'Failed to load flight routes';
		} finally {
			loading = false;
		}
	});

	// Extract airport markers from GeoJSON for Marker components
	$: airportMarkers = airportsGeoJson.features.map((f) => ({
		lngLat: f.geometry.coordinates as [number, number],
		iata: f.properties.iata_code as string,
		name: f.properties.name as string,
		city: f.properties.city_name as string
	}));
</script>

{#if loading}
	<div class="flex items-center justify-center h-full">
		<span class="loading loading-spinner loading-lg"></span>
	</div>
{:else if error}
	<div class="alert alert-error">
		<span>{error}</span>
	</div>
{:else if routesGeoJson.features.length === 0}
	<div class="flex flex-col items-center justify-center h-full text-base-content/50">
		<Airplane class="text-5xl mb-4" />
		<p class="text-lg">No flight routes to display</p>
		<p class="text-sm mt-1">Flight routes will appear once airports are loaded.</p>
	</div>
{:else}
	<div class="w-full h-full rounded-lg overflow-hidden">
		<FullMap zoom={2}>
			<!-- Flight route lines -->
			<GeoJSON id="flight-routes" data={routesGeoJson}>
				<LineLayer
					id="flight-routes-completed"
					filter={['==', ['get', 'status'], 'completed']}
					paint={{
						'line-color': '#22c55e',
						'line-width': 2,
						'line-opacity': 0.8
					}}
				/>
				<LineLayer
					id="flight-routes-upcoming"
					filter={['==', ['get', 'status'], 'upcoming']}
					paint={{
						'line-color': '#3b82f6',
						'line-width': 2,
						'line-opacity': 0.8,
						'line-dasharray': [4, 2]
					}}
				/>
				<LineLayer
					id="flight-routes-cancelled"
					filter={['==', ['get', 'status'], 'cancelled']}
					paint={{
						'line-color': '#9ca3af',
						'line-width': 1,
						'line-opacity': 0.5,
						'line-dasharray': [2, 2]
					}}
				/>
			</GeoJSON>

			<!-- Airport markers -->
			{#each airportMarkers as airport (airport.iata)}
				<Marker lngLat={airport.lngLat}>
					<div
						class="flex flex-col items-center cursor-pointer"
						title="{airport.iata} - {airport.name} ({airport.city})"
					>
						<div
							class="w-6 h-6 rounded-full bg-primary text-primary-content flex items-center justify-center text-xs font-bold shadow-md"
						>
							{airport.iata.charAt(0)}
						</div>
						<span
							class="text-xs font-bold mt-0.5 px-1 bg-base-100/80 rounded shadow-sm"
						>
							{airport.iata}
						</span>
					</div>
				</Marker>
			{/each}
		</FullMap>
	</div>
{/if}
