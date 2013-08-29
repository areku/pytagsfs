# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from unittest import TestCase

from pytagsfs.subspat import SubstitutionPattern

from manager import manager


class SubstitutionPatternTestMixin(object):
    pattern_cls = SubstitutionPattern

    def setUp(self):
        self.pattern = self.pattern_cls(self.pattern_string)

    def tearDown(self):
        del self.pattern

    def test_split(self):
        splitter = self.pattern.get_splitter(self.substitution_pattern_mapping)
        self.assertEqual(
          splitter.split(self.substitution_pattern_filled_string),
          self.substitution_pattern_mapping,
        )

    def test_fill(self):
        self.assertEqual(
          self.pattern.fill(self.substitution_pattern_mapping),
          self.substitution_pattern_filled_string,
        )


class ShortKeySubstitutionPatternTestCase(
  SubstitutionPatternTestMixin,
  TestCase,
):
    pattern_string = '%a %b %c'
    substitution_pattern_mapping = {'a': 'foo', 'b': 'bar', 'c': 'baz'}
    substitution_pattern_filled_string = 'foo bar baz'

manager.add_test_case_class(ShortKeySubstitutionPatternTestCase)


class LongKeySubstitutionPatternTestCase(
  SubstitutionPatternTestMixin,
  TestCase,
):
    pattern_string = '%{aye} %{bee} %{see}'
    substitution_pattern_mapping = {'aye': 'foo', 'bee': 'bar', 'see': 'baz'}
    substitution_pattern_filled_string = 'foo bar baz'

manager.add_test_case_class(LongKeySubstitutionPatternTestCase)


class MixedKeySubstitutionPatternTestCase(
  SubstitutionPatternTestMixin,
  TestCase,
):
    pattern_string = '%a %{bee} %c %{dee}'
    substitution_pattern_mapping = {
      'a': 'foo', 'bee': 'bar', 'c': 'baz', 'dee': 'boink'}
    substitution_pattern_filled_string = 'foo bar baz boink'

manager.add_test_case_class(MixedKeySubstitutionPatternTestCase)


class ConditionalSubstitutionPatternTestMixin(object):
    def test_conditional_split_true(self):
        splitter = self.pattern.get_splitter(
          self.conditional_pattern_mapping_true)
        self.assertEqual(
          splitter.split(self.conditional_pattern_filled_string_true),
          self.conditional_pattern_mapping_true,
        )

    def test_conditional_split_false(self):
        splitter = self.pattern.get_splitter(
          self.conditional_pattern_mapping_false)
        self.assertEqual(
          splitter.split(self.conditional_pattern_filled_string_false),
          self.conditional_pattern_mapping_false,
        )

    def test_conditional_fill_true(self):
        self.assertEqual(
          self.pattern.fill(self.conditional_pattern_mapping_true),
          self.conditional_pattern_filled_string_true,
        )

    def test_conditional_fill_false(self):
        self.assertEqual(
          self.pattern.fill(self.conditional_pattern_mapping_false),
          self.conditional_pattern_filled_string_false,
        )


class ShortKeyConditionalSubstitutionPatternTestCase(
  ConditionalSubstitutionPatternTestMixin,
  ShortKeySubstitutionPatternTestCase,
):
    pattern_string = '%a %b%? %c%?'
    conditional_pattern_mapping_true = {'a': 'foo', 'b': 'bar', 'c': 'baz'}
    conditional_pattern_mapping_false = {'a': 'foo', 'b': 'bar', 'c': None}
    conditional_pattern_filled_string_true = 'foo bar baz'
    conditional_pattern_filled_string_false = 'foo bar'

manager.add_test_case_class(ShortKeyConditionalSubstitutionPatternTestCase)


class LongKeyConditionalSubstitutionPatternTestCase(
  ConditionalSubstitutionPatternTestMixin,
  LongKeySubstitutionPatternTestCase,
):
    pattern_string = '%{aye} %{bee}%? %{see}%?'
    conditional_pattern_mapping_true = {
      'aye': 'foo', 'bee': 'bar', 'see': 'baz'}
    conditional_pattern_mapping_false = {
      'aye': 'foo', 'bee': 'bar', 'see': None}
    conditional_pattern_filled_string_true = 'foo bar baz'
    conditional_pattern_filled_string_false = 'foo bar'

manager.add_test_case_class(LongKeyConditionalSubstitutionPatternTestCase)


class MixedKeyConditionalSubstitutionPatternTestCase(
  ConditionalSubstitutionPatternTestMixin,
  MixedKeySubstitutionPatternTestCase,
):
    pattern_string = '%a %{bee} %c%? %{dee}%?'
    conditional_pattern_mapping_true = {
      'a': 'foo', 'bee': 'bar', 'c': 'baz', 'dee': 'boink'}
    conditional_pattern_mapping_false = {
      'a': 'foo', 'bee': 'bar', 'c': 'baz', 'dee': None}
    conditional_pattern_filled_string_true = 'foo bar baz boink'
    conditional_pattern_filled_string_false = 'foo bar baz'

manager.add_test_case_class(MixedKeyConditionalSubstitutionPatternTestCase)


class ShortKeyIfElseSubstitutionPatternTestCase(
  ShortKeyConditionalSubstitutionPatternTestCase,
):
    pattern_string = '%a %b %?%c%:Unknown%?'
    conditional_pattern_filled_string_false = 'foo bar Unknown'

manager.add_test_case_class(ShortKeyIfElseSubstitutionPatternTestCase)


class ShortKeyIfElseSubstitutionPatternWithDynamicElsePartTestCase(
  ShortKeyConditionalSubstitutionPatternTestCase,
):
    pattern_string = '%a %b %?%c%:%a%?'
    conditional_pattern_filled_string_false = 'foo bar foo'
    conditional_pattern_mapping_false = {'a': 'foo', 'b': 'bar', 'c': 'foo'}

manager.add_test_case_class(
  ShortKeyIfElseSubstitutionPatternWithDynamicElsePartTestCase)


class LongKeyIfElseSubstitutionPatternTestCase(
  LongKeyConditionalSubstitutionPatternTestCase,
):
    pattern_string = '%{aye} %{bee} %?%{see}%:Unknown%?'
    conditional_pattern_filled_string_false = 'foo bar Unknown'

manager.add_test_case_class(LongKeyIfElseSubstitutionPatternTestCase)


class LongKeyIfElseSubstitutionPatternWithDynamicElsePartTestCase(
  LongKeyConditionalSubstitutionPatternTestCase,
):
    pattern_string = '%{aye} %{bee} %?%{see}%:%{aye}%?'
    conditional_pattern_filled_string_false = 'foo bar foo'
    conditional_pattern_mapping_false = {
      'aye': 'foo', 'bee': 'bar', 'see': 'foo'}

manager.add_test_case_class(
  LongKeyIfElseSubstitutionPatternWithDynamicElsePartTestCase)


class MixedKeyIfElseSubstitutionPatternTestCase(
  MixedKeyConditionalSubstitutionPatternTestCase,
):
    pattern_string = '%a %{bee} %c %?%{dee}%:Unknown%?'
    conditional_pattern_filled_string_false = 'foo bar baz Unknown'

manager.add_test_case_class(MixedKeyIfElseSubstitutionPatternTestCase)


class MixedKeyIfElseSubstitutionPatternWithDynamicElsePartTestCase(
  MixedKeyConditionalSubstitutionPatternTestCase,
):
    pattern_string = '%a %{bee} %c %?%{dee}%:%a%?'
    conditional_pattern_filled_string_false = 'foo bar baz foo'
    conditional_pattern_mapping_false = {
      'a': 'foo', 'bee': 'bar', 'c': 'baz', 'dee': 'foo'}

manager.add_test_case_class(
  MixedKeyIfElseSubstitutionPatternWithDynamicElsePartTestCase)


class ModifiedSubstitutionPatternTestMixin(object):
    def test_modified_fill_lower_case_input(self):
        mapping_lower = {}
        for k, v in self.substitution_pattern_mapping.items():
            mapping_lower[k] = v.lower()

        self.assertEqual(
          self.pattern.fill(mapping_lower),
          self.substitution_pattern_filled_string,
        )

    def test_modified_fill_upper_case_input(self):
        mapping_upper = {}
        for k, v in self.substitution_pattern_mapping.items():
            mapping_upper[k] = v.upper()

        self.assertEqual(
          self.pattern.fill(mapping_upper),
          self.substitution_pattern_filled_string,
        )

    def test_modified_fill_title_case_input(self):
        mapping_title = {}
        for k, v in self.substitution_pattern_mapping.items():
            mapping_title[k] = v.title()

        self.assertEqual(
          self.pattern.fill(mapping_title),
          self.substitution_pattern_filled_string,
        )

    def test_modified_fill_changes_case_none(self):
        p = self.pattern_cls('%%%s' % self.modified_fill_test_expr)
        self.assertEqual(p.fill({self.modified_fill_test_key: 'foo'}), 'foo')

    def test_modified_fill_changes_case_upper(self):
        p = self.pattern_cls('%%^%s' % self.modified_fill_test_expr)
        self.assertEqual(p.fill({self.modified_fill_test_key: 'foo'}), 'FOO')

    def test_modified_fill_changes_case_lower(self):
        p = self.pattern_cls('%%_%s' % self.modified_fill_test_expr)
        self.assertEqual(p.fill({self.modified_fill_test_key: 'FOO'}), 'foo')

    def test_modified_fill_changes_case_title(self):
        p = self.pattern_cls('%%!%s' % self.modified_fill_test_expr)
        self.assertEqual(p.fill({self.modified_fill_test_key: 'fOo'}), 'Foo')


class ShortKeyModifiedSubstitutionPatternTestCase(
  ModifiedSubstitutionPatternTestMixin,
  ShortKeySubstitutionPatternTestCase,
):
    pattern_string = '%^a %_b %!c'
    substitution_pattern_mapping = {'a': 'FOO', 'b': 'bar', 'c': 'Baz'}
    substitution_pattern_filled_string = 'FOO bar Baz'
    modified_fill_test_key = 'a'
    modified_fill_test_expr = modified_fill_test_key

manager.add_test_case_class(ShortKeyModifiedSubstitutionPatternTestCase)


class LongKeyModifiedSubstitutionPatternTestCase(
  ModifiedSubstitutionPatternTestMixin,
  LongKeySubstitutionPatternTestCase,
):
    pattern_string = '%^{aye} %_{bee} %!{see}'
    substitution_pattern_mapping = {'aye': 'FOO', 'bee': 'bar', 'see': 'Baz'}
    substitution_pattern_filled_string = 'FOO bar Baz'
    modified_fill_test_key = 'aye'
    modified_fill_test_expr = '{%s}' % modified_fill_test_key

manager.add_test_case_class(LongKeyModifiedSubstitutionPatternTestCase)


class MixedKeyModifiedSubstitutionPatternTestCase(
  ModifiedSubstitutionPatternTestMixin,
  MixedKeySubstitutionPatternTestCase,
):
    pattern_string = '%^a %_{bee} %!c %_{dee}'
    substitution_pattern_mapping = {
      'a': 'FOO', 'bee': 'bar', 'c': 'Baz', 'dee': 'boink'}
    substitution_pattern_filled_string = 'FOO bar Baz boink'
    modified_fill_test_key = 'aye'
    modified_fill_test_expr = '{%s}' % modified_fill_test_key

manager.add_test_case_class(MixedKeyModifiedSubstitutionPatternTestCase)


class ShortKeyModifedIfElseSubstitutionPatternTestCase(
  ShortKeyModifiedSubstitutionPatternTestCase,
  ShortKeyIfElseSubstitutionPatternTestCase,
):
    pattern_string = '%^a %_b %?%!c%:Unknown%?'
    conditional_pattern_mapping_true = {'a': 'FOO', 'b': 'bar', 'c': 'Baz'}
    conditional_pattern_mapping_false = {'a': 'FOO', 'b': 'bar', 'c': None}
    conditional_pattern_filled_string_true = 'FOO bar Baz'
    conditional_pattern_filled_string_false = 'FOO bar Unknown'

manager.add_test_case_class(ShortKeyModifedIfElseSubstitutionPatternTestCase)


class LongKeyModifedIfElseSubstitutionPatternTestCase(
  LongKeyModifiedSubstitutionPatternTestCase,
  LongKeyIfElseSubstitutionPatternTestCase,
):
    pattern_string = '%^{aye} %_{bee} %?%!{see}%:Unknown%?'
    conditional_pattern_mapping_true = {
      'aye': 'FOO', 'bee': 'bar', 'see': 'Baz'}
    conditional_pattern_mapping_false = {
      'aye': 'FOO', 'bee': 'bar', 'see': None}
    conditional_pattern_filled_string_true = 'FOO bar Baz'
    conditional_pattern_filled_string_false = 'FOO bar Unknown'

manager.add_test_case_class(LongKeyModifedIfElseSubstitutionPatternTestCase)


class MixedKeyModifedIfElseSubstitutionPatternTestCase(
  MixedKeyModifiedSubstitutionPatternTestCase,
  MixedKeyIfElseSubstitutionPatternTestCase,
):
    pattern_string = '%^a %_{bee} %!c %?%_{dee}%:Unknown%?'
    conditional_pattern_mapping_true = {
      'a': 'FOO', 'bee': 'bar', 'c': 'Baz', 'dee': 'boink'}
    conditional_pattern_mapping_false = {
      'a': 'FOO', 'bee': 'bar', 'c': 'Baz', 'dee': None}
    conditional_pattern_filled_string_true = 'FOO bar Baz boink'
    conditional_pattern_filled_string_false = 'FOO bar Baz Unknown'

manager.add_test_case_class(MixedKeyModifedIfElseSubstitutionPatternTestCase)
