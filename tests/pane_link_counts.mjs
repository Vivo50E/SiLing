import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const cards = [];
const button = (hidden=false) => ({hidden, disabled:false, badge:null,dataset:{},
  querySelector(){return this.badge;}, append(badge){this.badge=badge;}, setAttribute(){}});
const context = {window:{}, document:{documentElement:{lang:'en'},
  createElement:()=>({}), querySelectorAll:()=>cards}};
vm.runInNewContext(fs.readFileSync(new URL('../static/pane-link-counts.js',import.meta.url),'utf8'),context);
const counts=context.window.SilingPaneLinkCounts, pending=[];
const api=path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject}));
const row=id=>({run_id:id,linked_folders:[]});
for(let i=0;i<3;i++)cards.push({dataset:{runId:`pane-${i}`},reviews:button(),jira:button(true),
  querySelector(selector){return this[selector.slice(5)];}});
for(const card of cards)counts.update(card,row(card.dataset.runId),api);
assert.equal(pending.length,2,'At most two requests concurrently');
assert.ok(pending.every(p=>p.path.endsWith('/reviews?branch=false')),'No provider lookup or disabled Jira discovery');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
counts.loaded('pane-0','reviews',[{url:'a',state:'open'},{url:'b',state:'merged'},{url:'b',state:'merged'}]);
pending[0].resolve({items:[]});await tick();
assert.equal(cards[0].reviews.badge.textContent,2,'Late initial discovery cannot overwrite a dialog count; URLs deduplicate');
assert.equal(cards[0].reviews.dataset.reviewState,'open','Late initial discovery cannot overwrite a refreshed status');
assert.equal(pending.length,3);
pending[1].reject(new Error('offline'));pending[2].resolve({items:[]});await tick();
assert.equal(cards[1].reviews.badge.textContent,'?','Failure is not zero');
assert.equal(cards[2].reviews.badge.textContent,0);
for(let i=0;i<10;i++)for(const card of cards)counts.update(card,row(card.dataset.runId),api);
assert.equal(pending.length,3,'Repeated pane decorations never poll');
counts.loaded('pane-1','reviews',[{url:'a'}]);
assert.equal(cards[1].reviews.badge.textContent,1,'Dialog retry repairs count');
cards[0].jira.hidden=false;counts.update(cards[0],row('pane-0'),api);
assert.equal(pending.length,4,'Enabling Jira starts initial count');
pending[3].resolve({items:[{url:'j'},{url:'j'}]});await tick();
assert.equal(cards[0].jira.badge.textContent,1);
counts.update(cards[0],{run_id:'pane-0',linked_folders:[{type:'url',path:'new'}]},api);
assert.equal(pending.length,6,'Changed saved links invalidate both counts');
pending[4].resolve({items:[]});pending[5].resolve({items:[]});await tick();
console.log('PASS: bounded count discovery, deduplication, race protection, no polling, error/retry, group toggle and link invalidation');

const colorCases = [
  [['open','merged'],'open'], [['opened','closed'],'open'], [['draft','unknown'],'open'],
  [['MERGED','merged'],'merged'], [['merged','closed'],''], [['merged','unknown'],''],
  [['closed'],''], [[undefined],''], [[], '']
];
for (const [states, expected] of colorCases) {
  counts.loaded('pane-0','reviews',states.map((state,i)=>({url:String(i),state})));
  assert.equal(cards[0].reviews.dataset.reviewState || '',expected,JSON.stringify(states));
  counts.update(cards[0],{run_id:'pane-0',linked_folders:[{type:'url',path:'new'}]},api);
  assert.equal(cards[0].reviews.dataset.reviewState || '',expected,'Decoration preserves status');
}
counts.loaded('pane-0','jira',[{url:'j',state:'open'}]);
assert.equal(cards[0].jira.dataset.reviewState,undefined,'Jira does not inherit review colors');
console.log('PASS: review status colors include drafts, require all merged, preserve neutral unknown/closed/empty and survive pane decoration');
const beforeInvalidation=pending.length;
counts.invalidate('jira');
counts.update(cards[0],{run_id:'pane-0',linked_folders:[{type:'url',path:'new'}]},api);
assert.equal(pending.length,beforeInvalidation+1,'Connecting Jira MCP invalidates only Jira counts');
assert.ok(pending.at(-1).path.endsWith('/jira?lookup=true'));
pending.at(-1).resolve({items:[{url:'j2'}]});await tick();
const beforeRename=pending.length;
const renamed={run_id:'pane-0',display_name:'SRAM Vmin Vmax',linked_folders:[{type:'url',path:'new'}]};
counts.update(cards[0],renamed,api);
assert.equal(pending.length,beforeRename+1,'Renaming the current task invalidates only its Jira count');
assert.ok(pending.at(-1).path.endsWith('/jira?lookup=true'));
pending.at(-1).resolve({items:[]});await tick();
counts.update(cards[0],renamed,api);
assert.equal(pending.length,beforeRename+1,'Unchanged task names do not poll');

let fakeNow = 1000000, topicEnabled = true;
context.Date = {now:()=>fakeNow};
context.window.SilingJiraTopics = {enabled:()=>topicEnabled};
counts.update(cards[0],{...renamed,alive:true},api);
assert.ok(pending.at(-1).path.endsWith('/jira?lookup=true&topic=true'),'Opt-in starts a topic search without opening the list');
pending.at(-1).resolve({items:[{url:'topic-1'}]});await tick();
const afterTopic=pending.length;
fakeNow+=599999;counts.update(cards[0],{...renamed,alive:true},api);
assert.equal(pending.length,afterTopic,'Topic search waits ten minutes');
fakeNow+=1;counts.update(cards[0],{...renamed,alive:false},api);
assert.equal(pending.length,afterTopic,'Ended sessions are not polled');
context.document.visibilityState='hidden';counts.update(cards[0],{...renamed,alive:true},api);
assert.equal(pending.length,afterTopic,'Hidden pages do not search');
context.document.visibilityState='visible';counts.update(cards[0],{...renamed,alive:true},api);
assert.equal(pending.length,afterTopic+1,'Visible active pane refreshes automatically after ten minutes');
counts.update(cards[0],{...renamed,alive:true},api);
assert.equal(pending.length,afterTopic+1,'Pending search never duplicates');
assert.equal(cards[0].jira.badge.textContent,1,'Automatic refresh retains the last count');
pending.at(-1).resolve({items:[{url:'topic-2'},{url:'topic-3'}]});await tick();
assert.equal(cards[0].jira.badge.textContent,2);
topicEnabled=false;counts.update(cards[0],{...renamed,alive:true},api);
assert.ok(pending.at(-1).path.endsWith('/jira?lookup=true'),'Turning off topics restores ordinary lookup');
pending.at(-1).resolve({items:[]});await tick();
const afterDisable=pending.length;fakeNow+=600000;
counts.update(cards[0],{...renamed,alive:true},api);
assert.equal(pending.length,afterDisable,'Disabled topics do not poll');
console.log('PASS: opt-in proactive topic discovery, ten-minute refresh, no ended/hidden polling, deduplication and disable');
topicEnabled=true;counts.update(cards[0],{...renamed,alive:true},api);
pending.at(-1).resolve({items:[],topic_error:'topic_busy'});await tick();
const afterBusy=pending.length;fakeNow+=29999;
counts.update(cards[0],{...renamed,alive:true},api);assert.equal(pending.length,afterBusy);
fakeNow+=1;counts.update(cards[0],{...renamed,alive:true},api);
assert.equal(pending.length,afterBusy+1,'Busy panes retry in thirty seconds instead of waiting ten minutes');
pending.at(-1).resolve({items:[]});await tick();
