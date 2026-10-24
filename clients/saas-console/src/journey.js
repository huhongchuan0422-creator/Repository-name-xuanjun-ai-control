import {verifiedPreviewUrl} from './api.js';
import {submitIntent} from './submission.js';
export class ProjectJourney {
 constructor(api,journal){this.api=api;this.journal=journal;}
 async projects(){const me=await this.api.me();if(!Array.isArray(me.projects))throw new Error('ACCOUNT_ONLY_NO_PROJECT_ACCESS');return me;}
 async project(p){const [checklist,previews,changes,messages]=await Promise.all([this.api.checklist(p.id),this.api.previews(p.id),this.api.changes(p.id),this.api.messages(p.id)]);return {project:p,checklist,previews:{...previews,pages:(previews.pages||[]).map(x=>({...x,url:verifiedPreviewUrl(x.url)}))},changes,messages};}
 async feedbackContext(p,page){if(p.role!=='OWNER')throw new Error('OWNER_PREVIEW_REQUIRED');return this.api.context(p.id,page.path,page.sha256);}
 async submitLegacy(p,page,text){if(p.role!=='OWNER')throw new Error('OWNER_PREVIEW_REQUIRED');return submitIntent(this.api,this.journal,{project:p.id,page:page.path,version:page.sha256,text,intent:'RECTIFICATION'},{idempotent:false});}
 // Candidate-only path. UI does not invoke this until the backend candidate is accepted and wired.
 async submitCandidate(p,page,text,{retryUnknown=false}={}){if(p.role!=='OWNER')throw new Error('OWNER_PREVIEW_REQUIRED');return submitIntent(this.api,this.journal,{project:p.id,page:page.path,version:page.sha256,text,intent:'RECTIFICATION'},{idempotent:true,retryUnknown});}
 async updates(p,page){if(p.role!=='OWNER')throw new Error('OWNER_PREVIEW_REQUIRED');return this.api.updates(p.id,page.path,page.sha256);}
 async retest(p,page,u,action,reason){if(p.role!=='OWNER')throw new Error('OWNER_PREVIEW_REQUIRED');return this.api.retest({project:p.id,caseId:u.case,revision:u.revision,page:page.path,version:page.sha256,delivery_sha256:u.delivery_sha256,action,reason});}
 async ask(p,text){if(!text?.trim())throw new Error('QUESTION_REQUIRED');return this.api.message(p.id,text.trim());}
}
