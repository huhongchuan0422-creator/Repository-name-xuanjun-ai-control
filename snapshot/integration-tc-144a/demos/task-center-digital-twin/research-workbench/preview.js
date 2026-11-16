'use strict';
// Isolated explicit workbench preview; no route or 3D default takeover.
window.XuanjunResearchWorkbench.mount(document.getElementById('app'),{});
var publicSummary=window.XuanjunPublicProjection.mount(document.getElementById('publicSummary'),{endpoint:new URL('../api/public-projection',document.baseURI).href});
document.getElementById('reloadPublic').onclick=publicSummary.refresh;
