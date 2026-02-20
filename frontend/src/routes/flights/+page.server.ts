import { redirect } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import type { Flight, FlightGroup, EmailAccount, FlightStats } from '$lib/types';
import { fetchCSRFToken } from '$lib/index.server';

const PUBLIC_SERVER_URL = process.env['PUBLIC_SERVER_URL'];
const endpoint = PUBLIC_SERVER_URL || 'http://localhost:8000';

export const load: PageServerLoad = async (event) => {
	if (!event.locals.user) {
		return redirect(302, '/login');
	}
	const sessionId = event.cookies.get('sessionid');
	if (!sessionId) {
		return redirect(302, '/login');
	}

	const headers = { Cookie: `sessionid=${sessionId}` };

	// Fetch flights, email accounts, and stats in parallel (no airline-rules endpoint)
	const [flightsRes, emailAccountsRes, statsRes, flightGroupsRes] = await Promise.all([
		fetch(`${endpoint}/api/flights/flights/`, { headers }),
		fetch(`${endpoint}/api/flights/email-accounts/`, { headers }),
		fetch(`${endpoint}/api/flights/flights/stats/`, { headers }),
		fetch(`${endpoint}/api/flights/flight-groups/`, { headers })
	]);

	let flights: Flight[] = [];
	let flightGroups: FlightGroup[] = [];
	let emailAccounts: EmailAccount[] = [];
	let stats: FlightStats | null = null;

	if (flightsRes.ok) {
		const data = await flightsRes.json();
		flights = data.results ?? data;
	}
	if (flightGroupsRes.ok) {
		const data = await flightGroupsRes.json();
		flightGroups = data.results ?? data;
	}
	if (emailAccountsRes.ok) {
		const data = await emailAccountsRes.json();
		emailAccounts = data.results ?? data;
	}
	if (statsRes.ok) {
		stats = await statsRes.json();
	}

	return {
		props: {
			flights,
			flightGroups,
			emailAccounts,
			stats
		}
	};
};

export const actions: Actions = {
	// Test email connection with raw credentials (before saving)
	testEmailConnection: async (event) => {
		const sessionId = event.cookies.get('sessionid');
		const csrfToken = await fetchCSRFToken();
		const formData = await event.request.formData();

		const provider = formData.get('provider');
		const body: Record<string, unknown> = {
			email_address: formData.get('email_address'),
			provider
		};

		if (provider === 'gmail' || provider === 'outlook' || provider === 'imap') {
			if (provider === 'imap') {
				body.imap_host = formData.get('imap_host') || '';
			}
			body.imap_port = parseInt(formData.get('imap_port')?.toString() || '993');
			body.imap_username = formData.get('imap_username') || '';
			body.imap_password = formData.get('imap_password') || '';
			body.use_ssl = formData.get('use_ssl') === 'on';
		} else if (provider === 'tuta') {
			body.tuta_user = formData.get('tuta_user') || '';
			body.tuta_password = formData.get('tuta_password') || '';
		}

		const res = await fetch(`${endpoint}/api/flights/email-accounts/test-connection/`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Cookie: `csrftoken=${csrfToken}; sessionid=${sessionId}`,
				'X-CSRFToken': csrfToken,
				Referer: event.url.origin
			},
			body: JSON.stringify(body)
		});

		const data = await res.json();
		if (!res.ok) {
			return { success: false, error: data.error || 'Connection failed' };
		}
		return { success: true, message: data.status || 'Connection successful' };
	},

	// Create a new email account
	createEmailAccount: async (event) => {
		const sessionId = event.cookies.get('sessionid');
		const csrfToken = await fetchCSRFToken();
		const formData = await event.request.formData();

		const provider = formData.get('provider');
		const body: Record<string, unknown> = {
			name: formData.get('name'),
			email_address: formData.get('email_address'),
			provider,
			is_active: true
		};

		// Only include fields relevant to the chosen provider
		if (provider === 'gmail' || provider === 'outlook' || provider === 'imap') {
			if (provider === 'imap') {
				body.imap_host = formData.get('imap_host') || '';
			}
			body.imap_port = parseInt(formData.get('imap_port')?.toString() || '993');
			body.imap_username = formData.get('imap_username') || '';
			body.imap_password = formData.get('imap_password') || '';
			body.use_ssl = formData.get('use_ssl') === 'on';
		} else if (provider === 'tuta') {
			body.tuta_user = formData.get('tuta_user') || '';
			body.tuta_password = formData.get('tuta_password') || '';
		}

		const res = await fetch(`${endpoint}/api/flights/email-accounts/`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Cookie: `csrftoken=${csrfToken}; sessionid=${sessionId}`,
				'X-CSRFToken': csrfToken,
				Referer: event.url.origin
			},
			body: JSON.stringify(body)
		});

		if (!res.ok) {
			const error = await res.json();
			return { success: false, error };
		}
		return { success: true };
	},

	// Delete an email account
	deleteEmailAccount: async (event) => {
		const sessionId = event.cookies.get('sessionid');
		const csrfToken = await fetchCSRFToken();
		const formData = await event.request.formData();
		const id = formData.get('id');

		const res = await fetch(`${endpoint}/api/flights/email-accounts/${id}/`, {
			method: 'DELETE',
			headers: {
				Cookie: `csrftoken=${csrfToken}; sessionid=${sessionId}`,
				'X-CSRFToken': csrfToken,
				Referer: event.url.origin
			}
		});

		if (!res.ok) {
			return { success: false };
		}
		return { success: true };
	},

	// Sync an email account
	syncEmailAccount: async (event) => {
		const sessionId = event.cookies.get('sessionid');
		const csrfToken = await fetchCSRFToken();
		const formData = await event.request.formData();
		const id = formData.get('id');

		const res = await fetch(`${endpoint}/api/flights/email-accounts/${id}/sync/`, {
			method: 'POST',
			headers: {
				Cookie: `csrftoken=${csrfToken}; sessionid=${sessionId}`,
				'X-CSRFToken': csrfToken,
				Referer: event.url.origin
			}
		});

		const data = await res.json();
		if (!res.ok) {
			return { success: false, error: data };
		}
		return { success: true, syncResult: data };
	},

	// Create a manual flight
	createFlight: async (event) => {
		const sessionId = event.cookies.get('sessionid');
		const csrfToken = await fetchCSRFToken();
		const formData = await event.request.formData();

		const body = {
			airline_name: formData.get('airline_name') || '',
			airline_code: formData.get('airline_code') || '',
			flight_number: formData.get('flight_number'),
			booking_reference: formData.get('booking_reference') || '',
			departure_airport: formData.get('departure_airport'),
			departure_city: formData.get('departure_city') || '',
			departure_datetime: formData.get('departure_datetime'),
			departure_terminal: formData.get('departure_terminal') || '',
			departure_gate: formData.get('departure_gate') || '',
			arrival_airport: formData.get('arrival_airport'),
			arrival_city: formData.get('arrival_city') || '',
			arrival_datetime: formData.get('arrival_datetime'),
			arrival_terminal: formData.get('arrival_terminal') || '',
			arrival_gate: formData.get('arrival_gate') || '',
			passenger_name: formData.get('passenger_name') || '',
			seat: formData.get('seat') || '',
			cabin_class: formData.get('cabin_class') || '',
			status: formData.get('status') || 'upcoming',
			notes: formData.get('notes') || ''
		};

		const res = await fetch(`${endpoint}/api/flights/flights/`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Cookie: `csrftoken=${csrfToken}; sessionid=${sessionId}`,
				'X-CSRFToken': csrfToken,
				Referer: event.url.origin
			},
			body: JSON.stringify(body)
		});

		if (!res.ok) {
			const error = await res.json();
			return { success: false, error };
		}
		return { success: true };
	},

	// Delete a flight
	deleteFlight: async (event) => {
		const sessionId = event.cookies.get('sessionid');
		const csrfToken = await fetchCSRFToken();
		const formData = await event.request.formData();
		const id = formData.get('id');

		const res = await fetch(`${endpoint}/api/flights/flights/${id}/`, {
			method: 'DELETE',
			headers: {
				Cookie: `csrftoken=${csrfToken}; sessionid=${sessionId}`,
				'X-CSRFToken': csrfToken,
				Referer: event.url.origin
			}
		});

		if (!res.ok) {
			return { success: false };
		}
		return { success: true };
	},

	// Delete a flight group
	deleteFlightGroup: async (event) => {
		const sessionId = event.cookies.get('sessionid');
		const csrfToken = await fetchCSRFToken();
		const formData = await event.request.formData();
		const id = formData.get('id');

		const res = await fetch(`${endpoint}/api/flights/flight-groups/${id}/`, {
			method: 'DELETE',
			headers: {
				Cookie: `csrftoken=${csrfToken}; sessionid=${sessionId}`,
				'X-CSRFToken': csrfToken,
				Referer: event.url.origin
			}
		});

		if (!res.ok) {
			return { success: false };
		}
		return { success: true };
	}
};
