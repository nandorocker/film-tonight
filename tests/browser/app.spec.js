import {test,expect} from '@playwright/test';

test('historical demo: first table, local filters, map selection, mobile',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/?demo=1');await expect(page.locator('#results table')).toBeVisible();
  await expect(page.locator('#demo-banner')).toBeVisible();
  const all=await page.locator('tbody tr').count();expect(all).toBeGreaterThan(10);
  await page.locator('[name=q]').fill('odyssey');const narrowed=await page.locator('tbody tr').count();expect(narrowed).toBeLessThan(all);
  await page.locator('[name=q]').fill('');await page.locator('#show-map').click();await expect(page.locator('.leaflet-container')).toBeVisible();
  await page.locator('[data-venue-index]').first().click();await expect(page.locator('.leaflet-popup')).toBeVisible();
  expect(await page.locator('a.ticket').first().getAttribute('href')).toMatch(/^https:\/\//);
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'/tmp/opencode/film-tonight-mobile.png',fullPage:true});expect(errors).toEqual([]);
});
test('empty cache stays useful; failed tiles leave table',async({page})=>{
  await page.route('**/api/v1/snapshot*',r=>r.fulfill({json:{schema_version:2,venues:[],snapshots:[],attempts:[]}}));
  await page.goto('/');await expect(page.locator('#results')).toContainText('No matching showtimes');
  await page.unroute('**/api/v1/snapshot*');await page.route('**/*tile.openstreetmap.org/**',r=>r.abort());
  await page.goto('/?demo=1');await expect(page.locator('table')).toBeVisible();await page.locator('#show-map').click();
  await expect(page.locator('#map-status')).toContainText('Map tiles could not load');await expect(page.locator('#results table')).toBeVisible();
});
test('first fetch failure and subsequent refresh failure are honest',async({page})=>{
  await page.route('**/api/v1/snapshot*',r=>r.abort());await page.goto('/');await expect(page.locator('#status')).toContainText('could not be loaded');
  await page.unroute('**/api/v1/snapshot*');await page.goto('/?demo=1');await expect(page.locator('table')).toBeVisible();const count=await page.locator('tbody tr').count();
  await page.route('**/demo.json',r=>r.abort());await page.locator('#refresh').click();await expect(page.locator('#status')).toContainText('last successfully');expect(await page.locator('tbody tr').count()).toEqual(count);
});

function responseFor(date) {
  return {schema_version:2,service_date:date,venues:[{id:'test',name:'Test cinema',coordinates:[14.4,50.1]}],snapshots:[{venue_id:'test',generation:new Date().toISOString(),checked_at:new Date().toISOString(),dates:[date],screenings:[{id:date,title:'Film for '+date,starts_at:date+'T23:59:00+02:00',access:'english_audio',booking_url:'https://cinema.example/'}]}],attempts:[]};
}
test('delayed A→B→A response never replaces cached A',async({page})=>{
  await page.clock.install({time:new Date('2026-10-24T17:00:00Z')});
  let delayed,release;const gate=new Promise(resolve=>release=resolve);
  await page.route('**/api/v1/snapshot*',async route=>{const d=new URL(route.request().url()).searchParams.get('date');if(d==='2026-10-25'){delayed=true;await gate;}await route.fulfill({json:responseFor(d)});});
  await page.goto('/');await expect(page.locator('table')).toBeVisible();const a=await page.locator('#date').inputValue();
  await page.locator('#date').fill('2026-10-25');await expect.poll(()=>delayed).toBeTruthy();await page.locator('#date').fill(a);release();
  await page.waitForLoadState('networkidle');await expect(page.locator('tbody')).toContainText('Film for '+a);
});
test('date change during initial load discards original response',async({page})=>{
  await page.clock.install({time:new Date('2026-10-24T17:00:00Z')});
  let release;const gate=new Promise(resolve=>release=resolve);let first=true;
  await page.route('**/api/v1/snapshot*',async route=>{const d=new URL(route.request().url()).searchParams.get('date');if(first){first=false;await gate;}await route.fulfill({json:responseFor(d)});});
  await page.goto('/');await page.locator('#date').fill('2026-10-25');await expect(page.locator('tbody')).toContainText('Film for 2026-10-25');release();
  await page.waitForLoadState('networkidle');await expect(page.locator('tbody')).toContainText('Film for 2026-10-25');
});
