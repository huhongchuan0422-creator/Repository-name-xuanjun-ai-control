# -*- coding: utf-8 -*-
"""Python 3.6 compatible JSON input validation probe.

Rejects duplicate keys, non-finite JSON numbers, and exponent overflow.
UTF-8 decoding is strict.
"""
from __future__ import absolute_import

import json
import math


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-finite JSON number: %s" % value)


def _parse_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite parsed JSON float")
    return number


def validate_json_bytes(raw_bytes):
    text = raw_bytes.decode("utf-8", "strict")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicates,
        parse_constant=_reject_constant,
        parse_float=_parse_float,
    )


if __name__ == "__main__":
    print(validate_json_bytes(b'{"ok":true}'))
