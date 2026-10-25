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
test('ticket and screening-source links go directly to the cinema instead of third parties',async({page})=>{
  await page.clock.install({time:new Date('2026-10-24T17:00:00Z')});
  await page.route('**/api/v1/snapshot*',route=>{
    const data=responseFor('2026-10-24');data.venues[0].url='https://cinema.example/programme';
    const row=data.snapshots[0].screenings[0];
    row.booking_url='https://goout.net/en/tickets/movie/123/';row.source_url='https://www.ticketportal.cz/event/123';
    return route.fulfill({json:data});
  });
  await page.goto('/');
  await expect(page.locator('a.ticket')).toHaveAttribute('href','https://cinema.example/programme');
  await page.locator('td details summary').click();
  await expect(page.getByRole('link',{name:'Screening source'})).toHaveAttribute('href','https://cinema.example/programme');
  await expect(page.locator('a[href*="goout.net"], a[href*="ticketportal.cz"]')).toHaveCount(0);
});
for (const width of [320,390,700]) {
  test(`mobile stays within ${width}px with long listings and expanded filters`,async({browser})=>{
    const context=await browser.newContext({viewport:{width,height:844},isMobile:true,hasTouch:true});
    const page=await context.newPage();
    await page.clock.install({time:new Date('2026-10-24T17:00:00Z')});
    await page.route('**/api/v1/snapshot*',route=>{
      const data=responseFor('2026-10-24');
      data.venues[0].name='Cinema'+ 'LongName'.repeat(30);
      const row=data.snapshots[0].screenings[0];
      row.title='LongTitle'.repeat(40);row.hall='LongHall'.repeat(30);
      row.language_evidence='https://cinema.example/'+ 'evidence'.repeat(60);
      return route.fulfill({json:data});
    });
    await page.goto('/');await expect(page.locator('table')).toBeVisible();
    const date=page.locator('input[type=date]');const time=page.locator('input[type=time]');
    await expect(date).toHaveCSS('appearance','none');await expect(time).toHaveCSS('appearance','none');
    for (const control of [date,time]) {
      const bounds=await control.evaluate(el=>({input:el.getBoundingClientRect().toJSON(),label:el.parentElement.getBoundingClientRect().toJSON()}));
      expect(bounds.input.left).toBeGreaterThanOrEqual(bounds.label.left);
      expect(bounds.input.right).toBeLessThanOrEqual(bounds.label.right);
    }
    const dateBox=await date.boundingBox();const timeBox=await time.boundingBox();
    expect(dateBox.y).toBe(timeBox.y);expect(dateBox.x+dateBox.width).toBeLessThan(timeBox.x);
    expect(Math.abs(dateBox.width-timeBox.width)).toBeLessThan(1);
    await page.locator('.filter-bottom summary').click();
    await page.locator('td details summary').click();
    await page.locator('#coverage summary').click();
    // Check content bounds as well as the root: clipping alone must not hide overflow.
    for (const selector of ['.film-title','.meta','.venue-button','td details p','#coverage-content','input','select']) {
      const bounds=await page.locator(selector).evaluateAll(elements=>elements.map(el=>({left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right,client:el.clientWidth,scroll:el.scrollWidth})));
      for (const box of bounds) {
        expect(box.left).toBeGreaterThanOrEqual(0);expect(box.right).toBeLessThanOrEqual(width);
        expect(box.scroll).toBeLessThanOrEqual(box.client+1);
      }
    }
    await page.evaluate(()=>window.scrollTo(120,400));
    expect(await page.evaluate(()=>scrollX)).toBe(0);
    expect(await page.evaluate(()=>scrollY)).toBeGreaterThan(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await context.close();
  });
}
test('mobile page scrolls and map pans without global gesture restrictions',async({browser,browserName})=>{
  test.skip(browserName!=='chromium','Touch injection uses Chromium CDP');
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const page=await context.newPage();
  await page.goto('/?demo=1');await expect(page.locator('table')).toBeVisible();
  for (const selector of ['html','body','main','#filters','#listings']) {
    await expect(page.locator(selector)).toHaveCSS('touch-action','auto');
    await expect(page.locator(selector)).toHaveCSS('overflow-x','visible');
  }
  const cdp=await context.newCDPSession(page);
  async function swipe(x,y,dx,dy) {
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
    for (let step=1;step<=10;step++) {
      await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+dx*step/10,y:y+dy*step/10}]});
    }
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  }
  await swipe(300,700,-220,0);
  expect(await page.evaluate(()=>scrollX)).toBe(0);
  await swipe(280,700,-100,-300);
  await expect.poll(()=>page.evaluate(()=>scrollY)).toBeGreaterThan(100);
  expect(await page.evaluate(()=>scrollX)).toBe(0);
  await page.locator('#show-map').click();await expect(page.locator('.leaflet-container')).toBeVisible();
  await page.locator('#map').scrollIntoViewIfNeeded();
  // A pan-y rule on html/body/main would disable horizontal map dragging too.
  for (const selector of ['html','body','main','.map-section']) {
    await expect(page.locator(selector)).toHaveCSS('touch-action','auto');
  }
  const pane=page.locator('.leaflet-map-pane');
  await expect(pane).not.toHaveClass(/leaflet-zoom-anim/);
  const before=await pane.evaluate(el=>el.style.transform);
  const box=await page.locator('#map').boundingBox();
  await swipe(box.x+80,box.y+70,80,0);
  await expect.poll(()=>pane.evaluate(el=>el.style.transform)).not.toBe(before);
  expect(await page.evaluate(()=>scrollX)).toBe(0);
  await context.close();
});
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
