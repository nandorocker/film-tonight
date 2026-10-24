import {cp,mkdir,rm,readFile,writeFile} from 'node:fs/promises';
await rm('dist',{recursive:true,force:true});await mkdir('dist/vendor/leaflet',{recursive:true});
await cp('web','dist',{recursive:true});
await cp('node_modules/leaflet/dist','dist/vendor/leaflet',{recursive:true});
await cp('assets/icon.svg','dist/icon.svg');
const venues=JSON.parse(await readFile('venues.json','utf8'));
const example=JSON.parse(await readFile('examples/snapshot-2026-10-24.json','utf8'));
await writeFile('dist/demo.json',JSON.stringify({schema_version:2,venues,ttl_seconds:900,snapshots:example.venues.map(v=>({venue_id:v.venue_id,dates:[example.service_date],kind:'manual_sample',generation:example.observed_at,checked_at:example.observed_at,screenings:v.screenings})),attempts:[]}));
await writeFile('dist/_headers',`/*\n  Referrer-Policy: no-referrer\n  X-Content-Type-Options: nosniff\n  Permissions-Policy: geolocation=(self)\n  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; connect-src 'self' https://tile.openstreetmap.org https://*.tile.openstreetmap.org; object-src 'none'; base-uri 'none'; frame-ancestors 'none'\n`);
