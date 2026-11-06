"""Opt-in scanner for mini-program image materials.

The scanner decodes the complete image and rewrites it as a bounded JPEG before
the original encrypted object store sees it. This removes metadata and trailing
polyglot bytes; malformed, oversized, non-image and decompression-bomb inputs
fail closed. It is deliberately image-only and never admits PDFs.
"""
from io import BytesIO
import warnings

from PIL import Image, ImageOps


class UploadedImageScanner:
    MAX_BYTES = 5_000_000
    MAX_PIXELS = 40_000_000

    def sanitize(self, raw):
        if type(raw) is not bytes or not 1 <= len(raw) <= self.MAX_BYTES:
            raise ValueError('IMAGE_SIZE_INVALID')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                with Image.open(BytesIO(raw)) as source:
                    if source.format not in ('JPEG', 'PNG'):
                        raise ValueError('IMAGE_FORMAT_INVALID')
                    source.load()
                    if source.width < 1 or source.height < 1 or source.width * source.height > self.MAX_PIXELS:
                        raise ValueError('IMAGE_DIMENSIONS_INVALID')
                    image = ImageOps.exif_transpose(source).convert('RGB')
                    for quality in (88, 78, 68, 58):
                        output = BytesIO()
                        image.save(output, format='JPEG', quality=quality, optimize=True)
                        value = output.getvalue()
                        if len(value) <= self.MAX_BYTES:
                            return value
        except (OSError, SyntaxError, ValueError, Warning):
            raise ValueError('IMAGE_SCAN_REJECTED') from None
        raise ValueError('IMAGE_SIZE_INVALID')

    def __call__(self, raw):
        if type(raw) is not bytes or not raw.startswith(b'\xff\xd8\xff') or not raw.endswith(b'\xff\xd9'):
            return False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                with Image.open(BytesIO(raw)) as image:
                    image.load()
                    return image.format == 'JPEG' and 0 < image.width * image.height <= self.MAX_PIXELS
        except (OSError, SyntaxError, ValueError, Warning):
            return False
