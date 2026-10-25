import {test} from 'node:test';import assert from 'node:assert/strict';
import {select,geojson,pragueDate} from '../web/query.js';
import venues from '../venues.json' with {type:'json'};
const now=new Date('2026-10-24T17:00:00Z');
const base={venues:[{id:'a',name:'Cinema',coordinates:[14.4,50.1]}],snapshots:[{venue_id:'a',dates:['2026-10-24'],checked_at:'2026-10-24T16:59:00Z',screenings:[{id:'1',title:'Movie',starts_at:'2026-10-24T18:30:00+02:00',access:'english_audio'},{id:'2',title:'Movie',starts_at:'2026-10-24T20:00:00+02:00',access:'unknown'},{id:'3',title:'Movie',starts_at:'2026-10-24T20:00:00+02:00',access:'english_audio',hall:'2'}]}]};
test('upcoming only excludes past, unknown; preserves simultaneous halls',()=>{const r=select(base,{},now);assert.deepEqual(r.screenings.map(x=>x.id),['3']);assert.equal(r.coverage[0].counts.total,3);assert.equal(geojson(r).features[0].properties.count,1);});
test('no provider/network calls on selection',()=>{const old=globalThis.fetch;globalThis.fetch=()=>{throw Error('network forbidden');};try{assert.equal(select(base,{remaining:false},now).total,2);}finally{globalThis.fetch=old;}});
test('radius exposes exclusions, coordinates remain browser-local',()=>{const r=select(base,{origin:[15,51],radius_km:1},now);assert.equal(r.total,0);assert.deepEqual(r.summary.excluded_by_radius,['a']);});
test('missing coordinates remain in list and map denominator',()=>{const r=select({...base,venues:[{id:'a',name:'Cinema',coordinates:null}]},{},now);assert.equal(r.total,1);assert.deepEqual(geojson(r).unmapped_venue_ids,['a']);});
test('midnight and DST use Prague instants',()=>{assert.equal(pragueDate(new Date('2026-10-24T22:30Z')),'2026-10-25');const r=select({...base,snapshots:base.snapshots.map(s=>({...s,checked_at:'2026-10-25T02:00Z'}))},{},now);assert.equal(r.coverage[0].state,'stale');});
test('future dates absent are unpublished, demos never fresh',()=>{assert.equal(select(base,{date:'2026-10-25'},now).coverage[0].state,'unpublished');assert.equal(select({...base,snapshots:base.snapshots.map(s=>({...s,kind:'manual_sample'}))},{},now).coverage[0].state,'sample');});
test('invalid inputs fail clearly',()=>{for(const f of [{date:'2026-02-30'},{after:'25:00'},{radius_km:2},{buffer_minutes:-1}])assert.throws(()=>select(base,f,now));});
test('private origin never appears in returned search or coverage filters',()=>{const origin=[14.456789123,50.123456789];const r=select(base,{origin},now);assert.equal(r.filters.origin,undefined);assert.equal(r.filters.origin_supplied,true);assert.ok(!JSON.stringify(r).includes('14.456789123'));assert.ok(!JSON.stringify(r).includes('50.123456789'));});
test('cinema links preserve official deep links and replace third-party or invalid URLs',()=>{
  const official='https://www.cinema.example/programme';
  for(const [url,expected] of [
    ['https://www.cinema.example/film?screening=123','https://www.cinema.example/film?screening=123'],
    ['https://cinema.example/film/123','https://cinema.example/film/123'],
    ['https://goout.net/en/tickets/movie/123/',official],
    ['https://www.ticketportal.cz/event/123',official],
    ['https://tickets.cinema.example/123',official],
    ['https://www.cinema.example.evil.test/123',official],
    ['https://user:password@www.cinema.example/123',official],
    ['javascript:alert(1)',official],['invalid',official],[undefined,official],
  ]) {
    const snapshot=structuredClone(base);snapshot.venues[0].url=official;
    const row=snapshot.snapshots[0].screenings[2];row.booking_url=url;row.source_url=url;
    const result=select(snapshot,{},now);
    assert.equal(result.screenings[0].booking_url,expected);
    assert.equal(result.screenings[0].source_url,expected);
    assert.equal(geojson(result).features[0].properties.screenings[0].booking_url,expected);
    assert.equal(row.booking_url,url,'cached source data is not mutated');
  }
});
test('missing official cinema URL never falls back to a third party',()=>{
  const snapshot=structuredClone(base);snapshot.snapshots[0].screenings[2].booking_url='https://goout.net/en/tickets/movie/123/';
  const row=select(snapshot,{},now).screenings[0];
  assert.equal(row.booking_url,null);assert.equal(row.source_url,null);
});
test('Dlabačov ticket fallback opens its website rather than the collection JSON endpoint',()=>{
  const snapshot=structuredClone(base),venue=venues.find(v=>v.id==='dlabacov');
  snapshot.venues=[venue];snapshot.snapshots[0].venue_id=venue.id;
  snapshot.snapshots[0].screenings[2].booking_url='https://goout.net/en/tickets/movie/123/';
  assert.equal(select(snapshot,{},now).screenings[0].booking_url,'https://dlabacov.cz/');
});
