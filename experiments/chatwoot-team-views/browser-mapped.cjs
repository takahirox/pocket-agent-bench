// Product assertions are evaluator-owned; the public JSON map supplies locators only.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { readMap, locator } = require('./ui-map.cjs');
(async () => {
  const root = path.resolve(process.argv[2]);
  const fixture = JSON.parse(fs.readFileSync(path.join(root, 'fixture.json')));
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json')));
  const ui = readMap(process.argv[4]);
  const vars = {team_id:String(fixture.teams.support),team_name:'support'};
  const at = (page, key) => locator(page, ui.locators[key], vars);
  const base = `http://localhost:${manifest.port}`;
  const browser = await chromium.launch({executablePath: process.argv[3],headless:true,args:['--disable-background-networking','--no-first-run']});
  const results = [], contexts = [];
  let runtimeErrors = 0;
  async function login(actor) {
    const context = await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});contexts.push(context);
    await context.route('**/*',r=>{
      const url=new URL(r.request().url());
      return ['localhost','127.0.0.1'].includes(url.hostname)&&
        [String(manifest.port),String(manifest.vite_port)].includes(url.port)?r.continue():r.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', () => { runtimeErrors += 1; });
    await page.goto(base+'/app/login',{waitUntil:'networkidle',timeout:120000});
    await page.locator('input[name=email_address]').fill(fixture.users[actor].email);
    await page.locator('input[name=password]').fill('PocketBench123!');
    await page.getByRole('button',{name:'Login',exact:true}).click();
    await page.waitForURL('**/accounts/**');await page.waitForLoadState('networkidle');
    return page;
  }
  async function assertNotManageable(page,key) {
    const control=at(page,key);
    const count=await control.count();
    assert.ok(count<=1,'Ambiguous management locator');
    if(count) assert.ok(!(await control.isVisible()) || !(await control.isEnabled()),'Enabled management control');
  }
  async function assertIdentity(page) {
    const identity=at(page,'view_heading');
    await identity.waitFor({state:'visible'});
    let text='';const deadline=Date.now()+10000;
    do {
      text=await identity.innerText();
      if(text.includes(vars.view_name)&&text.toLowerCase().includes(vars.team_name.toLowerCase())) break;
      await page.waitForTimeout(100);
    } while(Date.now()<deadline);
    assert.ok(text.includes(vars.view_name),'View name is not visible');
    assert.ok(text.toLowerCase().includes(vars.team_name.toLowerCase()),'Team identity is not visible');
  }
  let stage='login';
  try {
    const page=await login('alice');
    const name='UI shared '+Date.now();vars.view_name=name;
    stage='create and recover rejected save';
    for (const key of ui.prepare_create) await at(page,key).click();
    const audience=at(page,'audience');
    if(ui.audience_kind==='select') await audience.selectOption(String(fixture.teams.support));
    else { await audience.click(); await at(page,'audience_option').click(); }
    await audience.focus();await audience.press('Tab');
    const selectedAudience=ui.audience_kind==='select'?await audience.inputValue():await audience.innerText();
    if(ui.audience_kind==='select') assert.equal(selectedAudience,String(fixture.teams.support));
    const input=at(page,'name');await input.fill(name);
    const endpoint=`**/api/v1/accounts/${fixture.accounts.A}/custom_filters`;
    const reject=r=>r.request().method()==='POST'?r.fulfill({status:422,contentType:'application/json',body:JSON.stringify({message:'Fixture rejected save'})}):r.continue();
    await page.route(endpoint,reject);
    const save=at(page,'save');
    const rejected=page.waitForResponse(r=>r.url().endsWith('/custom_filters')&&r.request().method()==='POST');
    await save.click();assert.equal((await rejected).status(),422);
    await at(page,'save_error').waitFor({state:'visible'});
    assert.equal(await input.inputValue(),name);assert.equal(ui.audience_kind==='select'?await audience.inputValue():await audience.innerText(),selectedAudience);
    await page.unroute(endpoint,reject);
    const created=page.waitForResponse(r=>r.url().endsWith('/custom_filters')&&r.request().method()==='POST');
    stage='successful save';await save.focus();await save.press('Enter');
    const response=await created;assert.ok([200,201].includes(response.status()));const view=await response.json();
    assert.equal(view.team_id,fixture.teams.support);
    await page.getByText('restricted customer 0',{exact:true}).first().waitFor();
    await page.reload({waitUntil:'networkidle'});
    await assertIdentity(page);
    results.push({name:stage,status:'pass'});
    stage='creator edit';
    await at(page,'edit').click();
    const renamed=name+' renamed';await at(page,'edit_name').fill(renamed);
    await at(page,'edit_save').click();
    vars.view_name=renamed;await assertIdentity(page);
    results.push({name:stage,status:'pass'});
    stage='member read only';
    const peer=await login('bob');await at(peer,'view_link').click();
    await peer.getByText('general customer 0',{exact:true}).first().waitFor();
    assert.equal(await peer.getByText('restricted customer 0',{exact:true}).count(),0);
    await assertNotManageable(peer,'edit');
    await assertNotManageable(peer,'delete');
    await peer.screenshot({path:path.join(root,'shared-member.png'),fullPage:true});
    results.push({name:stage,status:'pass'});
    stage='member empty result';
    const empty=await login('dana');
    const filtered=empty.waitForResponse(r=>r.url().includes('/conversations/filter')&&r.request().method()==='POST');
    await at(empty,'view_link').click();
    const emptyBody=await (await filtered).json();assert.equal(emptyBody.meta.all_count,0);assert.deepEqual(emptyBody.payload,[]);
    results.push({name:stage,status:'pass'});
    stage='administrator delete confirmation';
    const admin=await login('admin');await at(admin,'view_link').click();
    await at(admin,'delete').click();
    await at(admin,'delete_confirm').click();
    await at(admin,'view_link').waitFor({state:'detached'});
    await peer.reload({waitUntil:'networkidle'});assert.equal(await at(peer,'view_link').count(),0);
    results.push({name:stage,status:'pass'});
    assert.equal(runtimeErrors,0,'Unexpected browser runtime errors');
  } catch(error) {
    results.push({name:stage,status:'error',detail:error.message.slice(0,1200),actual:error.actual,expected:error.expected});process.exitCode=1;
  } finally {
    const report={kind:'mapped-ui-qualification',browser:browser.version(),runtime_errors:runtimeErrors,checks:results};
    fs.writeFileSync(path.join(root,'browser-mapped.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
    for(const context of contexts) await context.close();await browser.close();
  }
})().catch(e=>{console.error(e.name);process.exitCode=1});
