import type { PageServerLoad } from './$types';
import { formatDateInTimezone, formatAllDayDate } from '$lib/dateUtils';
import { isAllDay } from '$lib';
import { redirect } from '@sveltejs/kit';

const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

type CalendarLocation = {
	id: string;
	name: string;
	location?: string | null;
	category?: {
		name?: string | null;
		icon?: string | null;
	} | null;
	visits: Array<{
		id: string;
		start_date: string;
		end_date?: string | null;
		timezone?: string | null;
	}>;
};

type CalendarFlight = {
	id: string;
	flight_number: string;
	airline_name: string;
	departure_airport: string;
	arrival_airport: string;
	departure_city: string;
	arrival_city: string;
	departure_datetime: string | null;
	arrival_datetime: string | null;
	status: string;
};

export const load = (async (event) => {
	let sessionId = event.cookies.get('sessionid');
	const headers: Record<string, string> = {};

	if (sessionId) {
		headers.Cookie = `sessionid=${sessionId}`;
	} else {
		return redirect(302, '/login');
	}

	let [visitedFetch, flightsFetch] = await Promise.all([
		fetch(`${endpoint}/api/locations/calendar/`, { headers }),
		fetch(`${endpoint}/api/flights/flights/calendar/`, { headers })
	]);

	let adventures: CalendarLocation[] = [];
	if (visitedFetch.ok) {
		adventures = (await visitedFetch.json()) as CalendarLocation[];
	}

	let flights: CalendarFlight[] = [];
	if (flightsFetch.ok) {
		flights = (await flightsFetch.json()) as CalendarFlight[];
	}

	// Get user's local timezone as fallback
	const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

	let dates: Array<{
		id: string;
		start: string;
		end: string;
		title: string;
		backgroundColor?: string;
		extendedProps?: {
			adventureName: string;
			category: string;
			icon: string;
			timezone: string;
			isAllDay: boolean;
			formattedStart: string;
			formattedEnd: string;
			location?: string;
			description?: string;
			adventureId?: string;
		};
	}> = [];

	adventures.forEach((adventure) => {
		adventure.visits.forEach((visit) => {
			if (visit.start_date) {
				let startDate = visit.start_date;
				let endDate = visit.end_date || visit.start_date;
				const targetTimezone = visit.timezone || userTimezone;
				const allDay = isAllDay(visit.start_date);

				// Handle timezone conversion for non-all-day events
				if (!allDay) {
					// Convert UTC dates to target timezone
					const startDateTime = new Date(visit.start_date);
					const endDateTime = new Date(visit.end_date || visit.start_date);

					// Format for calendar (ISO string in target timezone)
					startDate = new Intl.DateTimeFormat('sv-SE', {
						timeZone: targetTimezone,
						year: 'numeric',
						month: '2-digit',
						day: '2-digit',
						hour: '2-digit',
						minute: '2-digit',
						hourCycle: 'h23'
					})
						.format(startDateTime)
						.replace(' ', 'T');

					endDate = new Intl.DateTimeFormat('sv-SE', {
						timeZone: targetTimezone,
						year: 'numeric',
						month: '2-digit',
						day: '2-digit',
						hour: '2-digit',
						minute: '2-digit',
						hourCycle: 'h23'
					})
						.format(endDateTime)
						.replace(' ', 'T');
				} else {
					// For all-day events, use just the date part
					startDate = visit.start_date.split('T')[0];

					// For all-day events, add one day to end date to make it inclusive
					const endDateObj = new Date(visit.end_date || visit.start_date);
					endDateObj.setDate(endDateObj.getDate() + 1);
					endDate = endDateObj.toISOString().split('T')[0];
				}

				// Create detailed title with timezone info
				let detailedTitle = adventure.name;
				if (adventure.category?.icon) {
					detailedTitle = `${adventure.category.icon} ${detailedTitle}`;
				}

				// Add time info to title for non-all-day events
				if (!allDay) {
					const startTime = formatDateInTimezone(visit.start_date, targetTimezone);
					detailedTitle += ` (${startTime.split(' ').slice(-2).join(' ')})`;
					if (targetTimezone !== userTimezone) {
						detailedTitle += ` ${targetTimezone}`;
					}
				}

				dates.push({
					id: adventure.id,
					start: startDate,
					end: endDate,
					title: detailedTitle,
					backgroundColor: '#3b82f6',
					extendedProps: {
						adventureName: adventure.name,
						category: adventure.category?.name || 'Adventure',
						icon: adventure.category?.icon || '🗺️',
						timezone: targetTimezone,
						isAllDay: allDay,
						formattedStart: allDay
							? formatAllDayDate(visit.start_date)
							: formatDateInTimezone(visit.start_date, targetTimezone),
						formattedEnd: allDay
							? formatAllDayDate(visit.end_date || visit.start_date)
							: formatDateInTimezone(visit.end_date || visit.start_date, targetTimezone),
						location: adventure.location || '',
						description: '',
						adventureId: adventure.id
					}
				});
			}
		});
	});

	// Add flights to calendar
	flights.forEach((flight) => {
		if (!flight.departure_datetime) return;

		const depDate = new Date(flight.departure_datetime);
		const arrDate = flight.arrival_datetime ? new Date(flight.arrival_datetime) : depDate;

		const startDate = new Intl.DateTimeFormat('sv-SE', {
			timeZone: userTimezone,
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
			hourCycle: 'h23'
		})
			.format(depDate)
			.replace(' ', 'T');

		const endDate = new Intl.DateTimeFormat('sv-SE', {
			timeZone: userTimezone,
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
			hourCycle: 'h23'
		})
			.format(arrDate)
			.replace(' ', 'T');

		const route = `${flight.departure_airport} → ${flight.arrival_airport}`;
		const title = `✈️ ${flight.flight_number} ${route}`;

		const statusColor =
			flight.status === 'completed'
				? '#22c55e'
				: flight.status === 'cancelled'
					? '#9ca3af'
					: '#8b5cf6';

		dates.push({
			id: `flight-${flight.id}`,
			start: startDate,
			end: endDate,
			title,
			backgroundColor: statusColor,
			extendedProps: {
				adventureName: `${flight.airline_name} ${flight.flight_number}`,
				category: 'Flight',
				icon: '✈️',
				timezone: userTimezone,
				isAllDay: false,
				formattedStart: formatDateInTimezone(flight.departure_datetime, userTimezone),
				formattedEnd: formatDateInTimezone(
					flight.arrival_datetime || flight.departure_datetime,
					userTimezone
				),
				location: route,
				description: flight.status
			}
		});
	});

	return {
		props: {
			adventures,
			dates
		}
	};
}) satisfies PageServerLoad;
