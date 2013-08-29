# Copyright (c) 2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from unittest import TestCase

from pytagsfs.values import Values

from manager import manager


class TestValues(TestCase):
    def test_diff2_with_value_removal(self):
        old = Values({'a': [u'foo'], 'b': [u'baz']})
        new = Values({'b': [u'baz']})
        self.assertEqual(Values.diff2(old, new), Values({'a': []}))

    def test_diff3_with_partial_value_removal(self):
        base = Values({'a': [u'foo', u'bar'], 'b': [u'baz'], 'd': [u'qux']})
        old = Values({'a': [u'foo'], 'b': [u'baz']})
        new = Values({'b': [u'baz']})
        self.assertEqual(Values.diff3(base, old, new), Values({'a': [u'bar']}))

    def test_diff2_with_value_change(self):
        old = Values({'a': [u'foo'], 'b': [u'baz']})
        new = Values({'a': [u'boink'], 'b': [u'baz']})
        self.assertEqual(Values.diff2(old, new), Values({'a': [u'boink']}))

    def test_diff3_with_partial_value_change(self):
        base = Values({'a': [u'foo', u'bar'], 'b': [u'baz'], 'd': [u'qux']})
        old = Values({'a': [u'foo'], 'b': [u'baz']})
        new = Values({'a': [u'boink'], 'b': [u'baz']})
        self.assertEqual(
          Values.diff3(base, old, new),
          Values({'a': [u'bar', u'boink']}),
        )

    def test_combine(self):
        a = Values({'a': [u'foo'], 'b': [u'baz', u'bar']})
        b = Values({'b': [u'qux', u'bar', u'quxx']})
        self.assertEqual(
          Values.combine([a, b]),
          Values({'a': [u'foo'], 'b': [u'baz', u'bar', u'qux', u'quxx']}),
        )

manager.add_test_case_class(TestValues)
