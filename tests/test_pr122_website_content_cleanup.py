import tempfile
import unittest
from pathlib import Path
from scripts import pr122_website_content_cleanup as c


class CleanupTests(unittest.TestCase):
    def test_only_exact_duplicate_contact_pair(self):
        a = '<a class="button" href="/contact">描述我的需求</a>'
        b = '<a class="button secondary" href="/contact">联系玄钧</a>'
        self.assertEqual(c.remove_duplicate_contact(a+b), a)
        self.assertEqual(c.remove_duplicate_contact(a+b.replace('/contact', '/other')), a+b.replace('/contact', '/other'))

    def test_merge_preserves_unique_content_and_access_warning(self):
        dest = '<main><h1>项目中心</h1><p>服务端项目授权</p></main>'
        source = '<main><h1>验收</h1><p>登录尚未开放</p><a href="/preview/">预览</a></main>'
        out = c.merge_section(dest, source, 'acceptance', '验收')
        for value in ['服务端项目授权', '登录尚未开放', 'href="/preview/"', 'id="acceptance"']:
            self.assertIn(value, out)
        self.assertEqual(out.count('<h1>'), 1)

    def test_active_source_not_silently_merged(self):
        with self.assertRaisesRegex(ValueError, 'ACTIVE_MERGE'):
            c.merge_section('<main></main>', '<main><script>run()</script></main>', 'a', 'a')

    def test_compatibility_entry_keeps_header_footer(self):
        src = '<header>菜单</header><main><h1>旧页</h1></main><footer>备案</footer>'
        out = c.compatibility_page(src, '/visual/#catalog', '场景目录')
        for value in ['<header>菜单</header>', '<footer>备案</footer>', 'href="/visual/#catalog"']:
            self.assertIn(value, out)

    def test_wrong_source_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_DRIFT:index.html'):
            c.transform({'index.html': b'unknown successor'})

    def test_output_cannot_be_inside_source(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'OUTPUT_INSIDE_SOURCE'):
                c.build(Path(d), Path(d)/'candidate')

    def test_new_css_does_not_hide_navigation_or_buttons(self):
        self.assertNotIn('display:none', c.CSS)
        self.assertNotIn('pointer-events:none', c.CSS)
        self.assertIn('flex-wrap:wrap', c.CSS)
        self.assertIn('min-height:44px', c.CSS)

    def test_html_merge_adds_no_inline_script_or_styles(self):
        result = c.merge_section('<main></main>', '<main><p>内容</p></main>', 'a', '标题')
        self.assertNotIn('<script', result)
        self.assertNotIn('style=', result)


if __name__ == '__main__':
    unittest.main()
