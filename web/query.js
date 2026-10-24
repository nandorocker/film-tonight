// Pure, network-free selection shared by the Pages API and browser.
export const ACCESSIBLE = new Set(['english_audio', 'english_subtitles', 'english_friendly']);
const dt = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Prague', year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
export function pragueParts(now = new Date()) {
  return Object.fromEntries(dt.formatToParts(now).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));
}
export function pragueDate(now = new Date()) {const p=pragueParts(now);return `${p.year}-${p.month}-${p.day}`;}
export function distanceKm(a,b) {
  const r=x=>x*Math.PI/180, dlat=r(b[1]-a[1]),dlon=r(b[0]-a[0]);
  return 6371*2*Math.asin(Math.min(1,Math.sqrt(Math.sin(dlat/2)**2+Math.cos(r(a[1]))*Math.cos(r(b[1]))*Math.sin(dlon/2)**2)));
}
export function filters(input={}, now=new Date()) {
  const f={date:pragueDate(now),after:'18:00',remaining:true,buffer_minutes:0,access:'confirmed',venue:'',q:'',format:'',origin:null,radius_km:null,...input};
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.date)||!Number.isFinite(Date.parse(f.date))||new Date(f.date).toISOString().slice(0,10)!==f.date) throw new Error('Use a valid YYYY-MM-DD date');
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(f.after)) throw new Error('Use a valid HH:MM start time');
  if (!['confirmed','all','english_audio','english_subtitles','english_friendly','unknown','conflict','not_english'].includes(f.access)) throw new Error('Unknown English access filter');
  f.buffer_minutes=Number(f.buffer_minutes);
  if (!Number.isFinite(f.buffer_minutes)||f.buffer_minutes<0||f.buffer_minutes>240) throw new Error('Buffer must be 0–240 minutes');
  if (f.origin && (!Array.isArray(f.origin)||f.origin.length!==2||!f.origin.every(Number.isFinite)||Math.abs(f.origin[0])>180||Math.abs(f.origin[1])>90)) throw new Error('Origin must be [longitude, latitude]');
  if(f.radius_km!==null&&f.radius_km!=='') {
    f.radius_km=Number(f.radius_km);
    if(!f.origin||!Number.isFinite(f.radius_km)||f.radius_km<=0||f.radius_km>100)throw new Error('Radius needs an origin and must be 0–100 km');
  } else f.radius_km=null;
  if(typeof f.remaining!=='boolean')throw new Error('remaining must be boolean');
  return f;
}
export function select(snapshot,input={},now=new Date()) {
  now=new Date(now);const f=filters(input,now), byVenue=new Map((snapshot.snapshots||[]).map(x=>[x.venue_id,x]));
  const attempts=new Map((snapshot.attempts||[]).map(x=>[x.venue_id,x]));
  const screenings=[],coverage=[],excluded=new Set(),unmapped=new Set();
  for(const venue of snapshot.venues||[]) {
    const s=byVenue.get(venue.id), age=s?(now-new Date(s.checked_at))/1000:Infinity;
    const published=s?.dates?.includes(f.date), demo=s?.kind==='manual_sample';
    const state=!s?'missing':!published?'unpublished':demo?'sample':age>=0&&age<=(snapshot.ttl_seconds??900)?'fresh':'stale';
    const counts={total:0,qualifying:0,unknown:0,conflict:0,non_film:0};
    for(const row of s?.screenings||[]) {
      const start=new Date(row.starts_at),p=pragueParts(start);
      if(`${p.year}-${p.month}-${p.day}`!==f.date)continue;
      counts.total++;if(ACCESSIBLE.has(row.access))counts.qualifying++;
      if(row.access==='unknown')counts.unknown++;if(row.access==='conflict')counts.conflict++;
      if(row.event_type==='non_film'){counts.non_film++;continue;}
      if(`${p.hour}:${p.minute}`<f.after)continue;
      if(f.remaining&&start.getTime()<=now.getTime()+f.buffer_minutes*60000)continue;
      if(f.access==='confirmed'?!ACCESSIBLE.has(row.access):f.access!=='all'&&f.access!==row.access)continue;
      if(f.venue&&venue.id!==f.venue)continue;
      if(f.q&&!String(row.title).toLocaleLowerCase().includes(f.q.toLocaleLowerCase()))continue;
      if(f.format&&!String(row.format||'').toLowerCase().includes(f.format.toLowerCase()))continue;
      const distance=f.origin&&venue.coordinates?distanceKm(f.origin,venue.coordinates):null;
      if(f.radius_km!==null&&(distance===null||distance>f.radius_km)){excluded.add(venue.id);continue;}
      if(!venue.coordinates)unmapped.add(venue.id);
      screenings.push({...row,venue_id:venue.id,venue:venue.name,coordinates:venue.coordinates,distance_km:distance===null?null:Math.round(distance*10)/10,
        checked_at:s.checked_at,freshness:state,origin:demo?'manual_sample':'live',source_url:row.source_url||venue.url});
    }
    coverage.push({...venue,state,checked_at:s?.checked_at??null,last_attempt:attempts.get(venue.id)??null,counts,
      horizon:s?.dates||[],blocker:venue.blocker??null});
  }
  screenings.sort((a,b)=>f.origin?(a.distance_km??Infinity)-(b.distance_km??Infinity)||Date.parse(a.starts_at)-Date.parse(b.starts_at):Date.parse(a.starts_at)-Date.parse(b.starts_at)||a.id.localeCompare(b.id));
  const {origin:privateOrigin,...publicFilters}=f;
  return {schema_version:2,service_date:f.date,timezone:'Europe/Prague',generated_at:now.toISOString(),filters:{...publicFilters,origin_supplied:!!privateOrigin},
    screenings,coverage,total:screenings.length,summary:{total_venues:coverage.length,fresh_venues:coverage.filter(x=>x.state==='fresh').length,
      failed_venues:coverage.filter(x=>x.last_attempt?.outcome==='error').length,
      excluded_by_radius:[...excluded],unmapped_venue_ids:[...unmapped]}};
}
export function geojson(payload) {
  const grouped=new Map();for(const row of payload.screenings){if(!row.coordinates)continue;const items=grouped.get(row.venue_id)||[];items.push(row);grouped.set(row.venue_id,items);}
  return {type:'FeatureCollection',features:[...grouped].map(([id,rows])=>({type:'Feature',geometry:{type:'Point',coordinates:rows[0].coordinates},properties:{venue_id:id,name:rows[0].venue,count:rows.length,screenings:rows}})),unmapped_venue_ids:payload.summary.unmapped_venue_ids,service_date:payload.service_date};
}
