import * as L from '/vendor/leaflet/leaflet-src.esm.js';

export function createMap(element, status, highlight) {
  if (!document.querySelector('link[data-leaflet]')) {
    const css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = '/vendor/leaflet/leaflet.css'; css.dataset.leaflet = '';
    css.addEventListener('load', () => map.invalidateSize());
    document.head.append(css);
  }
  const map = L.map(element).setView([50.0755, 14.4378], 12);
  const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);
  let tileFailed = false;
  tiles.on('tileerror', () => { tileFailed = true; status('Map tiles could not load. Cinema markers may still appear; use the table and directions links for reliable navigation.'); });
  const layer = L.layerGroup().addTo(map);
  let markers = new Map();
  let currentRows = [];
  let lastBoundsKey = '';
  function name(row) { return typeof row.venue === 'object' ? row.venue?.name : row.venue_name || row.venue || row.venue_id; }
  function update(rows) {
    currentRows = rows;
    layer.clearLayers(); markers = new Map();
    const groups = new Map();
    rows.forEach((row, index) => {
      const coordinates = row.coordinates;
      if (!Array.isArray(coordinates) || coordinates.length !== 2 || !coordinates.every(Number.isFinite)) return;
      const key = coordinates.join(',');
      if (!groups.has(key)) groups.set(key, { coordinates, items: [] });
      groups.get(key).items.push({ row, index });
    });
    for (const { coordinates, items } of groups.values()) {
      const marker = L.circleMarker([coordinates[1], coordinates[0]], { radius: 9, color: '#174fc4', weight: 2, fillColor: '#174fc4', fillOpacity: .7 }).addTo(layer);
      const popup = document.createElement('div');
      const heading = document.createElement('strong');
      heading.textContent = [...new Set(items.map(({ row }) => name(row)))].join(' / ');
      popup.append(heading);
      for (const { row, index } of items) {
        const button = document.createElement('button');
        const start = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', hour: '2-digit', minute: '2-digit' }).format(new Date(row.starts_at));
        button.type = 'button'; button.textContent = `${start} — ${row.title}`;
        button.addEventListener('click', () => highlight(index));
        popup.append(button); markers.set(index, marker);
      }
      marker.bindPopup(popup);
      marker.bindTooltip(heading.textContent);
      // Circle paths need an explicit keyboard target, unlike Leaflet icon markers.
      const path = marker.getElement();
      path.setAttribute('tabindex', '0'); path.setAttribute('role', 'button');
      path.setAttribute('aria-label', `Show screenings at ${heading.textContent}`);
      path.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); marker.openPopup(); } });
    }
    const boundsKey = [...groups.keys()].sort().join(';');
    if (groups.size && boundsKey !== lastBoundsKey) map.fitBounds([...groups.values()].map(({ coordinates }) => [coordinates[1], coordinates[0]]), { maxZoom: 14, padding: [25, 25] });
    lastBoundsKey = boundsKey;
    map.invalidateSize();
    if (!tileFailed) status(`${groups.size} mapped location${groups.size === 1 ? '' : 's'} for ${rows.length} filtered showtime${rows.length === 1 ? '' : 's'}. Shared locations show all screenings in one popup. Select a screening to highlight it in the table.`);
  }
  return { update, open(index) { const marker = markers.get(index); if (marker) { map.panTo(marker.getLatLng()); marker.openPopup(); } else if (currentRows[index]) status('This cinema has no map coordinates. Its showtime is still available in the table.'); } };
}
