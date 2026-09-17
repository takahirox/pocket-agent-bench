// Declarative locators only: never load candidate JavaScript as a browser driver.
const fs = require('node:fs');
const required = ['audience','name','save','save_error','view_heading','view_link',
  'edit','edit_name','edit_save','delete','delete_confirm'];
function readMap(file, version=1) {
  const bytes=fs.readFileSync(file);
  if(bytes.length>16384) throw new Error('UI map exceeds 16 KiB');
  const map=JSON.parse(bytes);
  if(map.version!==version || !['select','menu'].includes(map.audience_kind) ||
     !Array.isArray(map.prepare_create) || map.prepare_create.length>8 ||
     !map.locators || typeof map.locators!=='object') throw new Error('Invalid UI map');
  function controls(steps) {
    return steps.map(step=>{
      if(typeof step==='string') return step;
      if(version!==2 || !step || typeof step!=='object' ||
         Object.keys(step).some(k=>!['control','action','value'].includes(k)) ||
         typeof step.control!=='string' || !['click','select','fill'].includes(step.action) ||
         (step.action!=='click' && (typeof step.value!=='string'||step.value.length>512)))
        throw new Error('Invalid declarative step');
      return step.control;
    });
  }
  const needed=[...required,...controls(map.prepare_create)];
  if(version===2) {
    if(!Array.isArray(map.set_resolved)||map.set_resolved.length>8) throw new Error('Invalid query-edit workflow');
    needed.push('delete_cancel','delete_error','edit_error','personal_link','personal_heading',
      ...controls(map.set_resolved));
    if(map.audience_kind==='menu') needed.push('personal_option');
  }
  if(map.audience_kind==='menu') needed.push('audience_option');
  for(const name of needed) if(!Object.hasOwn(map.locators,name)) throw new Error('Missing locator: '+name);
  for(const item of Object.values(map.locators)) {
    if(!item || typeof item!=='object' || Array.isArray(item) ||
       Object.keys(item).some(k=>!['by','value','role','scope'].includes(k)) ||
       !['css','role','label','placeholder','text'].includes(item.by) ||
       typeof item.value!=='string' || item.value.length>512 ||
       (item.by==='role' && typeof item.role!=='string') ||
       (item.scope!==undefined && typeof item.scope!=='string')) throw new Error('Invalid locator');
    for(const value of [item.value,item.scope || ''])
      for(const match of value.matchAll(/\{([^}]+)\}/g))
        if(!['view_name','team_id','team_name'].includes(match[1])) throw new Error('Unknown placeholder');
  }
  return map;
}
function locator(page, item, vars) {
  const expand=text=>text.replace(/\{([^}]+)\}/g,(_,key)=>{
    if(vars[key]===undefined) throw new Error('Missing placeholder value');
    return vars[key];
  });
  const scope=item.scope?page.locator(expand(item.scope)):page;
  const value=expand(item.value);
  switch(item.by) {
    case 'css': return scope.locator(value);
    case 'role': return scope.getByRole(item.role,{name:value,exact:true});
    case 'label': return scope.getByLabel(value,{exact:true});
    case 'placeholder': return scope.getByPlaceholder(value,{exact:true});
    case 'text': return scope.getByText(value,{exact:true});
    default: throw new Error('Unsupported locator');
  }
}
module.exports={readMap,locator};
