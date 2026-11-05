import io
import unittest

from PIL import Image, PngImagePlugin

from scripts.community_uploaded_image_scanner import UploadedImageScanner


class UploadedImageScannerTests(unittest.TestCase):
    def setUp(self):
        self.scanner=UploadedImageScanner()

    def image(self):
        output=io.BytesIO();meta=PngImagePlugin.PngInfo();meta.add_text('private-note','removed')
        Image.new('RGB',(640,480),(245,245,245)).save(output,format='PNG',pnginfo=meta)
        return output.getvalue()+b'trailing-polyglot-bytes'

    def test_valid_image_is_fully_decoded_rewritten_and_bounded(self):
        cleaned=self.scanner.sanitize(self.image())
        self.assertTrue(cleaned.startswith(b'\xff\xd8\xff'))
        self.assertTrue(cleaned.endswith(b'\xff\xd9'))
        self.assertLessEqual(len(cleaned),self.scanner.MAX_BYTES)
        self.assertTrue(self.scanner(cleaned))
        self.assertNotIn(b'private-note',cleaned)
        self.assertNotIn(b'trailing-polyglot-bytes',cleaned)

    def test_non_image_and_truncated_image_fail_closed(self):
        for value in (b'%PDF-fixture',b'not-an-image',b'\xff\xd8\xffbroken'):
            with self.assertRaises(ValueError):self.scanner.sanitize(value)
            self.assertFalse(self.scanner(value))


if __name__=='__main__':unittest.main()
