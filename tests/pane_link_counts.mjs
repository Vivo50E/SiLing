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
