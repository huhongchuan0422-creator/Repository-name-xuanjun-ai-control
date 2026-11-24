const {agreement}=require('./content');
Page({
  data:{document:null},
  onLoad(){this.setData({document:agreement()});},
});
