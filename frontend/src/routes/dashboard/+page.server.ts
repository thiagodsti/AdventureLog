import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
import type { Flight, Location } from '$lib/types';

const serverEndpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

export const load = (async (event) => {
	if (!event.locals.user) {
		return redirect(302, '/login');
	} else {
		let adventures: Location[] = [];
		const headers = {
			Cookie: `sessionid=${event.cookies.get('sessionid')}`
		};

		let [initialFetch, statsRes, upcomingFlightsRes, flightStatsRes] = await Promise.all([
			event.fetch(`${serverEndpoint}/api/locations/`, { headers, credentials: 'include' }),
			event.fetch(`${serverEndpoint}/api/stats/counts/${event.locals.user.username}/`, {
				headers
			}),
			event.fetch(`${serverEndpoint}/api/flights/flights/upcoming/`, { headers }),
			event.fetch(`${serverEndpoint}/api/flights/flights/stats/`, { headers })
		]);

		let stats = null;
		if (statsRes.ok) {
			stats = await statsRes.json();
		} else {
			console.error('Failed to fetch user stats');
		}

		let upcomingFlights: Flight[] = [];
		if (upcomingFlightsRes.ok) {
			upcomingFlights = (await upcomingFlightsRes.json()) as Flight[];
		}

		let flightStats = null;
		if (flightStatsRes.ok) {
			flightStats = await flightStatsRes.json();
		}

		if (!initialFetch.ok) {
			let error_message = await initialFetch.json();
			console.error(error_message);
			console.error('Failed to fetch visited adventures');
			return redirect(302, '/login');
		} else {
			let res = await initialFetch.json();
			let visited = res.results as Location[];
			// only get the first 3 adventures or less if there are less than 3
			adventures = visited.slice(0, 3);
		}

		return {
			props: {
				adventures,
				stats,
				upcomingFlights: upcomingFlights.slice(0, 3),
				flightStats
			}
		};
	}
}) satisfies PageServerLoad;
