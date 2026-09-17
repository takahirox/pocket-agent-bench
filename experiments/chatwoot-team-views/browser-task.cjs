// Versioned product workflow. Candidate input is locator JSON, never driver code.
const {chromium,request}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {readMap,locator}=require('./ui-map.cjs');

(async()=>{
  const fixture=JSON.parse(fs.readFileSync('/verify-input/fixture.json'));
  const ui=readMap('/verify-input/ui-map.json',2);
  const base=process.env.BROWSER_BASE_URL;
  assert.equal(new URL(base).hostname,'proxy');
  const browser=await chromium.launch({headless:true,args:['--disable-background-networking']});
  const checks=[],contexts=[],tokens={};
  let stage='setup',runtimeErrors=0;
  const vars={team_id:String(fixture.teams.support),team_name:'support',view_name:''};
  const at=(page,key)=>locator(page,ui.locators[key],vars);
  const client=await request.newContext({baseURL:base});
  const filters=`/api/v1/accounts/${fixture.accounts.A}/custom_filters`;
  async function api(actor,url,method='GET',data) {
    if(!tokens[actor]) {
      const response=await client.post('/auth/sign_in',{data:{email:fixture.users[actor].email,password:'PocketBench123!'}});
      assert.equal(response.status(),200,'Fixture login failed');
      const headers=response.headers();tokens[actor]=Object.fromEntries(['access-token','client','uid'].map(k=>[k,headers[k]]));
    }
    const response=await client.fetch(url,{method,data,headers:tokens[actor],maxRedirects:0});
    const headers=response.headers();
    if(headers['access-token']) tokens[actor]=Object.fromEntries(['access-token','client','uid'].map(k=>[k,headers[k]]));
    const text=await response.text();
    return {status:response.status(),body:text?JSON.parse(text):null};
  }
  async function login(actor) {
    const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});
    contexts.push(context);
    await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
    await context.routeWebSocket('**/*',ws=>{
      const url=new URL(ws.url());
      if(url.hostname==='proxy'&&url.port==='3000') ws.connectToServer(); else ws.close();
    });
    const page=await context.newPage();page.setDefaultTimeout(15000);
    page.on('pageerror',()=>runtimeErrors++);
    await page.goto(base+'/app/login',{waitUntil:'networkidle',timeout:60000});
    await page.locator('input[name=email_address]').fill(fixture.users[actor].email);
    await page.locator('input[name=password]').fill('PocketBench123!');
    await page.getByRole('button',{name:'Login',exact:true}).click();
    await page.waitForURL('**/accounts/**');await page.waitForLoadState('networkidle');
    return page;
  }
  async function steps(page,list) {
    for(const step of list) {
      if(typeof step==='string') await at(page,step).click();
      else if(step.action==='click') await at(page,step.control).click();
      else if(step.action==='select') await at(page,step.control).selectOption(step.value);
      else if(step.action==='fill') await at(page,step.control).fill(step.value);
    }
  }
  async function keyboard(page,key) {
    const control=at(page,key);
    await control.focus();assert.ok(await control.evaluate(el=>el===document.activeElement),'Control not focusable');
    await control.press('Enter');
  }
  async function identity(page,personal=false) {
    const control=at(page,personal?'personal_heading':'view_heading');
    await control.waitFor({state:'visible'});
    let text='';const deadline=Date.now()+10000;
    do {
      text=await control.innerText();
      if(text.includes(vars.view_name)&&(personal||text.toLowerCase().includes(vars.team_name))) return;
      await page.waitForTimeout(100);
    } while(Date.now()<deadline);
    assert.fail('Visible view/team identity missing');
  }
  async function audience(page,personal=false) {
    const control=at(page,'audience');
    assert.ok((await control.ariaSnapshot()).includes('"'),'Audience control needs an accessible name');
    if(ui.audience_kind==='select') {
      await control.selectOption(personal?'0':vars.team_id);
      await control.focus();await control.press('Tab');
      assert.equal(await control.inputValue(),personal?'0':vars.team_id);
    } else {
      await keyboard(page,'audience');await at(page,personal?'personal_option':'audience_option').click();
    }
  }
  async function filtered(page,action,actor,status) {
    await page.waitForLoadState('networkidle');
    let body;
    const pending=page.waitForResponse(async r=>{
      if(!r.url().includes('/conversations/filter')||r.request().method()!=='POST') return false;
      try { body=await r.json();return true; } catch { return false; }
    });
    await action();const response=await pending;
    assert.equal(response.status(),200);
    const inboxes=actor==='alice'?['general','restricted']:actor==='bob'?['general']:[];
    const expected=fixture.conversations.filter(r=>inboxes.includes(r.inbox)&&r.status===status).map(r=>r.display_id).sort((a,b)=>a-b);
    assert.deepEqual(body.payload.map(r=>r.id).sort((a,b)=>a-b),expected);
    assert.equal(body.meta.all_count,expected.length);
    return body;
  }
  async function notManageable(page,key) {
    const control=at(page,key),count=await control.count();assert.ok(count<=1,'Ambiguous management locator');
    if(count) assert.ok(!(await control.isVisible())||!(await control.isEnabled()),'Reader has enabled management control');
  }
  function passed(name=stage){checks.push({name,status:'pass'});}
  let viewId;
  try {
    stage='shared create: validation, failure retention and keyboard retry';
    const alice=await login('alice');vars.view_name='Browser shared '+Date.now();
    await steps(alice,ui.prepare_create);await audience(alice);
    const name=at(alice,'name'),save=at(alice,'save');
    await name.fill('');
    if(await save.isEnabled()) {
      const invalid=alice.waitForResponse(r=>r.url().endsWith('/custom_filters')&&r.request().method()==='POST');
      await save.click();assert.equal((await invalid).status(),422);
      assert.ok(ui.locators.validation_error,'Enabled blank save needs a validation-error locator');
      await at(alice,'validation_error').waitFor({state:'visible'});
    }
    await name.fill(vars.view_name);
    let rejectedBody;
    const rejected=route=>{
      if(route.request().method()!=='POST') return route.continue();
      rejectedBody=route.request().postDataJSON();
      return route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({message:'Fixture rejected save'})});
    };
    await alice.route('**'+filters,rejected);
    const bad=alice.waitForResponse(r=>r.url().endsWith('/custom_filters')&&r.request().method()==='POST');
    await save.click();assert.equal((await bad).status(),422);await at(alice,'save_error').waitFor({state:'visible'});
    assert.equal(await name.inputValue(),vars.view_name);
    await alice.unroute('**'+filters,rejected);
    const created=alice.waitForResponse(r=>r.url().endsWith('/custom_filters')&&r.request().method()==='POST');
    await keyboard(alice,'save');const response=await created;
    assert.ok([200,201].includes(response.status()));assert.deepEqual(response.request().postDataJSON(),rejectedBody,'Failed save lost name/query/audience');
    const view=await response.json();viewId=view.id;assert.equal(view.team_id,fixture.teams.support);
    await identity(alice);passed();

    stage='reload and new login preserve shared view';
    await filtered(alice,()=>alice.reload({waitUntil:'networkidle'}),'alice','open');await identity(alice);
    const relogged=await login('alice');await at(relogged,'view_link').click();await identity(relogged);passed();

    stage='creator edits name/query with failed-update recovery';
    await at(alice,'edit').click();await at(alice,'edit_name').fill(vars.view_name+' resolved');
    await steps(alice,ui.set_resolved);
    let rejectedEdit;
    const rejectEdit=route=>{
      if(!['PATCH','PUT'].includes(route.request().method())) return route.continue();
      rejectedEdit=route.request().postDataJSON();
      return route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({message:'Fixture rejected update'})});
    };
    const endpoint='**'+filters+'/'+viewId+'*';
    await alice.route(endpoint,rejectEdit);
    const updateFailure=alice.waitForResponse(r=>new URL(r.url()).pathname===filters+'/'+viewId&&['PATCH','PUT'].includes(r.request().method()));
    await at(alice,'edit_save').click();assert.equal((await updateFailure).status(),422);
    await at(alice,'edit_error').waitFor({state:'visible'});
    assert.equal(await at(alice,'edit_name').inputValue(),vars.view_name+' resolved');
    await alice.unroute(endpoint,rejectEdit);
    const updated=alice.waitForResponse(r=>new URL(r.url()).pathname===filters+'/'+viewId&&['PATCH','PUT'].includes(r.request().method()));
    await keyboard(alice,'edit_save');const edited=await updated;assert.equal(edited.status(),200);
    assert.deepEqual(edited.request().postDataJSON(),rejectedEdit,'Failed edit lost name/query');
    vars.view_name+=' resolved';await identity(alice);
    await filtered(alice,()=>alice.reload({waitUntil:'networkidle'}),'alice','resolved');passed();

    stage='member reads viewer-specific results without management controls';
    const bob=await login('bob');await filtered(bob,()=>at(bob,'view_link').click(),'bob','resolved');
    await bob.getByText('general customer 3',{exact:true}).waitFor();
    assert.equal(await bob.getByText('restricted customer 2',{exact:true}).count(),0);
    await notManageable(bob,'edit');await notManageable(bob,'delete');passed();

    stage='permitted empty result';
    const dana=await login('dana');await filtered(dana,()=>at(dana,'view_link').click(),'dana','resolved');
    await identity(dana);passed();

    stage='membership changes take effect after browser reload';
    const members=`/api/v1/accounts/${fixture.accounts.A}/teams/${fixture.teams.support}/team_members`;
    assert.equal((await api('admin',members,'DELETE',{user_ids:[fixture.users.bob.id]})).status,200);
    try {
      await bob.reload({waitUntil:'networkidle'});assert.equal(await at(bob,'view_link').count(),0);
    } finally {
      assert.equal((await api('admin',members,'POST',{user_ids:[fixture.users.bob.id]})).status,200);
    }
    await bob.reload({waitUntil:'networkidle'});await at(bob,'view_link').waitFor({state:'visible'});passed();

    stage='nonmember cannot discover shared view';
    const erin=await login('erin');assert.equal(await at(erin,'view_link').count(),0);passed();

    stage='nonmember administrator edits shared view';
    const admin=await login('admin');await at(admin,'view_link').click();await at(admin,'edit').click();
    const renamed=vars.view_name+' admin';await at(admin,'edit_name').fill(renamed);await keyboard(admin,'edit_save');
    vars.view_name=renamed;await identity(admin);assert.equal((await api('bob',filters+'/'+viewId)).body.name,renamed);passed();

    stage='delete cancellation and server rejection preserve view';
    await at(admin,'delete').click();await at(admin,'delete_confirm').waitFor({state:'visible'});
    assert.equal((await api('bob',filters+'/'+viewId)).status,200);await at(admin,'delete_cancel').click();await identity(admin);
    const rejectDelete=route=>route.request().method()==='DELETE'?route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({message:'Fixture rejected delete'})}):route.continue();
    await admin.route(endpoint,rejectDelete);await at(admin,'delete').click();
    const deleteFailure=admin.waitForResponse(r=>new URL(r.url()).pathname===filters+'/'+viewId&&r.request().method()==='DELETE');
    await at(admin,'delete_confirm').click();assert.equal((await deleteFailure).status(),422);await at(admin,'delete_error').waitFor({state:'visible'});
    assert.equal((await api('bob',filters+'/'+viewId)).status,200);await admin.unroute(endpoint,rejectDelete);passed();

    stage='administrator confirms delete and member reload removes entry';
    // Both keeping the failed confirmation open and returning to the view are valid.
    if(!(await at(admin,'delete_confirm').isVisible())) await at(admin,'delete').click();
    await keyboard(admin,'delete_confirm');await at(admin,'view_link').waitFor({state:'detached'});
    await bob.reload({waitUntil:'networkidle'});assert.equal(await at(bob,'view_link').count(),0);passed();

    stage='personal create, reload, privacy, edit and creator delete';
    const personal=await login('alice');vars.view_name='Browser personal '+Date.now();
    await steps(personal,ui.prepare_create);await audience(personal,true);await at(personal,'name').fill(vars.view_name);
    const saved=personal.waitForResponse(r=>r.url().endsWith('/custom_filters')&&r.request().method()==='POST');
    await keyboard(personal,'save');const personalView=await (await saved).json();assert.equal(personalView.team_id,null);
    await identity(personal,true);await personal.reload({waitUntil:'networkidle'});await identity(personal,true);
    await bob.reload({waitUntil:'networkidle'});assert.equal(await at(bob,'personal_link').count(),0);
    await at(personal,'edit').click();await at(personal,'edit_name').fill(vars.view_name+' renamed');
    await keyboard(personal,'edit_save');vars.view_name+=' renamed';await identity(personal,true);
    await at(personal,'delete').click();await keyboard(personal,'delete_confirm');await at(personal,'personal_link').waitFor({state:'detached'});passed();
    assert.equal(runtimeErrors,0,'Browser runtime errors');
  } catch(error) {
    checks.push({name:stage,status:error.code==='ERR_ASSERTION'?'fail':'error',detail:error.message.slice(0,1400)});
    process.exitCode=1;
  } finally {
    const report={version:2,browser:browser.version(),runtime_errors:runtimeErrors,checks};
    console.log('POCKET_BROWSER='+JSON.stringify(report));
    await client.dispose();for(const context of contexts) await context.close();await browser.close();
  }
})().catch(error=>{console.error(error.name+': '+error.message.slice(0,200));process.exitCode=2;});
