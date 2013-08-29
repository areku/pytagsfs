# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from unittest import TestCase

from manager import manager


from pytagsfs.regex import (
  SegmentContainer,
  Regex,
  SimpleExpression,
  Context,
  Group,
  NamedGroup,
)


class SegmentContainerTestCase(TestCase):
    cls = SegmentContainer
    cls_name = 'SegmentContainer'

    def _test_str_unicode_repr(self, which):
        self.assertEqual(which(self.cls()), '%s([])' % self.cls_name)

        segment = SimpleExpression('foo')
        self.assertEqual(
          which(self.cls([segment])),
          '%s([%s])' % (self.cls_name, repr(segment)),
        )

        self.assertEqual(
          which(self.cls([segment, segment])),
          '%s([%s, %s])' % (self.cls_name, repr(segment), repr(segment)),
        )

    def test_str(self):
        return self._test_str_unicode_repr(str)

    def test_unicode(self):
        return self._test_str_unicode_repr(unicode)

    def test_repr(self):
        return self._test_str_unicode_repr(repr)

manager.add_test_case_class(SegmentContainerTestCase)


class RegexTestCase(SegmentContainerTestCase):
    cls = Regex
    cls_name = 'Regex'

    def test_str(self):
        self.assertEqual(str(Regex()), '')
        self.assertEqual(str(Regex([SimpleExpression('foo')])), 'foo')

    def test_unicode(self):
        self.assertEqual(unicode(Regex()), u'')
        self.assertEqual(unicode(Regex([SimpleExpression(u'foo')])), u'foo')

    def test_empty_regex(self):
        regex = Regex()
        self.assertEqual(regex.get_string(), u'')

    def test_append_simple_expression(self):
        regex = Regex()
        regex.append(SimpleExpression('^'))
        regex.append(SimpleExpression('$'))
        self.assertEqual(regex.get_string(), u'^$')

manager.add_test_case_class(RegexTestCase)


class ContextTestCase(TestCase):
    def test_str(self):
        self.assertEqual(str(Context()), '')
        self.assertEqual(str(Context(u'foo')), 'foo')

    def test_unicode(self):
        self.assertEqual(unicode(Context()), u'')
        self.assertEqual(unicode(Context(u'foo')), u'foo')

    def test_repr(self):
        self.assertEqual(repr(Context()), "Context()")
        self.assertEqual(repr(Context(u'foo')), "Context(u'foo')")

    def test_get_named_group_names(self):
        self.assertEqual(
          list(Context(r'(?P<foo>bar)').get_named_group_names()),
          ['foo'],
        )

    def test_get_number_of_groups(self):
        self.assertEqual(
          Context(r'()(?P<foo>bar(baz))\(x\)').get_number_of_groups(),
          3,
        )

manager.add_test_case_class(ContextTestCase)


class SimpleExpressionTestCase(TestCase):
    def test_in_regex(self):
        regex = Regex()
        regex.append(SimpleExpression('foo'))
        self.assertEqual(regex.get_string(), 'foo')

manager.add_test_case_class(SimpleExpressionTestCase)


class GroupTestCase(TestCase):
    def test_in_regex(self):
        regex = Regex()
        regex.append(Group([SimpleExpression('foo')]))
        self.assertEqual(regex.get_string(), '(foo)')

manager.add_test_case_class(GroupTestCase)


class NamedGroupTestCase(TestCase):
    def test_in_regex(self):
        regex = Regex()
        regex.append(NamedGroup('foo', [SimpleExpression('bar')]))
        self.assertEqual(regex.get_string(), '(?P<foo>bar)')

        regex.append(NamedGroup('bink', [SimpleExpression('bonk')]))
        self.assertEqual(regex.get_string(), '(?P<foo>bar)(?P<bink>bonk)')

        regex.append(NamedGroup('foo'))
        self.assertEqual(
          regex.get_string(), '(?P<foo>bar)(?P<bink>bonk)(?P=foo)')

manager.add_test_case_class(NamedGroupTestCase)
