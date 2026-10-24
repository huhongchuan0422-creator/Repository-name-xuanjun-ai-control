import {verifiedPreviewUrl} from './api.js';import {submitLegacy,submitCandidate} from './submission.js';
export class ProjectJourney{
 constructor(api,journal){this.api=api;this.journal=journal}
 async projects(){const m=await this.api.me();if(!Array.isArray(m.projects))throw Error('ACCOUNT_ONLY_NO_PROJECT_ACCESS');return m}
 async project(p){const [checklist,previews,changes,messages]=await Promise.all([this.api.checklist(p.id),this.api.previews(p.id),this.api.changes(p.id),this.api.messages(p.id)]);return{project:p,checklist,previews:{...previews,pages:(previews.pages||[]).map(x=>({...x,url:verifiedPreviewUrl(x.url,p.id,x.sha256)}))},changes,messages}}
 async feedbackContext(p,page){if(p.role!=='OWNER')throw Error('OWNER_PREVIEW_REQUIRED');return this.api.context(p.id,page.path,page.sha256)}
 async submitLegacy(p,page,text){if(p.role!=='OWNER')throw Error('OWNER_PREVIEW_REQUIRED');return submitLegacy(this.api,this.journal,{project:p.id,page:page.path,version:page.sha256,text,intent:'RECTIFICATION'})}
 async submitCandidate(p,page,text,o){return submitCandidate(this.api,this.journal,{project:p.id,page:page.path,version:page.sha256,text,intent:'RECTIFICATION'},o)}
 async currentPage(p,path){const d=await this.api.previews(p.id),page=(d.pages||[]).find(x=>x.path===path);if(!page)throw Error('CURRENT_PREVIEW_NOT_FOUND');return{...page,url:verifiedPreviewUrl(page.url,p.id,page.sha256)}}
 async updates(p,page){return this.api.updates(p.id,page.path,page.sha256)}
 async retest(p,page,u,action,reason){return this.api.retest({project:p.id,caseId:u.case,revision:u.revision,page:page.path,version:page.sha256,delivery_sha256:u.delivery_sha256,action,reason})}
 async ask(p,text){if(!text?.trim())throw Error('QUESTION_REQUIRED');return this.api.message(p.id,text.trim())}
}
