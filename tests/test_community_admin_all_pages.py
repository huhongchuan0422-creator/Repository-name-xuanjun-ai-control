import re
import subprocess
import unittest
from pathlib import Path

from scripts.community_web_entries import PAGES, asset


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'demos' / 'community-stage'


class CommunityAdminAllPages(unittest.TestCase):
    def test_every_published_entry_renders_with_its_assets(self):
        for route in PAGES:
            with self.subTest(route=route):
                rendered, mime = asset(route)
                text = rendered.decode('utf-8')
                self.assertEqual(mime, 'text/html; charset=utf-8')
                self.assertIn('社区分账', text)
                self.assertNotIn('玄', text)
                self.assertNotIn('钧', text)
                for reference in re.findall(r'(?:href|src)="(/community-preview/(?:merchant|community)/[^"#?]+)', text):
                    self.assertIsNotNone(asset(reference[len('/community-preview'):]), reference)

    def test_workbench_navigation_targets_a_real_view(self):
        html = (STAGE / 'workbench.html').read_text()
        script = (STAGE / 'workbench.js').read_text()
        targets = re.findall(r'href="/merchant/workbench(#[^"]+)"', html)
        self.assertEqual(len(targets), len(set(targets)))
        for target in targets:
            with self.subTest(target=target):
                if target == '#workbenchMain':
                    self.assertIn("hash=viewTargets.has(currentHash)?currentHash:'#workbenchMain'", script)
                else:
                    self.assertIn("['" + target + "',$('", script)

    def test_community_navigation_targets_are_declared(self):
        workbench = (STAGE / 'workbench.html').read_text()
        shell = (STAGE / 'admin-shell.js').read_text()
        targets = set(re.findall(r'href="/community/portal(#[^"]+)"', workbench))
        self.assertEqual(targets, set())
        internal_targets = {
            '#community-profile', '#community-opening', '#community-promotion',
            '#merchant-members', '#platform-operations', '#admin-settings',
        }
        for target in internal_targets:
            self.assertIn(target, shell)

    def test_all_browser_api_paths_are_server_routes(self):
        browser = '\n'.join((STAGE / name).read_text() for name in (
            'web-session.js', 'communities.js', 'workbench.js', 'onboarding.js'))
        server = (ROOT / 'scripts' / 'community_mini_http.py').read_text()
        paths = set(re.findall(r"fetch\(['\"](/community-preview)?(/(?:community|merchant)/[A-Za-z0-9_./+-]+)", browser))
        self.assertTrue(paths)
        for _, path in paths:
            with self.subTest(path=path):
                self.assertIn(path, server)

    def test_points_and_both_payment_ad_surfaces_are_present(self):
        application = (STAGE / 'onboarding.html').read_text()
        review = (STAGE / 'onboarding.js').read_text()
        checkout = (ROOT / 'clients/community-mini/pages/checkout/index.wxml').read_text()
        for tier in ('0', '10', '20', '25', '30'):
            self.assertIn('value="' + tier + '"', application)
        self.assertIn('爱心积分抵扣比例（申请值）', review)
        self.assertIn('爱心积分抵扣比例（审核生效）', review)
        self.assertNotIn('申请积分抵扣比例', review)
        self.assertNotIn('积分商城申请抵扣比例', review)
        self.assertIn('payment-ad-before', checkout)
        self.assertIn('payment-ad-success', checkout)
        self.assertIn('afterAdVerified', checkout)

    def test_community_profile_is_management_first_and_editor_is_on_demand(self):
        shell = (STAGE / 'admin-shell.js').read_text()
        css = (STAGE / 'admin-shell.css').read_text()
        self.assertIn("profileHeading.textContent='社区资料管理'", shell)
        self.assertIn("editor.className='community-profile-editor';editor.hidden=true", shell)
        self.assertIn("profileStats.className='management-stats'", shell)
        self.assertIn("openHeading.textContent='社区开通管理'", shell)
        self.assertIn("promotionHeading.textContent='社区推广管理'", shell)
        self.assertIn("memberHeading.textContent='社区商家'", shell)
        self.assertIn("merchantHeading.textContent='商家管理'", shell)
        self.assertIn('.community-profile-editor #profile', css)
        self.assertIn('@media(max-width:700px)', css)

    def test_twelve_management_pages_use_list_filter_detail_patterns(self):
        html = (STAGE / 'workbench.html').read_text()
        script = (STAGE / 'workbench.js').read_text()
        shell = (STAGE / 'admin-shell.js').read_text()
        review = (STAGE / 'onboarding.js').read_text()
        for control in (
            'merchantKeyword', 'merchantStatusFilter', 'merchantRecords', 'merchantDetail',
            'priceKeyword', 'priceStatusFilter', 'priceCatalogList', 'priceDetail', 'priceEditor',
            'mallOrderKeyword', 'mallOrders', 'mallOrderDetail',
            'pointsKeyword', 'pointsTypeFilter', 'pointsLedger', 'pointsDetail',
            'orderKeyword',
            'refundKeyword', 'refundStatusFilter', 'refundApplications',
            'adKeyword', 'adSlotFilter', 'adStatusFilter', 'splitKeyword', 'splitStatusFilter',
        ):
            self.assertIn('id="' + control + '"', html, control)
        self.assertIn("['#mall-orders',$('mall-orders')]", script)
        self.assertNotIn("['#mall-orders',$('orders-section')]", script)
        for unsupported in ('orderUserKeyword', 'orderMerchantKeyword', 'mallProductKeyword',
                            'mallUserKeyword', 'pointsStart', 'pointsEnd'):
            self.assertNotIn('id="' + unsupported + '"', html)
            self.assertNotIn("$('" + unsupported + "')", script)
        self.assertNotIn("$('orderDetail').textContent=JSON.stringify", script)
        self.assertNotIn("$('refundApplicationResult').textContent=JSON.stringify", script)
        self.assertNotIn("$('priceResult').textContent=JSON.stringify", script)
        self.assertNotIn("$('providerActionResult').textContent=JSON.stringify", script)
        self.assertNotIn("$('staffResult').textContent=JSON.stringify", script)
        self.assertNotIn("$('storeResult').textContent=JSON.stringify", script)
        self.assertIn("$('ruleId').closest('label').hidden=true", script)
        self.assertIn("$('ruleVersion').closest('label').hidden=true", script)
        self.assertIn("$('ruleRevision').closest('label').hidden=true", script)
        for phrase in ('reviewMerchantKeyword', '申请编号、商家名称、门店名称、联系人、经营类目、申请状态', 'reviewQueueCount'):
            self.assertIn(phrase, review)
        self.assertNotIn('商家审核列表', review)
        for phrase in ('memberKeyword', 'memberState', 'operationKeyword', 'operationType'):
            self.assertIn(phrase, shell)

    def test_supported_management_filters_keep_and_exclude_real_rows(self):
        subprocess.run([
            'node', str(ROOT / 'tests' / 'community_management_filter_helpers.cjs'),
            str(STAGE / 'workbench.js'),
        ], check=True, timeout=30)

    def test_product_and_advertisement_images_are_required_sized_and_listed(self):
        html = (STAGE / 'workbench.html').read_text()
        script = (STAGE / 'workbench.js').read_text()
        styles = (STAGE / 'workbench.css').read_text()
        for phrase in (
            '商品图片 <small class="upload-guidance">请上传 800 × 800 像素（1:1）',
            '广告图片 <small class="upload-guidance">请上传 1200 × 400 像素（3:1）',
            '尺寸不符无法保存',
            'id="itemImage" type="file"', 'id="adImage" type="file"',
            'id="itemPrice" type="number" min="0.01"',
            'id="itemStock" type="number" min="0"',
            'id="itemEnabled" type="checkbox" checked',
        ):
            self.assertIn(phrase, html)
        for phrase in (
            "loadValidatedImage(file,{width:800,height:800,label:'商品图片'})",
            "loadValidatedImage(file,{width:1200,height:400,label:'广告图片'})",
            "if(embeddedMode&&!itemEditorImageData)throw Error('请上传商品图片')",
            "if(!adEditorImageData)throw Error('请上传广告图片')",
            "['商品图片','商品编号','商品名称','商品描述','状态','售价 / 库存','操作']",
            "yuanToMinor($('itemPrice').value,'单价')",
            "commerce(t,'price_set',{item_id:itemId",
            "keywords.every(keyword=>text.includes(keyword))",
            "matchesCatalogKeywords(item,query)",
            "['广告图片','广告编号','广告标题','广告位','投放状态','审核状态','投放时间','操作']",
        ):
            self.assertIn(phrase, script)
        self.assertIn('.catalog-image img', styles)
        self.assertIn('.ad-list-image img', styles)
        self.assertNotIn('pattern="[A-Za-z0-9_-]', html)
        self.assertNotIn(".pattern='[A-Za-z0-9_-]", script)
        self.assertEqual(html.count('pattern="[A-Za-z0-9_\\-]{1,64}"'), 6)
        self.assertIn("splitReceiver.pattern='[A-Za-z0-9_\\\\-]{1,100}'", script)
        self.assertNotIn('服务端', script)

    def test_merchant_money_fields_use_yuan_and_convert_at_request_boundary(self):
        html = (STAGE / 'workbench.html').read_text()
        script = (STAGE / 'workbench.js').read_text()
        shell = (STAGE / 'admin-shell.js').read_text()
        for phrase in ('订单金额（元）', '单价（元）', '退款金额（元）', '回退金额（元）'):
            self.assertIn(phrase, html)
        for forbidden in ('金额（分）', '退款金额（整数分）', '最小货币单位'):
            self.assertNotIn(forbidden, html + script + shell)
        self.assertIn("function operationMoney(v,c){return Number.isSafeInteger(v)&&typeof c==='string'&&c?(c==='CNY'?'¥':'')+(v/100).toFixed(2)", shell)
        for phrase in (
            "yuanToMinor($('refundAmount').value,'退款金额')",
            "yuanToMinor($('providerRefundAmount').value,'退款金额')",
            "yuanToMinor($('returnAmount').value,'回退金额')",
            "yuanToMinor($('priceUnit').value,'单价')",
            "moneyText(line.unit_minor)",
        ):
            self.assertIn(phrase, script)

    def test_business_views_do_not_expose_technical_copy(self):
        visible_sources = '\n'.join((STAGE / name).read_text() for name in (
            'admin-shell.js', 'communities.js', 'onboarding.js'))
        for phrase in (
            '最小货币单位', '查看分账快照', '工作区权限',
            '原映射', '当前版本CAS', '当前原', '真实回执', '真实回读',
            '当前社区版本', '版本0', '版本填0',
        ):
            self.assertNotIn(phrase, visible_sources)

    def test_business_search_uses_compact_toolbar_and_explicit_placeholders(self):
        html = (STAGE / 'workbench.html').read_text()
        styles = (STAGE / 'workbench.css').read_text()
        self.assertGreaterEqual(html.count('compact-toolbar'), 7)
        for phrase in (
            'placeholder="商家名称、编号或联系方式"',
            'placeholder="退款单号、订单号、用户或原因"',
            'placeholder="商品名称或编号"',
            'placeholder="广告标题或编号"',
        ):
            self.assertIn(phrase, html)
        for unrelated_copy in (
            '统一管理积分商城商品、销售状态与展示顺序',
            '修改操作集中在右侧编辑区',
            '腾讯广告需由平台配置小程序广告位 ID',
        ):
            self.assertNotIn(unrelated_copy, html)
        self.assertIn('.compact-toolbar label{flex:0 1 210px;font-size:0}', styles)
        self.assertIn('.compact-toolbar input,.compact-toolbar select', styles)

    def test_customer_pages_translate_protocol_data_and_describe_order_scope_honestly(self):
        communities = (STAGE / 'communities.js').read_text()
        onboarding = (STAGE / 'onboarding.js').read_text()
        shell = (STAGE / 'admin-shell.js').read_text()
        workbench = (STAGE / 'workbench.js').read_text()
        html = (STAGE / 'workbench.html').read_text()

        for target in ('result', 'customerResult', 'merchantResult', 'platformViewResult'):
            self.assertNotRegex(
                communities,
                r"\$\('" + target + r"'\)\.textContent\s*=.*JSON\.stringify",
                target,
            )
        self.assertNotIn("$('wechatState').textContent=JSON.stringify", onboarding)
        for protocol_label in (
            '管理员类型：LEGAL', 'IDENTIFICATION_TYPE_IDCARD 或',
            '账户类型：BANK_ACCOUNT_TYPE',
        ):
            self.assertNotIn(protocol_label, onboarding)
        for internal_value in (
            "['LEGAL','法人/经营者']", "['SUPER','授权经办人']",
            "['IDENTIFICATION_TYPE_IDCARD','居民身份证']",
            "['BANK_ACCOUNT_TYPE_CORPORATE','对公账户']",
            "['BANK_ACCOUNT_TYPE_PERSONAL','个人银行卡']",
        ):
            self.assertIn(internal_value, onboarding)

        self.assertIn("operationOrderState(state)", shell)
        self.assertIn("operationProjectRole(r.project_role)", shell)
        self.assertIn("operationAuditEvent(r.event)", shell)
        self.assertNotIn("state+'：'", shell)
        self.assertNotIn("['项目角色',r.project_role]", shell)
        self.assertNotIn("['事件',r.event]", shell)

        self.assertIn('<h2>订单查询</h2>', html)
        self.assertNotIn('不能据此判定积分商城归属', html)
        self.assertNotIn('<h2>商城订单</h2>', html)
        self.assertNotIn('<th>商品</th><th>用户</th>', html)
        self.assertIn("['#mall-orders','订单查询']", workbench)
        self.assertNotIn('本页不宣称商城归属', workbench)
        self.assertNotIn("['商品','接口未返回商品字段']", workbench)

    def test_member_material_and_store_protocol_codes_are_never_customer_labels(self):
        communities = (STAGE / 'communities.js').read_text()
        onboarding = (STAGE / 'onboarding.js').read_text()
        shell = (STAGE / 'admin-shell.js').read_text()

        self.assertIn("{CUSTOMER:'消费者',MERCHANT:'商家'}[value]||'类型待确认'", communities)
        self.assertIn("operation==='members'?memberKindText(item.kind)", communities)
        self.assertNotIn("operation==='members'?item.kind", communities)
        self.assertIn("merchantStoreText(item.store_status)", communities)

        material_labels = {
            'operator_identity': '经办人证件正面',
            'operator_identity_back': '经办人证件反面',
            'operator_authorization': '经办人授权书',
            'industry_permit': '行业经营许可',
        }
        for index in range(1, 5):
            material_labels['ubo_' + str(index) + '_front'] = '受益人' + str(index) + '证件正面'
            material_labels['ubo_' + str(index) + '_back'] = '受益人' + str(index) + '证件反面'
        for kind, label in material_labels.items():
            self.assertIn(kind + ":'" + label + "'", onboarding)
        self.assertIn("kind=>materialKindTitles[kind]||'其他补充材料'", onboarding)
        self.assertNotIn("catalog?.materials?.find(item=>item.id===kind)?.title", onboarding)
        self.assertNotIn("description?.title||kind", onboarding)
        self.assertNotIn("?.title||material.kind", onboarding)
        self.assertNotIn("?.title||m.kind", onboarding)

        self.assertIn("ACTIVE:'营业中'", shell)
        self.assertIn("[item.store_status]||'状态待确认'", shell)
        self.assertNotIn("String(item.store_status)", shell)

    def test_management_objects_keep_list_detail_return_in_current_navigation_page(self):
        html = (STAGE / 'workbench.html').read_text()
        workbench = (STAGE / 'workbench.js').read_text()
        for target in ('ordersMainDetail','refundApplicationDetail','catalogDetail','priceDetail','adDetail','pointsDetail'):
            self.assertIn('id="' + target + '"', html)
        for target in ('ordersMainDetailBack','refundApplicationDetailBack','catalogDetailBack','priceDetailBack','adDetailBack','pointsDetailBack'):
            self.assertIn("$('" + target + "').onclick", workbench)
        self.assertNotIn("renderBusinessFields($('report'),'广告详情'", workbench)
        self.assertIn("call('points_records',{},ticket)", workbench)
        self.assertIn("commerce(t,'price_list',{})", workbench)
        self.assertNotIn("'待查询'", workbench)
        self.assertNotIn("'账号、门店与业务范围'", workbench)

    def test_owner_user_list_and_revenue_amendments_are_real_wired_pages(self):
        shell = (STAGE / 'admin-shell.js').read_text()
        portal = (STAGE / 'communities.js').read_text()
        directory = (ROOT / 'scripts' / 'community_center_communities.py').read_text()
        views = (ROOT / 'scripts' / 'community_platform_views.py').read_text()
        inventory = (ROOT / 'scripts' / 'community_admin_route_inventory.py').read_text()
        for label in ('用户编号','用户名称','用户类型','消费金额','积分余额','关联订单','推荐人','状态','操作'):
            self.assertIn(label, shell)
        self.assertIn("open.textContent='查看';edit.textContent='编辑'", shell)
        self.assertIn("communityUpdatePlatformCustomer({user_id:record.user_id", shell)
        self.assertIn("window.communityUpdatePlatformCustomer=async params=>", portal)
        self.assertIn("用户资料已保存并回读。", shell)
        self.assertIn("'platform_customers'", directory)
        self.assertIn("elif customer_update", views)
        self.assertNotIn("'platform_customer_update'", inventory)
        self.assertIn("reportQuery.className='management-filter-bar report-filter-bar'", shell)
        self.assertIn("reportSearch.textContent='查询'", shell)
        self.assertIn("reportDetail.append(reportControls,reportRows,reportBack)", shell)
        self.assertNotIn('正在加载用户列表', shell)
        self.assertIn("operationFilterButton.textContent='查询'", shell)
        workbench_html = (STAGE / 'workbench.html').read_text()
        workbench_script = (STAGE / 'workbench.js').read_text()
        self.assertIn('id="publishAd"', workbench_html)
        self.assertIn('>发布广告</button>', workbench_html)
        self.assertIn("$('publishAd').onclick", workbench_script)
        self.assertIn("saved=response.result", workbench_script)
        self.assertIn("campaignId=saved.campaign_id||saved.id", workbench_script)
        self.assertIn("currentState=saved.status||saved.state", workbench_script)
        self.assertIn("call('ad_state',{campaign_id:campaignId,state:nextState,expected_version:saved.version},t)", workbench_script)
        self.assertNotIn("reportReference", shell)
        self.assertNotIn("暂无分账记录", shell)
        self.assertIn("cell.textContent=message||'当前条件下无记录'", shell)
        self.assertIn("memberQueryDisclosure.hidden=true", shell)
        self.assertIn("orderQuery.hidden=users", shell)


if __name__ == '__main__':
    unittest.main()
