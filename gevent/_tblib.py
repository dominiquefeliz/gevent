# -*- coding: utf-8 -*-
# A vendored version of part of https://github.com/ionelmc/python-tblib
####
# Copyright (c) 2013-2014, Ionel Cristian Mărieș
# All rights reserved.

# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
# following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
# disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
# disclaimer in the documentation and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
####

# cpython.py

"""
Taken verbatim from Jinja2.

https://github.com/mitsuhiko/jinja2/blob/master/jinja2/debug.py#L267
"""
#import platform # XXX: gevent cannot import platform at the top level; interferes with monkey patching
import sys


def _init_ugly_crap():
    """This function implements a few ugly things so that we can patch the
    traceback objects.  The function returned allows resetting `tb_next` on
    any python traceback object.  Do not attempt to use this on non cpython
    interpreters
    """
    import ctypes
    from types import TracebackType

    # figure out side of _Py_ssize_t
    if hasattr(ctypes.pythonapi, 'Py_InitModule4_64'):
        _Py_ssize_t = ctypes.c_int64
    else:
        _Py_ssize_t = ctypes.c_int

    # regular python
    class _PyObject(ctypes.Structure):
        pass
    _PyObject._fields_ = [
        ('ob_refcnt', _Py_ssize_t),
        ('ob_type', ctypes.POINTER(_PyObject))
    ]

    # python with trace
    if hasattr(sys, 'getobjects'):
        class _PyObject(ctypes.Structure):
            pass
        _PyObject._fields_ = [
            ('_ob_next', ctypes.POINTER(_PyObject)),
            ('_ob_prev', ctypes.POINTER(_PyObject)),
            ('ob_refcnt', _Py_ssize_t),
            ('ob_type', ctypes.POINTER(_PyObject))
        ]

    class _Traceback(_PyObject):
        pass
    _Traceback._fields_ = [
        ('tb_next', ctypes.POINTER(_Traceback)),
        ('tb_frame', ctypes.POINTER(_PyObject)),
        ('tb_lasti', ctypes.c_int),
        ('tb_lineno', ctypes.c_int)
    ]

    def tb_set_next(tb, next):
        """Set the tb_next attribute of a traceback object."""
        if not (isinstance(tb, TracebackType) and
                (next is None or isinstance(next, TracebackType))):
            raise TypeError('tb_set_next arguments must be traceback objects')
        obj = _Traceback.from_address(id(tb))
        if tb.tb_next is not None:
            old = _Traceback.from_address(id(tb.tb_next))
            old.ob_refcnt -= 1
        if next is None:
            obj.tb_next = ctypes.POINTER(_Traceback)()
        else:
            next = _Traceback.from_address(id(next))
            next.ob_refcnt += 1
            obj.tb_next = ctypes.pointer(next)

    return tb_set_next

tb_set_next = None
# try:
#     if platform.python_implementation() == 'CPython':
#         #tb_set_next = _init_ugly_crap()
#         tb_set_next = None
# except Exception as exc:
#     sys.stderr.write("Failed to initialize cpython support: {!r}".format(exc))
# del _init_ugly_crap

# __init__.py
try:
    from __pypy__ import tproxy
except ImportError:
    tproxy = None

#if not tb_set_next and not tproxy:
#    raise ImportError("Cannot use tblib. Runtime not supported.")


from types import CodeType
from types import TracebackType

PY3 = sys.version_info[0] == 3


class _AttrDict(dict):
    def __getattr__(self, attr):
        return self[attr]


class __traceback_maker(Exception):
    pass


class Code(object):
    def __init__(self, code):
        self.co_filename = code.co_filename
        self.co_name = code.co_name
        self.co_nlocals = code.co_nlocals
        self.co_stacksize = code.co_stacksize
        self.co_flags = code.co_flags
        self.co_firstlineno = code.co_firstlineno


class Frame(object):
    def __init__(self, frame):
        # gevent: python 2.6 syntax fix
        self.f_globals = {'__file__': frame.f_globals.get('__file__'),
                          '__name__': frame.f_globals.get('__name__')}
        self.f_code = Code(frame.f_code)


class Traceback(object):
    def __init__(self, tb):
        self.tb_frame = Frame(tb.tb_frame)
        self.tb_lineno = tb.tb_lineno
        if tb.tb_next is None:
            self.tb_next = None
        else:
            self.tb_next = Traceback(tb.tb_next)

    def as_traceback(self):
        if tproxy:
            return tproxy(TracebackType, self.__tproxy_handler)
        elif tb_set_next:
            f_code = self.tb_frame.f_code
            code = compile('\n' * (self.tb_lineno - 1) + 'raise __traceback_maker', self.tb_frame.f_code.co_filename, 'exec')
            if PY3:
                code = CodeType(
                    0, 0,
                    f_code.co_nlocals, f_code.co_stacksize, f_code.co_flags,
                    code.co_code, code.co_consts, code.co_names, code.co_varnames,
                    f_code.co_filename, f_code.co_name,
                    code.co_firstlineno, b"",
                    (), ()
                )
            else:
                code = CodeType(
                    0,
                    f_code.co_nlocals, f_code.co_stacksize, f_code.co_flags,
                    code.co_code, code.co_consts, code.co_names, code.co_varnames,
                    f_code.co_filename.encode(), f_code.co_name.encode(),
                    code.co_firstlineno, b"",
                    (), ()
                )

            try:
                exec(code, self.tb_frame.f_globals, {})
            except:
                tb = sys.exc_info()[2].tb_next
                tb_set_next(tb, self.tb_next and self.tb_next.as_traceback())
                try:
                    return tb
                finally:
                    del tb
        else:
            raise RuntimeError("Cannot re-create traceback !")

    def __tproxy_handler(self, operation, *args, **kwargs):
        if operation in ('__getattribute__', '__getattr__'):
            if args[0] == 'tb_next':
                return self.tb_next and self.tb_next.as_traceback()
            else:
                return getattr(self, args[0])
        else:
            return getattr(self, operation)(*args, **kwargs)


# pickling_support.py


def unpickle_traceback(tb_frame, tb_lineno, tb_next):
    ret = object.__new__(Traceback)
    ret.tb_frame = tb_frame
    ret.tb_lineno = tb_lineno
    ret.tb_next = tb_next
    return ret.as_traceback()


def pickle_traceback(tb):
    return unpickle_traceback, (Frame(tb.tb_frame), tb.tb_lineno, tb.tb_next and Traceback(tb.tb_next))


def install():
    try:
        import copy_reg
    except ImportError:
        import copyreg as copy_reg

    copy_reg.pickle(TracebackType, pickle_traceback)

# Added by gevent

# We have to defer the initilization, and especially the import of platform,
# until runtime.


def _import_dump_load():
    global dumps
    global loads
    try:
        import cPickle as pickle
    except ImportError:
        import pickle
    dumps = pickle.dumps
    loads = pickle.loads

dumps = loads = None

_installed = False


def _init():
    global _installed
    global tb_set_next
    if _installed:
        return

    _installed = True
    import platform
    try:
        if platform.python_implementation() == 'CPython':
            tb_set_next = _init_ugly_crap()
    except Exception as exc:
        sys.stderr.write("Failed to initialize cpython support: {!r}".format(exc))

    try:
        from __pypy__ import tproxy
    except ImportError:
        tproxy = None

    if not tb_set_next and not tproxy:
        raise ImportError("Cannot use tblib. Runtime not supported.")
    _import_dump_load()
    install()


def dump_traceback(tb):
    _init()
    return dumps(tb)


def load_traceback(s):
    _init()
    return loads(s)
