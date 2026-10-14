/* A paint-only layer: never wraps, reparents or resizes terminal panes. */
(() => {
  'use strict';
  window.SilingGroupOutlines = ({grid, enabled, groupFor}) => {
    const ns='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(ns,'svg');
    svg.id='pane-group-outlines';svg.setAttribute('aria-hidden','true');
    document.body.append(svg);
    let scheduled=0, previous='';
    const observed=new Set();
    const schedule=()=>{if(!scheduled)scheduled=requestAnimationFrame(draw);};
    const resize=new ResizeObserver(schedule);
    resize.observe(grid);
    // Watch only grid membership/presentation, never terminal text or iframe DOM.
    const mutations=new MutationObserver(schedule);
    mutations.observe(grid,{childList:true,attributes:true,attributeFilter:['class','style']});
    const cardChanges=new MutationObserver(schedule);
    window.addEventListener('resize',schedule);
    window.addEventListener('scroll',schedule,true);
    function draw() {
      scheduled=0;
      const cards=[...grid.children].filter(card=>card.matches('.pane-card[data-run-id]:not(.cached-pane):not(.group-hidden)'));
      let membershipChanged=false;
      for(const card of observed)if(!cards.includes(card)){resize.unobserve(card);observed.delete(card);membershipChanged=true;}
      if(membershipChanged || cards.some(card=>!observed.has(card))){
        cardChanges.disconnect();
        for(const card of cards){resize.observe(card);observed.add(card);cardChanges.observe(card,{attributes:true,attributeFilter:['class','style']});}
      }
      if(!enabled() || document.querySelector('.app.mobile') || grid.querySelector('.zoomed-pane')){
        svg.replaceChildren();previous='';return;
      }
      const bounds=grid.getBoundingClientRect(),style=getComputedStyle(grid);
      const gapX=parseFloat(style.columnGap)||0,gapY=parseFloat(style.rowGap)||0;
      const tracks=(values,start,gap)=>{
        let cursor=start;
        return values.split(' ').map(parseFloat).filter(Number.isFinite).map(size=>{const track={start:cursor,end:cursor+size,center:cursor+size/2};cursor+=size+gap;return track;});
      };
      const columns=tracks(style.gridTemplateColumns,bounds.left+grid.clientLeft+(parseFloat(style.paddingLeft)||0)-grid.scrollLeft,gapX);
      const rows=tracks(style.gridTemplateRows,bounds.top+grid.clientTop+(parseFloat(style.paddingTop)||0)-grid.scrollTop,gapY);
      if(!columns.length || !rows.length){svg.replaceChildren();previous='';return;}
      const nearest=(tracks,value)=>tracks.reduce((best,track,index)=>Math.abs(track.center-value)<Math.abs(tracks[best].center-value)?index:best,0);
      const cells=new Map(), groups=new Map();
      for(const card of cards){
        const group=groupFor(card.dataset.runId);if(!group)continue;
        const rect=card.getBoundingClientRect();if(!rect.width||!rect.height)continue;
        const x=nearest(columns,rect.left+rect.width/2),y=nearest(rows,rect.top+rect.height/2);
        const cell={x,y,left:columns[x].start-gapX/2,right:columns[x].end+gapX/2,top:rows[y].start-gapY/2,bottom:rows[y].end+gapY/2,group};
        cells.set(`${x},${y}`,cell);
        if(!groups.has(group.id))groups.set(group.id,{group,cells:[],lines:[]});
        groups.get(group.id).cells.push(cell);
      }
      for(const cell of cells.values()){
        const {x,y,left:l,right:r,top:t,bottom:b,group}=cell;
        const same=(dx,dy)=>cells.get(`${x+dx},${y+dy}`)?.group.id===group.id;
        const lines=groups.get(group.id).lines;
        if(!same(0,-1))lines.push(`M${l},${t}H${r}`);
        if(!same(1,0))lines.push(`M${r},${t}V${b}`);
        if(!same(0,1))lines.push(`M${r},${b}H${l}`);
        if(!same(-1,0))lines.push(`M${l},${b}V${t}`);
      }
      const signature=JSON.stringify([bounds.left,bounds.top,grid.clientWidth,grid.clientHeight,[...groups.values()]]);
      if(signature===previous)return;
      previous=signature;svg.replaceChildren();
      const node=(tag,attrs,parent=svg)=>{const element=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))element.setAttribute(key,value);parent.append(element);return element;};
      const defs=node('defs',{});
      const viewport=node('clipPath',{id:'group-outline-viewport',clipPathUnits:'userSpaceOnUse'},defs);
      node('rect',{x:bounds.left+grid.clientLeft,y:bounds.top+grid.clientTop,width:grid.clientWidth,height:grid.clientHeight},viewport);
      const layer=node('g',{'clip-path':'url(#group-outline-viewport)'});
      let index=0;
      for(const {group,cells,lines} of groups.values()){
        const clipId=`group-outline-${index++}`;
        const clip=node('clipPath',{id:clipId,clipPathUnits:'userSpaceOnUse'},defs);
        for(const c of cells)node('rect',{x:c.left,y:c.top,width:c.right-c.left,height:c.bottom-c.top},clip);
        // Clip the stroke inward so adjacent groups both retain their own color.
        node('path',{'data-group-id':group.id,d:lines.join(''),stroke:group.color,'stroke-width':5,fill:'none','clip-path':`url(#${clipId})`},layer);
      }
    }
    schedule();return {schedule};
  };
})();
