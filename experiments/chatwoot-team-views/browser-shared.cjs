// Reference UI qualification. Exact labels are reference-specific, not a hidden
// contract imposed on arbitrary candidate UIs.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const root = path.resolve(process.argv[2]);
  const fixture = JSON.parse(fs.readFileSync(path.join(root, 'fixture.json')));
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json')));
  const base = `http://localhost:${manifest.port}`;
  const browser = await chromium.launch({executablePath: process.argv[3],headless:true,args:['--disable-background-networking','--no-first-run']});
  const results = [], contexts = [];
  let runtimeErrors = 0;
  async function login(actor) {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});contexts.push(context);
    await context.route('**/*',r=>['localhost','127.0.0.1'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
    const page = await context.newPage();
    page.on('pageerror', () => { runtimeErrors += 1; });
    await page.goto(base+'/app/login',{waitUntil:'networkidle',timeout:120000});
    await page.locator('input[name=email_address]').fill(fixture.users[actor].email);
    await page.locator('input[name=password]').fill('PocketBench123!');
    await page.getByRole('button',{name:'Login',exact:true}).click();
    await page.waitForURL('**/accounts/**');await page.waitForLoadState('networkidle');
    return page;
  }
  let stage='login';
  try {
    const page=await login('alice');
    const name='UI shared '+Date.now();
    stage='create and recover rejected save';
    await page.locator('#toggleConversationFilterButton').first().click();
    await page.getByRole('button',{name:'Apply filters',exact:true}).click();
    await page.getByRole('button',{name:'Save filter',exact:true}).click();
    const audience=page.getByLabel('View audience');
    await audience.selectOption(String(fixture.teams.support));await audience.focus();await audience.press('Tab');
    assert.equal(await audience.inputValue(),String(fixture.teams.support));
    const input=page.getByPlaceholder('Name your filter to refer it later.');await input.fill(name);
    const endpoint=`**/api/v1/accounts/${fixture.accounts.A}/custom_filters`;
    const reject=r=>r.request().method()==='POST'?r.fulfill({status:422,contentType:'application/json',body:JSON.stringify({message:'Fixture rejected save'})}):r.continue();
    await page.route(endpoint,reject);
    const save=page.locator('#saveFilterTeleportTarget').getByRole('button',{name:'Save filter',exact:true});
    await save.click();await page.getByText('Fixture rejected save',{exact:true}).waitFor();
    assert.equal(await input.inputValue(),name);assert.equal(await audience.inputValue(),String(fixture.teams.support));
    await page.unroute(endpoint,reject);
    const created=page.waitForResponse(r=>r.url().endsWith('/custom_filters')&&r.request().method()==='POST');
    stage='successful save';await save.focus();await save.press('Enter');
    const response=await created;assert.equal(response.status(),200);const view=await response.json();
    assert.equal(view.team_id,fixture.teams.support);
    await page.waitForURL('**/custom_view/**');
    await page.getByText('restricted customer 0',{exact:true}).first().waitFor();
    await page.reload({waitUntil:'networkidle'});
    await page.getByRole('heading',{name:name+' · support',exact:true}).waitFor();
    results.push({name:stage,status:'pass'});
    stage='creator edit';
    await page.getByRole('button',{name:'Edit folder',exact:true}).click();
    const renamed=name+' renamed';await page.getByPlaceholder('Enter value',{exact:true}).fill(renamed);
    await page.getByRole('button',{name:'Update folder',exact:true}).click();
    await page.getByRole('heading',{name:renamed+' · support',exact:true}).waitFor();
    results.push({name:stage,status:'pass'});
    stage='member read only';
    const peer=await login('bob');await peer.getByText(renamed+' · support',{exact:true}).first().click();
    await peer.getByText('general customer 0',{exact:true}).first().waitFor();
    assert.equal(await peer.getByText('restricted customer 0',{exact:true}).count(),0);
    assert.equal(await peer.getByRole('button',{name:'Edit folder',exact:true}).count(),0);
    assert.equal(await peer.getByRole('button',{name:'Delete filter',exact:true}).count(),0);
    await peer.screenshot({path:path.join(root,'shared-member.png'),fullPage:true});
    results.push({name:stage,status:'pass'});
    stage='member empty result';
    const empty=await login('dana');
    const filtered=empty.waitForResponse(r=>r.url().includes('/conversations/filter')&&r.request().method()==='POST');
    await empty.getByText(renamed+' · support',{exact:true}).first().click();
    const emptyBody=await (await filtered).json();assert.equal(emptyBody.meta.all_count,0);assert.deepEqual(emptyBody.payload,[]);
    results.push({name:stage,status:'pass'});
    stage='administrator delete confirmation';
    const admin=await login('admin');await admin.getByText(renamed+' · support',{exact:true}).first().click();
    await admin.getByRole('button',{name:'Delete filter',exact:true}).click();
    await admin.getByRole('button',{name:'Yes, delete',exact:true}).click();
    await admin.getByText(renamed+' · support',{exact:true}).first().waitFor({state:'detached'});
    await peer.reload({waitUntil:'networkidle'});assert.equal(await peer.getByText(renamed+' · support',{exact:true}).count(),0);
    results.push({name:stage,status:'pass'});
    assert.equal(runtimeErrors,0,'Unexpected browser runtime errors');
  } catch(error) {
    results.push({name:stage,status:'error',detail:error.message.slice(0,1200),actual:error.actual,expected:error.expected});process.exitCode=1;
  } finally {
    const report={kind:'reference-ui-qualification',browser:browser.version(),runtime_errors:runtimeErrors,checks:results};
    fs.writeFileSync(path.join(root,'browser-shared.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
    for(const context of contexts) await context.close();await browser.close();
  }
})().catch(e=>{console.error(e.name);process.exitCode=1});
