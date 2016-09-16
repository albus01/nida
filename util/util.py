"""
author: shawnsha@tencent.com
date: 2016.08.05
Utility functions and datas for nida.
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function,with_statement

import sys
import os

PY3 = sys.version_info >= (3,)

if PY3:
    string_compatible  = str
    unicode_compatible = str
else:
    string_compatible  = basestring
    unicode_compatible = unicode

_UNICODE_TYPE = (unicode_compatible, type(None))

if type('') is not type(b''):
    def u(s):
        return s
    bytes_type = bytes
    unicode_type = str
    basestring_type = str
else:
    def u(s):
        return s.decode('unicode_escape')
    bytes_type = str
    unicode_type = unicode
    basestring_type = basestring


def _unicode(value):
    """
    Convert str to unicode str.
    """
    if isinstance(value, _UNICODE_TYPE):
        return value
    if not isinstance(value, bytes):
        raise TypeError("Unexpected type %r, need bytes, unicode or None" %
                        value)
    return value.decode("utf-8")

class Error(Exception):
    pass

def get_errno(e):
    if hasattr(e, 'errno'):
        return e.errno
    elif e.args:
        return e.args[0]
    else:
        return None

class ObjectDict(dict):
    """Makes a dictionary behave like an object, with attribute-style access.
    """
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value


