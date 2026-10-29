"use strict";
(()=>{
 const main=document.querySelector('main'),nav=document.getElementById('admin-sections');
 if(!main||!nav)return;
 const sections=Array.from(main.children).filter(el=>el.tagName==='SECTION');
 const result=sections.find(el=>el.querySelector('#result'));
 const panels=sections.filter(el=>el!==result);
 const home=document.createElement('section');home.className='admin-home';
 const heading=document.createElement('h2');heading.textContent='社区运营工作台';home.append(heading);
 const intro=document.createElement('p');intro.textContent='选择功能查看与处理。业务数据由原账户权限决定，未读取时不展示示例金额或记录。';home.append(intro);
 const cards=document.createElement('div');cards.className='admin-cards';home.append(cards);
 const back=document.createElement('button');back.type='button';back.className='admin-back';back.textContent='返回工作台';
 main.insertBefore(home,sections[0]);main.insertBefore(back,home);
 const buttons=[];
 const profileForm=document.getElementById('profile');
 const profilePanel=profileForm.closest('section');
 const profileIndex=panels.indexOf(profilePanel);
 const detail=document.createElement('div');detail.className='community-profile-detail';detail.hidden=true;
 const detailTitle=document.createElement('h3');detailTitle.textContent='社区资料详情';detail.append(detailTitle);
 const fields=document.createElement('dl');detail.append(fields);
 const edit=document.createElement('button');edit.type='button';edit.textContent='编辑资料';
 const reread=document.createElement('button');reread.type='button';reread.textContent='回读当前记录';
 const toList=document.createElement('button');toList.type='button';toList.textContent='返回记录列表';
 const create=document.createElement('button');create.type='button';create.textContent='登记新社区';
 const hint=document.createElement('p');hint.className='profile-hint';hint.textContent='尚未读取；点击“我的社区”查询原记录。';
 const submit=document.getElementById('submit'),mine=document.getElementById('mine');
 profilePanel.append(hint,create,detail);detail.append(edit,reread,toList,profileForm,submit);
 profileForm.hidden=true;submit.hidden=true;
 let profileRecord=null,activeIndex=null;
 function emptyProfile(message){profileRecord=null;detail.hidden=true;profileForm.hidden=true;submit.hidden=true;fields.replaceChildren();hint.textContent=message;}
 window.communityProfileView=({type,record})=>{
  if(type==='reset'){emptyProfile('身份或工作区已变化，请重新查询。');return;}
  if(type==='error'){emptyProfile('本次操作未确认或权限已变化；请回读原记录，不要重复提交。');return;}
  if(type==='list'){detail.hidden=true;profileForm.hidden=true;submit.hidden=true;if(result)result.hidden=false;hint.textContent='查询原社区记录中…';return;}
  if(type==='listed'){hint.textContent=record.count?'已读取当前页 '+record.count+' 条原记录。':'当前页没有记录。';return;}
  if(type!=='detail'||activeIndex!==profileIndex)return;
  profileRecord=record;fields.replaceChildren();
  for(const [label,key] of [['社区名称','name'],['社区介绍','description'],['联系人及联系方式','contact'],['状态','state'],['当前版本','version']]){
   const term=document.createElement('dt'),value=document.createElement('dd');term.textContent=label;value.textContent=record[key]===undefined?'当前权限未返回该字段':String(record[key]);fields.append(term,value);
  }
  detail.hidden=false;profileForm.hidden=true;submit.hidden=true;
  edit.disabled=!['DRAFT','CORRECTION','REJECTED'].includes(record.state);
  hint.textContent='已读取原记录；可编辑状态仍由服务端校验所有者权限。';
  if(result)result.hidden=true;
 };
 edit.addEventListener('click',()=>{if(!profileRecord||edit.disabled)return;profileForm.hidden=false;submit.hidden=false;});
 reread.addEventListener('click',()=>{if(profileRecord)document.getElementById('read').click();});
 toList.addEventListener('click',()=>{detail.hidden=true;profileForm.hidden=true;submit.hidden=true;if(result)result.hidden=false;hint.textContent='已返回原列表；需要最新数据时点击“我的社区”。';});
 create.addEventListener('click',()=>{document.getElementById('directoryStatus').onchange();profileRecord=null;fields.replaceChildren();detail.hidden=false;profileForm.hidden=false;submit.hidden=true;edit.disabled=true;hint.textContent='登记新社区；保存仍使用原 register 接口及服务端权限。';});

 function select(index){
  activeIndex=index;
  // Move, never clone, the original query result so list/detail uses the same cursor and handlers.
  if(index===profileIndex)profilePanel.append(result);else if(result)main.append(result);
  home.hidden=index!==null;back.hidden=index===null;
  panels.forEach((panel,i)=>{panel.hidden=i!==index;});
  // Preserve the original result DOM and business handlers without cloning or rebinding.
  if(result)result.hidden=index===null||(index===profileIndex&&!detail.hidden);
  buttons.forEach((button,i)=>{if(i===index)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  if(index!==null){const title=panels[index].querySelector('h2');title.tabIndex=-1;title.focus();}
 }
 const homeButton=document.createElement('button');homeButton.type='button';homeButton.textContent='工作台首页';homeButton.addEventListener('click',()=>select(null));nav.append(homeButton);
 panels.forEach((panel,index)=>{
  const title=panel.querySelector('h2').textContent;
  const button=document.createElement('button');button.type='button';button.textContent=title;button.addEventListener('click',()=>select(index));nav.append(button);buttons.push(button);
  const card=document.createElement('button');card.type='button';card.className='admin-card';
  const strong=document.createElement('strong');strong.textContent=title;const description=document.createElement('span');description.textContent='打开原业务模块 · 按当前角色权限';card.append(strong,description);card.addEventListener('click',()=>select(index));cards.append(card);
 });
 back.addEventListener('click',()=>select(null));select(null);
})();
