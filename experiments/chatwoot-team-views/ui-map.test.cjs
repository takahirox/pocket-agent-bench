const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {readMap,locator}=require('./ui-map.cjs');
const reference=JSON.parse(fs.readFileSync(path.join(__dirname,'reference-ui-map.json')));
function load(value,version=1){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'team-view-ui-'));
  try {const file=path.join(dir,'map.json');fs.writeFileSync(file,JSON.stringify(value));return readMap(file,version);}
  finally{fs.rmSync(dir,{recursive:true});}
}
test('accepts alternate wording and layout without altering assertions',()=>{
  const map=structuredClone(reference);
  map.locators.save={by:'role',role:'button',value:'共有する',scope:'#custom-panel'};
  assert.equal(load(map).locators.save.value,'共有する');
});
test('rejects executable adapters and unsupported placeholders',()=>{
  for(const item of [{by:'evaluate',value:'fetch("secret")'},
                    {by:'css',value:'#save',script:'return true'},
                    {by:'text',value:'{token}'}]) {
    const map=structuredClone(reference);map.locators.save=item;
    assert.throws(()=>load(map));
  }
});
test('requires all fixed workflow controls',()=>{
  const map=structuredClone(reference);delete map.locators.delete;
  assert.throws(()=>load(map),/Missing locator/);
});
test('passes exact names as data rather than executable expressions',()=>{
  let actual;
  const page={getByRole:(role,options)=>{actual={role,options};return 'locator';}};
  const name='hello "); process.exit(); //';
  assert.equal(locator(page,{by:'role',role:'heading',value:'{view_name}'},{view_name:name}),'locator');
  assert.deepEqual(actual,{role:'heading',options:{name,exact:true}});
});
test('version 2 accepts declarative select/fill steps and rejects executable steps',()=>{
  const map=JSON.parse(fs.readFileSync(path.join(__dirname,'task-ui-map.json')));
  map.set_resolved=[{control:'edit_name',action:'fill',value:'ordinary text'},
                    {control:'audience',action:'select',value:'1'}];
  assert.equal(load(map,2).set_resolved.length,2);
  for(const step of [{control:'edit_name',action:'evaluate',value:'fetch("secret")'},
                    {control:'edit_name',action:'click',script:'process.exit()'}]) {
    map.set_resolved=[step];assert.throws(()=>load(map,2),/Invalid declarative step/);
  }
});
test('version 2 requires the failure and personal workflow controls',()=>{
  const map=JSON.parse(fs.readFileSync(path.join(__dirname,'task-ui-map.json')));
  delete map.locators.personal_heading;
  assert.throws(()=>load(map,2),/Missing locator/);
});
