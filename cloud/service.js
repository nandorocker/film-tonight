import venues from '../venues.json' with {type:'json'};
import {select,geojson,pragueDate} from '../web/query.js';

const ALLOWED_ACCESS=new Set(['english_audio','english_subtitles','english_friendly','not_english','unknown','conflict']);
const ISO=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}});
function assert(ok,message){if(!ok)throw new Error(message);}
function instant(value){return typeof value==='string'&&ISO.test(value)&&Number.isFinite(Date.parse(value));}
function https(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password;}catch{return false;}}
export function validate(input,now=Date.now()) {
  const venue=venues.find(v=>v.id===input.venue_id);
  assert(venue,'Unknown venue');assert(instant(input.generation),'Invalid generation');
  assert(Math.abs(now-Date.parse(input.generation))<86400000,'Generation outside one-day publication window');
  assert(instant(input.checked_at)&&Date.parse(input.checked_at)>=Date.parse(input.generation)&&Date.parse(input.checked_at)<=now+60000,'Invalid check timestamp');
  assert(['ok','error','blocked'].includes(input.outcome),'Invalid outcome');
  const result={venue_id:venue.id,generation:new Date(input.generation).toISOString(),checked_at:new Date(input.checked_at).toISOString(),outcome:input.outcome,detail:String(input.detail||'').slice(0,300)};
  if(input.outcome!=='ok')return result;
  assert(Array.isArray(input.dates)&&input.dates.length>0&&input.dates.length<=60,'Invalid published horizon');
  assert(input.dates.every(d=>/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d))&&new Date(d).toISOString().slice(0,10)===d),'Invalid published dates');
  assert(Array.isArray(input.screenings)&&input.screenings.length<=2000,'Too many screenings');
  const ids=new Set();
  result.dates=[...new Set(input.dates)].sort();result.state='ok';
  result.screenings=input.screenings.map(row=>{
    assert(typeof row.id==='string'&&row.id.length>0&&row.id.length<=180&&!ids.has(row.id),'Invalid/duplicate screening ID');ids.add(row.id);
    assert(typeof row.title==='string'&&row.title.length>0&&row.title.length<=500,'Invalid title');
    assert(instant(row.starts_at),'Screening needs aware start');
    assert(ALLOWED_ACCESS.has(row.access),'Unknown access classification');
    assert(input.dates.includes(pragueDate(new Date(row.starts_at))), 'Screening outside published dates');
    assert(https(row.booking_url),'Booking URL must be HTTPS');
    const host=new URL(row.booking_url).hostname, sourceHost=new URL(venue.url).hostname;
    assert(host===sourceHost||['goout.net','tickets.cinemacity.cz','tickets.colosseum.eu','kino35.koupitvstupenku.cz','shop.mat.cz','shop.entradio.cz','www.koupitvstupenku.cz','www.ticketportal.cz','ticketportal.cz'].includes(host),'Unrecognized booking origin');
    const allowed=['id','provider_id','film_id','title','starts_at','ends_at','audio','subtitles','dubbed','access','hall','format','price','currency','booking_url','availability_reported','language_evidence','event_type'];
    const clean=Object.fromEntries(allowed.filter(k=>row[k]!==undefined).map(k=>[k,row[k]]));
    clean.source_url=venue.url;clean.event_type=clean.event_type||'unknown';
    clean.service_date=pragueDate(new Date(row.starts_at));
    assert(['film','unknown','non_film'].includes(clean.event_type),'Invalid event type');
    assert(clean.ends_at==null||instant(clean.ends_at),'Invalid end time');
    assert(JSON.stringify(clean.language_evidence??{}).length<=6000,'Oversized evidence');
    return clean;
  });
  assert(input.screenings.length>0||input.explicit_empty===true,'Empty requires explicit publication evidence');
  result.parser_version=String(input.parser_version||'unknown').slice(0,80);
  result.raw_sha=typeof input.raw_sha==='string'?input.raw_sha.slice(0,64):null;
  return result;
}
export async function snapshot(db,day=null) {
  // Filter normalized rows inside D1 so Free Worker reads do not parse the entire
  // seven-day programme. Horizons remain complete for honest date coverage.
  const statement=day?db.prepare(`SELECT json_set(payload,'$.screenings',json((SELECT json_group_array(value) FROM json_each(payload,'$.screenings') WHERE coalesce(json_extract(value,'$.service_date'),substr(json_extract(value,'$.starts_at'),1,10))=?))) AS payload FROM current_programmes`).bind(day):db.prepare('SELECT payload FROM current_programmes');
  const [current,attempts]=await Promise.all([statement.all(),db.prepare('SELECT venue_id,checked_at,outcome,detail FROM latest_attempts').all()]);
  return {schema_version:2,service_date:day,generated_at:new Date().toISOString(),timezone:'Europe/Prague',ttl_seconds:900,venues,
    snapshots:current.results.map(r=>JSON.parse(r.payload)),attempts:attempts.results};
}
export async function ingest(db,value) {
  const payload=JSON.stringify(value), day=value.checked_at.slice(0,10);
  const statements=[db.prepare(`INSERT INTO latest_attempts VALUES (?,?,?,?,?) ON CONFLICT(venue_id) DO UPDATE SET generation=excluded.generation,checked_at=excluded.checked_at,outcome=excluded.outcome,detail=excluded.detail WHERE excluded.generation>latest_attempts.generation`).bind(value.venue_id,value.generation,value.checked_at,value.outcome,value.detail)];
  if(value.outcome==='ok') {
    statements.push(db.prepare(`INSERT INTO current_programmes VALUES (?,?,?,?) ON CONFLICT(venue_id) DO UPDATE SET generation=excluded.generation,checked_at=excluded.checked_at,payload=excluded.payload WHERE excluded.generation>current_programmes.generation`).bind(value.venue_id,value.generation,value.checked_at,payload));
    statements.push(db.prepare(`INSERT INTO daily_history VALUES (?,?,?,?) ON CONFLICT(venue_id,day) DO UPDATE SET generation=excluded.generation,payload=excluded.payload WHERE excluded.generation>daily_history.generation`).bind(value.venue_id,day,value.generation,payload));
  }
  await db.batch(statements);return {ok:true,venue_id:value.venue_id,generation:value.generation};
}
async function authorized(request,secret) {
  if(!secret)return false;
  // Compare fixed-length digests rather than variable-length token characters.
  const a=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(request.headers.get('Authorization')||''));
  const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode('Bearer '+secret));
  const x=new Uint8Array(a),y=new Uint8Array(b);let n=0;for(let i=0;i<x.length;i++)n|=x[i]^y[i];return n===0;
}
async function body(request) {
  if(!request.headers.get('Content-Type')?.startsWith('application/json'))throw new Error('Use application/json');
  if(Number(request.headers.get('Content-Length'))>1_500_000)throw new Error('Body too large');
  const reader=request.body?.getReader();if(!reader)throw new Error('Missing body');
  const chunks=[];let size=0;
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>1_500_000){await reader.cancel();throw new Error('Body too large');}chunks.push(value);}
  const bytes=new Uint8Array(size);let p=0;for(const c of chunks){bytes.set(c,p);p+=c.length;}return JSON.parse(new TextDecoder().decode(bytes));
}
export async function handle(request,env) {
  const url=new URL(request.url),path=url.pathname.replace(/^\/api\/v1/,'');
  if(!['GET','POST'].includes(request.method))return json({error:{code:'method_not_allowed',message:'Use GET or authorized POST'}},405);
  if(path==='/health'&&request.method==='GET')return json({ok:true,schema_version:2});
  if(!env.DB)return json({error:{code:'not_ready',message:'Database binding missing'}},503);
  try {
    if(path==='/internal/ingest'&&request.method==='POST') {
      if(!await authorized(request,env.INGEST_TOKEN))return json({error:{code:'unauthorized'}},401);
      return json(await ingest(env.DB,validate(await body(request))));
    }
    if(path==='/internal/jobs'&&request.method==='POST') {
      if(!await authorized(request,env.INGEST_TOKEN))return json({error:{code:'unauthorized'}},401);
      const input=await body(request),failed=input.failed??false;
      if(!instant(input.generation)||typeof failed!=='boolean')throw new Error('Invalid job completion');
      const generation=new Date(input.generation).toISOString();
      const retentionCutoff=new Date(Date.now()-7*86400000).toISOString();
      await env.DB.batch([
        env.DB.prepare("UPDATE refresh_requests SET state=? WHERE state='queued' AND requested_at<=?").bind(failed?'complete_with_errors':'complete',generation),
        env.DB.prepare("DELETE FROM daily_history WHERE day<date('now','-30 days')"),
        env.DB.prepare('DELETE FROM refresh_requests WHERE requested_at<?').bind(retentionCutoff)]);
      return json({ok:true});
    }
    if(path==='/refresh'&&request.method==='POST') {
      if(!await authorized(request,env.REFRESH_TOKEN))return json({error:{code:'unauthorized'}},401);
      const cutoff=new Date(Date.now()-30*60000).toISOString();
      await env.DB.prepare("INSERT INTO refresh_requests(id,requested_at,state) SELECT ?,?,'queued' WHERE NOT EXISTS(SELECT 1 FROM refresh_requests WHERE state='queued' AND requested_at>?)").bind(crypto.randomUUID(),new Date().toISOString(),cutoff).run();
      const job=await env.DB.prepare("SELECT * FROM refresh_requests WHERE state='queued' ORDER BY requested_at DESC LIMIT 1").first();
      return json({...job,note:'Queued for next GitHub Actions collection; scheduling is best effort.'},202);
    }
    if(path.startsWith('/jobs/')&&request.method==='GET') {
      if(!await authorized(request,env.REFRESH_TOKEN))return json({error:{code:'unauthorized'}},401);
      const job=await env.DB.prepare('SELECT * FROM refresh_requests WHERE id=?').bind(path.slice(6)).first();
      if(job?.state==='queued'&&Date.parse(job.requested_at)<Date.now()-3600000)job.state='expired';
      return json(job||{error:{code:'not_found'}},job?200:404);
    }
    if(request.method!=='GET')return json({error:{code:'not_found'}},404);
    if(path==='/ready') {await env.DB.prepare('SELECT 1 FROM current_programmes LIMIT 1').all();return json({ready:true,database:true});}
    if(!['/snapshot','/screenings','/coverage','/map.geojson'].includes(path))return json({error:{code:'not_found'}},404);
    const day=url.searchParams.get('date')||pragueDate();
    const data=await snapshot(env.DB,day);
    if(path==='/snapshot')return json(data);
    assert(!url.searchParams.has('origin')&&!url.searchParams.has('radius_km'),'Compute private origin and distance client-side');
    const f=Object.fromEntries(url.searchParams);
    if(f.remaining!==undefined){assert(['true','false'].includes(f.remaining),'remaining must be true/false');f.remaining=f.remaining==='true';}
    const result=select(data,f);
    if(path==='/coverage')return json({...result,screenings:undefined});
    return json(path==='/map.geojson'?geojson(result):result);
  } catch(error) {
    // No request URLs, headers, source bodies or credential-bearing errors in logs.
    if(error.message.startsWith('D1_'))return json({error:{code:'service_error',message:'Database unavailable'}},503);
    if(error instanceof SyntaxError)return json({error:{code:'invalid_request',message:'Invalid JSON payload'}},400);
    return json({error:{code:'invalid_request',message:error.message}},400);
  }
}
