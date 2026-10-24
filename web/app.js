import { select, pragueDate } from './query.js';

const $ = (selector) => document.querySelector(selector);
const form = $('#filters');
const demo = new URLSearchParams(location.search).get('demo') === '1';
const time = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', hour: '2-digit', minute: '2-digit' });
const timestamp = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', dateStyle: 'medium', timeStyle: 'short' });
const labels = { english_audio: 'English audio', english_subtitles: 'English subtitles', english_friendly: 'English-friendly', unknown: 'Unknown', conflict: 'Conflicting evidence', not_english: 'Not English-accessible' };
let snapshot = null;
let result = null;
let origin = null;
let mapView = null;
let mapLoading = null;
let lastError = '';
let locating = false;
let locationRevision = 0;
let loadRevision = 0;

export function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}
const e = escapeHTML;
function safeLink(url, text, className = '') {
  try {
    const parsed = new URL(url);
    if (!['https:', 'http:'].includes(parsed.protocol)) return '';
    return `<a class="${className}" href="${e(parsed.href)}" target="_blank" rel="noopener noreferrer">${e(text)}<span class="sr-only"> (opens a new tab)</span></a>`;
  } catch { return ''; }
}
function dateText(value) {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? timestamp.format(date) : 'Not checked';
}
function age(value) {
  if (!value || !Number.isFinite(new Date(value).getTime())) return 'Check time unavailable';
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
  return minutes < 1 ? 'Checked just now' : minutes < 60 ? `Checked ${minutes} min ago` : minutes < 1440 ? `Checked ${Math.floor(minutes / 60)} h ago` : `Checked ${Math.floor(minutes / 1440)} days ago`;
}
function venueName(row) {
  return typeof row.venue === 'object' ? row.venue?.name : row.venue_name || row.venue || row.venue_id;
}
function filters() {
  const data = new FormData(form);
  return {
    date: data.get('date'), after: data.get('after'), remaining: data.has('remaining'),
    buffer_minutes: Number(data.get('buffer_minutes') || 0), access: data.get('access'),
    venue: data.get('venue'), q: data.get('q'), format: data.get('format'), origin,
    radius_km: origin && data.get('radius_km') ? Number(data.get('radius_km')) : null,
  };
}
function evidence(row) {
  const raw = row.language_evidence;
  const text = typeof raw === 'string' ? raw : raw == null ? 'No screening-specific evidence provided.' : JSON.stringify(raw, null, 2);
  return `<details><summary>Evidence</summary><p>${e(text)}</p><p>Audio: ${e(row.audio || 'unknown')}<br>Subtitles: ${e(row.subtitles || 'unknown')}</p><p>${safeLink(row.source_url, 'Screening source')}</p><p>Checked: ${e(dateText(row.checked_at))}<br>Freshness: ${e(row.freshness || 'unknown')}<br>Origin: ${e(typeof row.origin === 'object' ? JSON.stringify(row.origin) : row.origin || 'cache')}</p></details>`;
}
function render() {
  if (!snapshot || !form.reportValidity()) return;
  if (!demo && snapshot.service_date && snapshot.service_date !== form.elements.date.value) {
    $('#status').textContent = 'Loading the selected date. Previous listings remain below until it is ready.';
    return;
  }
  try { result = select(snapshot, filters(), new Date()); }
  catch {
    $('#status').textContent = 'These listings could not be read. Try refreshing.';
    $('#status').className = 'error';
    return;
  }
  const rows = result.screenings;
  $('#results-heading').textContent = `${rows.length} ${rows.length === 1 ? 'showtime' : 'showtimes'}`;
  const stale = rows.filter((row) => row.freshness !== 'fresh').length;
  $('#status').className = lastError ? 'error' : '';
  $('#status').textContent = [demo ? 'Historical example data.' : `Snapshot generated ${dateText(snapshot.generated_at)} (Prague).`, `${result.summary.fresh_venues}/${result.summary.total_venues} cinemas fresh. Coverage is incomplete.`, result.summary.failed_venues ? `${result.summary.failed_venues} latest source checks failed.` : '', stale ? `${stale} listing${stale === 1 ? '' : 's'} not marked fresh; check the source.` : '', lastError].filter(Boolean).join(' ');
  $('#results').innerHTML = rows.length ? `<table><caption class="sr-only">Filtered Prague cinema showtimes, in chronological order. All times Europe/Prague.</caption><thead><tr><th scope="col">Start</th><th scope="col">Film</th><th scope="col">Cinema</th><th scope="col">English access</th><th scope="col">Tickets</th></tr></thead><tbody>${rows.map((row, index) => {
    const coordinates = row.coordinates;
    const directions = coordinates ? safeLink(`https://www.google.com/maps/dir/?api=1&destination=${coordinates[1]},${coordinates[0]}`, 'Directions') : '';
    return `<tr id="screening-${index}" data-index="${index}"><td class="time"><time datetime="${e(row.starts_at)}">${e(time.format(new Date(row.starts_at)))}</time></td><td><div class="film-title">${e(row.title)}</div><div class="meta">${e(row.format || 'Format not listed')}${row.hall ? ` · ${e(row.hall)}` : ''}</div></td><td>${coordinates ? `<button type="button" class="venue-button" data-venue-index="${index}" aria-label="Show ${e(venueName(row))} on map">${e(venueName(row))}</button>` : e(venueName(row))}<div class="meta">${row.distance_km != null ? `${e(Number(row.distance_km).toFixed(1))} km · ` : ''}${directions || 'Location unavailable'}</div></td><td><div class="access">${e(labels[row.access] || row.access || 'Unknown')}</div>${evidence(row)}</td><td>${safeLink(row.booking_url, 'Check tickets', 'ticket') || safeLink(row.source_url, 'Cinema listing', 'ticket') || 'No booking link'}<div class="meta">${e(row.price == null ? 'Price not listed' : `${row.price} ${row.currency || ''}`)}</div><div class="meta">${e(age(row.checked_at))}</div></td></tr>`;
  }).join('')}</tbody></table>` : '<div class="empty"><strong>No matching showtimes.</strong><p>Try an earlier start, another date or cinema, or a wider radius. Coverage may be incomplete; check the details below.</p></div>';
  const summary = result.summary || {};
  $('#coverage-content').innerHTML = `<p>${e(summary.fresh_venues ?? 0)} of ${e(summary.total_venues ?? snapshot.venues.length)} cinemas have fresh coverage. A successful check does not mean a cinema has published this date.</p>${summary.excluded_by_radius?.length ? `<p>${e(summary.excluded_by_radius.length)} cinemas excluded by radius: ${e(summary.excluded_by_radius.join(', '))}. Clear the radius for citywide results.</p>` : ''}${summary.unmapped_venue_ids?.length ? `<p>No map coordinates: ${e(summary.unmapped_venue_ids.join(', '))}. These cinemas cannot be included in a radius search.</p>` : ''}<ul>${(result.coverage || []).map((venue) => `<li><strong>${e(venue.name)}</strong>: ${e(venue.state || 'missing')}<br>Checked: ${e(dateText(venue.checked_at))}${venue.blocker ? `<br>${e(venue.blocker)}` : ''}${venue.last_attempt ? `<br>Last attempt: ${e(typeof venue.last_attempt === 'object' ? `${venue.last_attempt.outcome || ''} ${venue.last_attempt.detail || ''} (${dateText(venue.last_attempt.checked_at)})` : venue.last_attempt)}` : ''}<br>${e(venue.counts?.qualifying ?? 0)} confirmed, ${e(venue.counts?.unknown ?? 0)} unknown, ${e(venue.counts?.conflict ?? 0)} conflicting.</li>`).join('')}</ul><p>Unknown or conflicting English access is excluded by default. Missing, unpublished, failed or unimplemented cinemas are not proof that nothing is playing.</p>`;
  if (mapView) mapView.update(rows);
}

async function refresh() {
  const revision = ++loadRevision;
  const requestedDate = form.elements.date.value;
  const button = $('#refresh');
  button.disabled = true;
  $('#results').setAttribute('aria-busy', 'true');
  $('#status').textContent = snapshot ? 'Refreshing… previous listings remain below.' : 'Loading cinema listings…';
  try {
    const response = await fetch(demo ? '/demo.json' : `/api/v1/snapshot?date=${encodeURIComponent(requestedDate)}`, { cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const next = await response.json();
    if (revision !== loadRevision || (!demo && requestedDate !== form.elements.date.value)) return;
    if (next.schema_version !== 2 || !Array.isArray(next.venues) || !Array.isArray(next.snapshots)) throw new Error('Unsupported snapshot');
    if (demo && !snapshot) {
      const dates = next.snapshots.flatMap((entry) => entry.dates || entry.screenings?.map((row) => pragueDate(new Date(row.starts_at))) || []).sort();
      if (dates.length) $('#date').value = dates[0];
    }
    // Keep the last good response if a replacement cannot be queried.
    select(next, filters(), new Date());
    snapshot = next;
    lastError = '';
    const selected = form.elements.venue.value;
    $('#venue').innerHTML = '<option value="">All cinemas</option>' + snapshot.venues.map((venue) => `<option value="${e(venue.id)}">${e(venue.name)}</option>`).join('');
    form.elements.venue.value = selected;
    render();
  } catch {
    if (revision !== loadRevision || (!demo && requestedDate !== form.elements.date.value)) return;
    if (!demo && snapshot?.service_date) form.elements.date.value = snapshot.service_date;
    lastError = snapshot ? 'Refresh failed. Showing the last successfully loaded snapshot; its age continues to increase.' : 'Listings could not be loaded. Check your connection and try Refresh listings.';
    if (snapshot) render();
    else { $('#status').textContent = lastError; $('#status').className = 'error'; $('#results').innerHTML = '<p class="empty">No cached listings have been loaded in this page. No showtimes can be confirmed.</p>'; }
  } finally {
    if (revision === loadRevision) {
      button.disabled = false;
      $('#results').setAttribute('aria-busy', 'false');
    }
  }
}

function highlight(index) {
  document.querySelectorAll('tr.selected').forEach((row) => row.classList.remove('selected'));
  const row = $(`#screening-${index}`);
  if (row) { row.classList.add('selected'); row.tabIndex = -1; row.focus({ preventScroll: true }); row.scrollIntoView({ behavior: 'instant', block: 'center' }); }
}
async function showMap(index) {
  if (!result) return;
  $('#show-map').disabled = true;
  $('#map-status').textContent = 'Loading map… The showtimes above are still available.';
  try {
    if (!mapLoading) mapLoading = import('./map.js');
    const { createMap } = await mapLoading;
    if (!mapView) {
      $('#map').hidden = false;
      mapView = createMap($('#map'), (message) => { $('#map-status').textContent = message; }, highlight);
    }
    mapView.update(result.screenings);
    if (index != null) { mapView.open(index); $('#map').scrollIntoView({ behavior: 'instant', block: 'center' }); }
  } catch {
    mapLoading = null;
    $('#map').hidden = true;
    $('#map-status').textContent = 'The map could not load. Use the showtime table and cinema directions links instead.';
  } finally { $('#show-map').disabled = false; }
}

$('#date').value = pragueDate(new Date());
$('#demo-banner').hidden = !demo;
if (demo) form.elements.remaining.checked = false;
form.addEventListener('submit', (event) => { event.preventDefault(); render(); });
form.addEventListener('input', (event) => {
  if (event.target === form.elements.date && !demo) {
    ++loadRevision;
    $('#refresh').disabled = false;
    $('#results').setAttribute('aria-busy', 'false');
    if (form.checkValidity() && form.elements.date.value !== snapshot?.service_date) refresh();
    else render();
    return;
  }
  if (!form.checkValidity()) return;
  render();
});
$('#refresh').addEventListener('click', refresh);
$('#show-map').addEventListener('click', () => showMap());
$('#results').addEventListener('click', (event) => {
  const button = event.target.closest('[data-venue-index]');
  if (button) showMap(Number(button.dataset.venueIndex));
});
$('#locate').addEventListener('click', () => {
  if (locating) return;
  if (!navigator.geolocation) { $('#location-status').textContent = 'Location is unavailable in this browser. All cinemas remain visible.'; return; }
  locating = true;
  const revision = ++locationRevision;
  $('#locate').disabled = true;
  $('#location-status').textContent = 'Waiting for location permission…';
  navigator.geolocation.getCurrentPosition((position) => {
    if (revision !== locationRevision) return;
    locating = false; $('#locate').disabled = false;
    origin = [position.coords.longitude, position.coords.latitude];
    $('#location-status').textContent = 'Location enabled for this page only. Choose a radius to limit results.';
    $('#clear-location').hidden = false;
    render();
  }, () => {
    if (revision !== locationRevision) return;
    locating = false; $('#locate').disabled = false;
    $('#location-status').textContent = 'Location was not available or permission was denied. You can still browse every cinema.';
  }, { enableHighAccuracy: false, timeout: 12000, maximumAge: 60000 });
});
$('#clear-location').addEventListener('click', () => {
  locationRevision++; locating = false; origin = null;
  $('#locate').disabled = false; $('#radius').value = ''; $('#clear-location').hidden = true;
  $('#location-status').textContent = 'Location cleared. All cinemas are visible without a radius limit.';
  render();
});
$('#radius').addEventListener('change', () => {
  if (!origin && $('#radius').value) $('#location-status').textContent = 'Use “Use my location” first. No radius filter has been applied.';
});
// Re-evaluate imminent starts and freshness without sending location or fetching.
setInterval(() => { if (snapshot && !document.hidden) render(); }, 60000);
refresh();
