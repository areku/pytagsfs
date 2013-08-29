# coding: utf-8

# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, sys, stat

try:
    from hashlib import md5
except ImportError:
    from md5 import md5

from pytagsfs.metastore import (
  MetaStore,
  DelegateMultiMetaStore,
  UnsettableKeyError,
)
from pytagsfs.values import Values
from pytagsfs.metastore.path import PathMetaStore
from pytagsfs.metastore.mutagen_ import MutagenFileMetaStore
from pytagsfs.subspat import SubstitutionPattern
from pytagsfs.sourcetree import SourceTree
from pytagsfs.sourcetreemon import SourceTreeMonitor
from pytagsfs.sourcetreerep import SourceTreeRepresentation
from pytagsfs.pathstore.pytypes import PyTypesPathStore
from pytagsfs.exceptions import (
  PathNotFound,
  IsADirectory,
  NotADirectory,
  UnrepresentablePath,
)
from pytagsfs.pathpropcache import PathPropCache
from pytagsfs.util import (
  unicode_path_sep,
  split_path,
  join_path,
  join_path_abs,
)

from manager import manager
from common import (
  TEST_DATA_DIR,
  mixin_unicode,
  TestWithDir,
)


class MockSourceTreeMonitor(SourceTreeMonitor):
    pass


class NullMetaStore(MetaStore):
    keys = ()

    def get(self, path):
        return Values()

    def set(self, path, values):
        return []


class ContentMetaStore(MetaStore):
    keys = ('c', 'content')

    def get(self, path):
        values = Values()
        try:
            f = open(path, 'r')
            try:
                values['c'] = values['content'] = [
                  l.rstrip('\n').decode('utf-8') for l in f.readlines()]
            finally:
                f.close()
        except (OSError, IOError):
            pass
        return values

    def set(self, path, values):
        set_keys = []
        for key in self.keys:
            if key in values:
                if key in self.keys:
                    f = open(path, 'w')
                    try:
                        for line in values[key]:
                            f.write(line.encode('utf-8'))
                            f.write('\n')
                    finally:
                        f.close()
                    set_keys.append(key)
        return set_keys


class _BaseSourceTreeRepresentationTestCase(TestWithDir):
    test_dir_prefix = 'str'

    source_tree_rep = None

    def p(self, s):
        return unicode(s)

    def _init(self, meta_store = None, format_string = None, **kwargs):
        kwargs = dict(kwargs)
        if meta_store is not None:
            kwargs['meta_store'] = meta_store
        if format_string is not None:
            substitution_patterns = [
              SubstitutionPattern(s) for s in split_path(format_string)
            ]
            kwargs['substitution_patterns'] = substitution_patterns
        self.source_tree_rep = self._create_source_tree_rep(**kwargs)

    def _create_source_tree_rep(self, **kwargs):
        kwargs = dict(kwargs)

        if 'meta_store' not in kwargs:
            kwargs['meta_store'] = NullMetaStore()
        if 'substitution_patterns' not in kwargs:
            kwargs['substitution_patterns'] = []
        if 'path_store' not in kwargs:
            kwargs['path_store'] = PyTypesPathStore()
        if 'source_tree' not in kwargs:
            kwargs['source_tree'] = SourceTree(self.test_dir)
        if 'monitor' not in kwargs:
            kwargs['monitor'] = MockSourceTreeMonitor()

        meta_store = kwargs.pop('meta_store')
        substitution_patterns = kwargs.pop('substitution_patterns')
        path_store = kwargs.pop('path_store')
        source_tree = kwargs.pop('source_tree')
        monitor = kwargs.pop('monitor')

        args = (meta_store, substitution_patterns, path_store, source_tree, monitor)

        return SourceTreeRepresentation(*args, **kwargs)

    def assertEqualPlusOrMinus(self, first, second, n, msg = None):
        if msg is None:
            msg = '%s and %s are more than %s apart' % (first, second, n)
        difference = abs(first - second)
        if difference > n:
            raise AssertionError(msg)


class _PathPropCacheMixin(object):
    def _create_source_tree_rep(self, **kwargs):
        kwargs = dict(kwargs)
        kwargs['cache'] = PathPropCache()
        return super(_PathPropCacheMixin, self)._create_source_tree_rep(
          **kwargs)


def mixin_pathpropcache(cls):
    newcls = type(
      '%sPathPropCache' % cls.__name__, (_PathPropCacheMixin, cls), {})
    newcls.__module__ = cls.__module__
    return newcls


class SourceTreeRepresentationTestCase(_BaseSourceTreeRepresentationTestCase):
    def test(self):
        self._init(PathMetaStore(), u'/%p/%f')

        dirs = [
          os.path.join(self.test_dir, u'a'),
          os.path.join(self.test_dir, u'•'),
        ]
        files = [
          os.path.join(self.test_dir, u'c'),
          os.path.join(self.test_dir, u'a', u'b'),
          os.path.join(self.test_dir, u'•', u'x'),
        ]

        self._create_dirs(dirs)

        try:
            self._create_files(files)

            try:
                self.source_tree_rep.start()
                try:
                    self.assertEqual(
                      self.source_tree_rep.get_real_path(
                        os.path.join(unicode_path_sep, u'•', u'x')),
                      os.path.join(self.test_dir, u'•', u'x'),
                    )
                    self.assertEqual(
                      self.source_tree_rep.get_fake_paths(
                        os.path.join(self.test_dir, u'•/x')),
                      [os.path.join(unicode_path_sep, u'•', u'x')],
                    )
                    self.assertRaises(
                      PathNotFound,
                      self.source_tree_rep.get_real_path,
                      os.path.join(unicode_path_sep, u'a', u'x'),
                    )

                    # Order of entries is dependent upon the order that files
                    # were read from the source filesystem.  This can vary
                    # depending on the filesystem type, so we use set(...)
                    # to compare irrespective of order.
                    self.assertEqual(
                      set(self.source_tree_rep.get_entries(unicode_path_sep)),
                      set([u'a', u'•', os.path.basename(self.test_dir)]),
                    )
                    self.assertEqual(
                      self.source_tree_rep.get_entries(u'/a'),
                      [u'b'],
                    )
                    self.assertEqual(
                      self.source_tree_rep.get_entries(u'/•'),
                      [u'x'],
                    )
                finally:
                    self.source_tree_rep.stop()

            finally:
                self._remove_files(files)

        finally:
            self._remove_dirs(dirs)

    def test_updates_to_renamed_files_in_a_renamed_directory(self):
        a_content = self.p('boing')
        a_source_path = os.path.join(self.test_dir, u'a', u'b')
        y_source_path = os.path.join(self.test_dir, u'x', u'y')

        meta_store = DelegateMultiMetaStore([
          ContentMetaStore(), PathMetaStore()])

        self._init(meta_store, u'/%p/%c')

        directory_path = os.path.join(self.test_dir, u'a')
        file_path = os.path.join(self.test_dir, u'a', u'b')

        self._create_dir(directory_path)

        try:
            self._create_file(file_path, content = a_content.encode('utf-8'))

            try:
                self.source_tree_rep.start()

                try:
                    self.assertEqual(
                      self.source_tree_rep.get_fake_paths(file_path),
                      [os.path.join(u'/', u'a', a_content)],
                    )

                    new_directory_path = os.path.join(self.test_dir, u'x')
                    os.rename(directory_path, new_directory_path)
                    old_directory_path = directory_path
                    directory_path = new_directory_path

                    file_path = os.path.join(
                      directory_path, os.path.basename(file_path))

                    new_file_path = os.path.join(directory_path, u'y')
                    os.rename(file_path, new_file_path)
                    old_file_path = file_path
                    file_path = new_file_path

                    self.source_tree_rep.remove_cb(
                      old_directory_path, is_dir = True)
                    self.source_tree_rep.add_cb(directory_path, is_dir = True)
                    self.source_tree_rep.remove_cb(
                      old_file_path, is_dir = False)
                    self.source_tree_rep.add_cb(file_path, is_dir = False)
                    self.source_tree_rep.remove_cb(file_path, is_dir = False)
                    self.source_tree_rep.add_cb(file_path, is_dir = False)

                    self.assertEqual(
                      self.source_tree_rep.get_entries(unicode_path_sep),
                      [u'x'],
                    )
                finally:
                    self.source_tree_rep.stop()

            finally:
                self._remove_file(file_path)

        finally:
            self._remove_dir(directory_path)

################################################################################

    def test_stat_fake_directory_with_not_found_file(self):
        dir_path = join_path([self.test_dir, self.p(u'foo')])
        file_path = join_path([dir_path, self.p(u'bar')])
        self._create_dir(dir_path)
        try:
            self._create_file(file_path)
            self._init(PathMetaStore(), u'/%p/%f')
            self.source_tree_rep.start()
            try:
                self._remove_file(file_path)
                self.source_tree_rep.getattr(unicode_path_sep)
            finally:
                self.source_tree_rep.stop()
        finally:
            self._remove_dir(dir_path)

################################################################################

    def test_fill_path(self):
        self._init(NullMetaStore(), u'/%a/%b/%c')
        values = {
          'a': self.p('foo'),
          'b': self.p('bar'),
          'c': self.p('baz'),
        }
        self.assertEqual(
          self.source_tree_rep.fill_path(values),
          join_path_abs([self.p('foo'), self.p('bar'), self.p('baz')]),
        )

    def test_fill_path_with_slash_in_values(self):
        self._init(NullMetaStore(), u'/%a/%b')
        values = {
          'a': join_path([self.p('foo'), self.p('bar')]),
        }
        self.assertRaises(
          UnrepresentablePath,
          self.source_tree_rep.fill_path,
          values,
        )

    def test_fill_path_with_missing_conditional(self):
        self._init(NullMetaStore(), u'/%a/%b/%?%c%:Default%?')
        values = {'a': self.p('foo'), 'b': self.p('bar')}
        self.assertEqual(
          self.source_tree_rep.fill_path(values),
          join_path_abs([self.p('foo'), self.p('bar'), u'Default']),
        )

    def test_populate_with_files_only(self):
        filenames = [self.p('bar'), self.p('baz')]
        file_paths = [
          join_path([self.test_dir, filename])
          for filename in filenames
        ]

        self._create_files(file_paths)

        try:
            self._init(PathMetaStore(), u'/%f')
            self.source_tree_rep.start()
            try:
                # Order of entries is dependent upon the order that files
                # were read from the source filesystem.  This can vary
                # depending on the filesystem type, so we use set(...)
                # to compare irrespective of order.
                self.assertEqual(
                  set(self.source_tree_rep.get_entries(u'/')),
                  set(filenames),
                )
            finally:
                self.source_tree_rep.stop()
        finally:
            self._remove_files(file_paths)

    def test_populate_with_one_subdir(self):
        dirname = join_path([self.test_dir, self.p('foo')])
        filenames = [self.p('bar'), self.p('baz')]
        file_paths = [join_path([dirname, filename]) for filename in filenames]

        self._create_dir(dirname)
        try:
            self._create_files(file_paths)
            try:
                self._init(PathMetaStore(), u'/%f')
                self.source_tree_rep.start()
                try:
                    # Order of entries is dependent upon the order that files
                    # were read from the source filesystem.  This can vary
                    # depending on the filesystem type, so we use set(...)
                    # to compare irrespective of order.
                    self.assertEqual(
                      set(self.source_tree_rep.get_entries(u'/')),
                      set(filenames),
                    )
                finally:
                    self.source_tree_rep.stop()

            finally:
                self._remove_files(file_paths)
        finally:
            self._remove_dir(dirname)

    def test_populate_with_multiple_subdirs(self):
        dirname = join_path([self.test_dir, self.p('foo')])
        bar_dirname = join_path([dirname, self.p('bar')])
        baz_dirname = join_path([dirname, self.p('baz')])

        bar_paths = [
          join_path([bar_dirname, filename])
          for filename in [self.p('klink'), self.p('klank')]
        ]
        baz_paths = [
          join_path([baz_dirname, filename])
          for filename in [self.p('klonk'), self.p('klunk')]
        ]

        self._create_dirs([dirname, bar_dirname, baz_dirname])

        try:
            self._create_files(bar_paths + baz_paths)

            try:
                self._init(PathMetaStore(), u'/%f')
                self.source_tree_rep.start()
                try:
                    # We use set(...) here because we can't make assumptions
                    # about the order in which files are added via populate.
                    # This is dependent upon the source tree filesystem (HPFS+
                    # seems to always return them in alphabetical order, while
                    # ext3 returns them in the order that they were added).
                    self.assertEqual(
                      set(self.source_tree_rep.get_entries(u'/')),
                      set([
                        self.p('klink'),
                        self.p('klank'),
                        self.p('klonk'),
                        self.p('klunk'),
                      ]),
                    )
                finally:
                    self.source_tree_rep.stop()

            finally:
                self._remove_files(bar_paths + baz_paths)

        finally:
            self._remove_dirs([bar_dirname, baz_dirname, dirname])

    def test_file_end_point(self):
        filename = self.p('foo')
        real_path = join_path([self.test_dir, filename])
        self._create_file(real_path)
        try:
            self._init(PathMetaStore(), u'/%f/%f')
            fake_path = join_path_abs([filename, filename])

            self.source_tree_rep.start()
            try:
                self.assertEqual(
                  self.source_tree_rep.get_real_path(fake_path), real_path)
                self.assertEqual(
                  self.source_tree_rep.get_fake_paths(real_path), [fake_path])
                self.assertRaises(
                  NotADirectory, self.source_tree_rep.get_entries, fake_path)
                self.assertTrue(
                  self.source_tree_rep.path_exists(fake_path))
                self.assertTrue(
                  self.source_tree_rep.is_file(fake_path))
                self.assertFalse(
                  self.source_tree_rep.is_dir(fake_path))
                self.assertFalse(
                  self.source_tree_rep.is_empty_dir(fake_path))
            finally:
                self.source_tree_rep.stop()
        finally:
            self._remove_file(real_path)

    def test_directory_mid_point(self):
        filename = self.p('foo')
        real_path = join_path([self.test_dir, filename])
        self._create_file(real_path)
        try:
            self._init(PathMetaStore(), u'/%f/%f')
            fake_path = join_path_abs([filename])

            self.source_tree_rep.start()
            try:
                self.assertRaises(
                  IsADirectory, self.source_tree_rep.get_real_path, fake_path)
                self.assertEqual(
                  self.source_tree_rep.get_entries(fake_path), [filename])
                self.assertTrue(
                  self.source_tree_rep.path_exists(fake_path))
                self.assertFalse(
                  self.source_tree_rep.is_file(fake_path))
                self.assertTrue(
                  self.source_tree_rep.is_dir(fake_path))
                self.assertFalse(
                  self.source_tree_rep.is_empty_dir(fake_path))
            finally:
                self.source_tree_rep.stop()
        finally:
            self._remove_file(real_path)

    def test_directory_end_point(self):
        self._init(PathMetaStore(), u'/%f/%f')
        fake_path = join_path_abs([self.p('foo')])

        self.source_tree_rep.start()
        try:
            self.source_tree_rep.add_directory(fake_path)
            self.assertRaises(
              IsADirectory, self.source_tree_rep.get_real_path, fake_path)
            self.assertEqual(
              self.source_tree_rep.get_entries(fake_path), [])
            self.assertTrue(
              self.source_tree_rep.path_exists(fake_path))
            self.assertFalse(
              self.source_tree_rep.is_file(fake_path))
            self.assertTrue(
              self.source_tree_rep.is_dir(fake_path))
            self.assertTrue(
              self.source_tree_rep.is_empty_dir(fake_path))
        finally:
            self.source_tree_rep.stop()

    def test_non_existent_path(self):
        self._init(PathMetaStore(), u'/%f/%f')
        fake_path = join_path_abs([self.p('foo')])

        self.source_tree_rep.start()
        try:
            self.assertRaises(
              PathNotFound, self.source_tree_rep.get_real_path, fake_path)
            self.assertRaises(
              PathNotFound, self.source_tree_rep.get_entries, fake_path)
            self.assertFalse(
              self.source_tree_rep.path_exists(fake_path))
            self.assertFalse(
              self.source_tree_rep.is_file(fake_path))
            self.assertFalse(
              self.source_tree_rep.is_dir(fake_path))
            self.assertFalse(
              self.source_tree_rep.is_empty_dir(fake_path))
        finally:
            self.source_tree_rep.stop()

    def test_get_fake_path_with_directory(self):
        real_path = join_path([self.test_dir, self.p('foo')])
        self._init(PathMetaStore(), u'/%f/%f')
        self._create_dir(real_path)
        try:
            self.source_tree_rep.start()
            try:
                self.assertRaises(
                  PathNotFound, self.source_tree_rep.get_fake_paths, real_path)
            finally:
                self.source_tree_rep.stop()
        finally:
            self._remove_dir(real_path)

    def test_add_remove_source_dir_with_files_only(self):
        dirname = join_path([self.test_dir, self.p('foo')])
        filenames = [self.p('bar'), self.p('baz')]
        file_paths = [join_path([dirname, filename]) for filename in filenames]

        self._init(PathMetaStore(), u'/%f')
        self.source_tree_rep.start()
        try:
            self._create_dir(dirname)
            self._create_files(file_paths)
            self.source_tree_rep.add_source_dir(dirname)

            # Seems like there is some variability in the order of entries
            # here on different systems.  It must be related to the source
            # filesystem type, even though I would think it would only depend
            # on the order the files are added (above).  It is not critical
            # that the order is what we'd expect, so we use set(...) here
            # to accomodate the variability.
            self.assertEqual(
              set(self.source_tree_rep.get_entries(u'/')),
              set(filenames),
            )

            self._remove_files(file_paths)
            self._remove_dir(dirname)
            self.source_tree_rep.remove_source_dir(dirname)
            self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
        finally:
            self.source_tree_rep.stop()

    def test_add_remove_source_dir_with_subdirs(self):
        dirname = join_path([self.test_dir, self.p('foo')])
        bar_dirname = join_path([dirname, self.p('bar')])
        baz_dirname = join_path([dirname, self.p('baz')])

        bar_paths = [
          join_path([bar_dirname, filename])
          for filename in [self.p('klink'), self.p('klank')]
        ]
        baz_paths = [
          join_path([baz_dirname, filename])
          for filename in [self.p('klonk'), self.p('klunk')]
        ]

        self._init(PathMetaStore(), u'/%f')
        self.source_tree_rep.start()
        try:
            self._create_dirs([dirname, bar_dirname, baz_dirname])
            self._create_files(bar_paths + baz_paths)
            self.source_tree_rep.add_source_dir(dirname)
            # We use set(...) here because we can't make assumptions
            # about the order in which files are added via populate.
            # This is dependent upon the source tree filesystem (HPFS+
            # seems to always return them in alphabetical order, while
            # ext3 returns them in the order that they were added).
            self.assertEqual(
              set(self.source_tree_rep.get_entries(u'/')),
              set([
                self.p('klink'),
                self.p('klank'),
                self.p('klonk'),
                self.p('klunk'),
              ]),
            )
            self._remove_files(bar_paths + baz_paths)
            self._remove_dirs([bar_dirname, baz_dirname, dirname])
            self.source_tree_rep.remove_source_dir(dirname)
            self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
        finally:
            self.source_tree_rep.stop()

    def test_add_remove_source_file(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        self._init(PathMetaStore(), u'/%f')
        self.source_tree_rep.start()
        try:
            self._create_file(file_path)
            self.source_tree_rep.add_source_file(file_path)
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'),
              [self.p('foo')],
            )
            self._remove_file(file_path)
            self.source_tree_rep.remove_source_file(file_path)
            self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
        finally:
            self.source_tree_rep.stop()

    def test_add_source_file_nonexistent(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        self._init(PathMetaStore(), u'/%f')
        self.source_tree_rep.start()
        try:
            self.source_tree_rep.add_source_file(file_path)
            self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
        finally:
            self.source_tree_rep.stop()

    def test_add_source_file_unrepresentable(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        self._init(MutagenFileMetaStore(), u'/%t')
        self.source_tree_rep.start()
        try:
            self._create_file(file_path)
            try:
                self.source_tree_rep.add_source_file(file_path)
                self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
            finally:
                self._remove_file(file_path)
        finally:
            self.source_tree_rep.stop()

    def test_add_source_file_excluded_by_fake_path(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        content = self.p('bar')
        self._init(
          ContentMetaStore(), u'/%c',
          filters = [
            (r'!^/%s$' % content, False),
          ],
        )
        self.source_tree_rep.start()
        try:
            self._create_file(file_path, content)
            try:
                self.source_tree_rep.add_source_file(file_path)
                self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
            finally:
                self._remove_file(file_path)
        finally:
            self.source_tree_rep.stop()

    def test_add_source_file_excluded_by_real_path(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        content = u'bar'
        self._init(
          ContentMetaStore(), u'/%c',
          filters = [
            (self.p(r'!^/%s$' % self.p('foo')), True),
          ],
        )
        self.source_tree_rep.start()
        try:
            self._create_file(file_path, content)
            try:
                self.source_tree_rep.add_source_file(file_path)
                self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
            finally:
                self._remove_file(file_path)
        finally:
            self.source_tree_rep.stop()

    def test_add_remove_source_file_same_real_path_twice(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        self._init(PathMetaStore(), u'/%f')
        self.source_tree_rep.start()
        try:
            self._create_file(file_path)
            try:
                self.source_tree_rep.add_source_file(file_path)
                self.source_tree_rep.add_source_file(file_path)
                self.assertEqual(
                  self.source_tree_rep.get_entries(u'/'),
                  [self.p('foo')],
                )
                self.source_tree_rep.remove_source_file(file_path)
                self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
            finally:
                self._remove_file(file_path)
        finally:
            self.source_tree_rep.stop()

    def test_remove_source_file_nonexistent(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        self._init(PathMetaStore(), u'/%f')
        self.source_tree_rep.start()
        try:
            self.source_tree_rep.remove_source_file(file_path)
            self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
        finally:
            self.source_tree_rep.stop()

    def test_update_source_file_causing_path_rename(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        content = self.p('foo')
        new_content = self.p('bar')

        self._create_file(file_path, content)
        self._init(ContentMetaStore(), u'/%c')
        self.source_tree_rep.start()
        try:
            f = open(file_path, 'w')
            try:
                f.write(new_content.encode('utf-8'))
            finally:
                f.close()
            self.source_tree_rep.update_source_file(file_path)
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'),
              [new_content],
            )
        finally:
            self.source_tree_rep.stop()
            self._remove_file(file_path)

    def test_update_source_file_causing_no_path_rename(self):
        filename = self.p('foo')
        file_path = join_path([self.test_dir, filename])
        content = 'foo'
        new_content = 'bar'

        self._create_file(file_path, content)
        self._init(PathMetaStore(), u'/%f')
        self.source_tree_rep.start()
        try:
            f = open(file_path, 'w')
            try:
                f.write(new_content.encode('utf-8'))
            finally:
                f.close()
            self.source_tree_rep.update_source_file(file_path)
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'),
              [self.p(filename)],
            )
        finally:
            self.source_tree_rep.stop()
            self._remove_file(file_path)

    def test_rename_path_with_file_end_point(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        content_old = self.p('bar\n')
        content_new = self.p('baz\n')
        self._create_file(file_path, content_old)
        self._init(ContentMetaStore(), u'/%c')
        self.source_tree_rep.start()
        try:
            self.source_tree_rep.rename_path(
              join_path_abs([content_old.rstrip(u'\n')]),
              join_path_abs([content_new.rstrip(u'\n')]),
            )
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'),
              [content_old.rstrip(u'\n')],
            )
            self.assertEqual(self._get_file_content(file_path), content_new)
        finally:
            self.source_tree_rep.stop()
            self._remove_file(file_path)

    def test_rename_path_with_empty_directory_end_point(self):
        self._init(ContentMetaStore(), u'/%c/%c')
        self.source_tree_rep.start()
        try:
            self.source_tree_rep.add_directory(join_path_abs([self.p('foo')]))
            self.source_tree_rep.rename_path(
              join_path_abs([self.p('foo')]),
              join_path_abs([self.p('bar')]),
            )
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'), [self.p('bar')])
            self.assertEqual(
              self.source_tree_rep.get_entries(self.p(u'/bar')), [])
        finally:
            self.source_tree_rep.stop()

    def test_rename_path_with_directory_containing_file_end_points(self):
        file_path = join_path([self.test_dir, self.p('foo')])
        content_old = self.p('klink\n')
        content_new = self.p('klank\n')
        self._create_file(file_path, content_old)
        self._init(
          DelegateMultiMetaStore([ContentMetaStore(), PathMetaStore()]),
          u'/%c/%f',
        )
        self.source_tree_rep.start()
        try:
            self.source_tree_rep.rename_path(
              join_path_abs([content_old.rstrip(u'\n')]),
              join_path_abs([content_new.rstrip(u'\n')]),
            )
            self.source_tree_rep.update_source_file(file_path)
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'),
              [content_new.rstrip(u'\n')],
            )
            self.assertEqual(
              self.source_tree_rep.get_entries(join_path_abs([content_new.rstrip(u'\n')])),
              [self.p('foo')],
            )
            self.assertEqual(self._get_file_content(file_path), content_new)
        finally:
            self.source_tree_rep.stop()
            self._remove_file(file_path)

    def test_rename_path_with_nonexistent_path(self):
        self._init(ContentMetaStore(), u'/%c')
        self.source_tree_rep.start()
        try:
            self.assertRaises(
              PathNotFound,
              self.source_tree_rep.rename_path,
              join_path_abs([self.p('foo')]),
              join_path_abs([self.p('bar')]),
            )
        finally:
            self.source_tree_rep.stop()

    def test_rename_path_causing_value_change_on_first_of_two_values(self):
        self._init(ContentMetaStore(), u'/%c')
        file_path = join_path([self.test_dir, self.p('foo')])
        self._create_file(file_path, self.p('bar\nbaz\n'))
        try:
            self.source_tree_rep.start()
            self.source_tree_rep.rename_path(self.p('/bar'), self.p('/qux'))
            self.source_tree_rep.update_source_file(file_path)
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'),
              [self.p('baz'), self.p('qux')],
            )
        finally:
            self._remove_file(file_path)

    def test_rename_path_causing_value_change_on_last_of_two_values(self):
        self._init(ContentMetaStore(), u'/%c')
        file_path = join_path([self.test_dir, self.p('foo')])
        self._create_file(file_path, self.p('bar\nbaz\n'))
        try:
            self.source_tree_rep.start()
            self.source_tree_rep.rename_path(self.p('/baz'), self.p('/qux'))
            self.source_tree_rep.update_source_file(file_path)
            self.assertEqual(
              self.source_tree_rep.get_entries(u'/'),
              [self.p('bar'), self.p('qux')],
            )
        finally:
            self._remove_file(file_path)

    def test_add_remove_directory(self):
        self._init(ContentMetaStore(), u'/%c/%c')
        self.source_tree_rep.start()
        try:
            self.source_tree_rep.add_directory(join_path_abs([self.p('foo')]))
            self.source_tree_rep.remove_directory(join_path_abs([self.p('foo')]))
            self.assertEqual(self.source_tree_rep.get_entries(u'/'), [])
        finally:
            self.source_tree_rep.stop()

    def test_supports_threads(self):
        self._init()
        value = self.source_tree_rep.supports_threads()
        self.assertTrue((value is True) or (value is False))

    def test_can_handle_fork(self):
        self._init()
        value = self.source_tree_rep.can_handle_fork()
        self.assertTrue((value is True) or (value is False))

    def _assert_lstat_getattr_attrs_are_equal(
      self, attr, lstat_result, getattr_result):
        lstat_value = getattr(lstat_result, attr)
        getattr_value = getattr(getattr_result, attr)
        self.assertEqual(
          lstat_value,
          getattr_value,
          '%s is not equal: %s != %s' % (
            attr, lstat_value, getattr_value),
        )

    def _assert_lstat_getattr_attrs_are_equal_plus_or_minus(
      self, attr, lstat_result, getattr_result, n):
        lstat_value = getattr(lstat_result, attr)
        getattr_value = getattr(getattr_result, attr)
        self.assertEqualPlusOrMinus(
          lstat_value,
          getattr_value,
          n,
          '%s: %s and %s are more than %s apart' % (
            attr, lstat_value, getattr_value, n),
        )

    def test_getattr_with_file_end_point(self):
        filename = self.p('foo')
        real_path = join_path([self.test_dir, filename])
        self._create_file(real_path)

        try:
            self._init(PathMetaStore(), u'/%f/%f')
            fake_path = join_path_abs([filename, filename])

            self.source_tree_rep.start()
            try:
                lstat_result = os.lstat(real_path)
                getattr_result = self.source_tree_rep.getattr(fake_path)

                self.assertTrue(isinstance(getattr_result, os.stat_result))
                self.assertTrue(stat.S_ISREG(getattr_result.st_mode))

                self.assertEqual(
                  stat.S_IMODE(lstat_result.st_mode),
                  stat.S_IMODE(getattr_result.st_mode),
                )
                
                for attr in ('st_nlink', 'st_uid', 'st_gid', 'st_size'):
                    self._assert_lstat_getattr_attrs_are_equal(
                      attr, lstat_result, getattr_result)

                for attr in ('st_atime', 'st_mtime', 'st_ctime'):
                    self._assert_lstat_getattr_attrs_are_equal_plus_or_minus(
                      attr, lstat_result, getattr_result, 2)
            finally:
                self.source_tree_rep.stop()

        finally:
            self._remove_file(real_path)

    def test_getattr_with_directory_end_point(self):
        self._init(PathMetaStore(), u'/%f/%f')
        fake_path = join_path_abs([self.p('foo')])

        self.source_tree_rep.start()
        try:
            self.source_tree_rep.add_directory(fake_path)
            lstat_result = os.lstat(self.test_dir)
            getattr_result = self.source_tree_rep.getattr(fake_path)

            self.assertTrue(isinstance(getattr_result, os.stat_result))
            self.assertEqual(getattr_result.st_size, 0)
            # Empty directories have two links.
            self.assertEqual(getattr_result.st_nlink, 2)
            self.assertTrue(stat.S_ISDIR(getattr_result.st_mode))

            self.assertEqual(
              stat.S_IMODE(lstat_result.st_mode),
              stat.S_IMODE(getattr_result.st_mode),
            )
            
            for attr in ('st_uid', 'st_gid'):
                self._assert_lstat_getattr_attrs_are_equal(
                  attr, lstat_result, getattr_result)
            
            for attr in ('st_atime', 'st_mtime', 'st_ctime'):
                self._assert_lstat_getattr_attrs_are_equal_plus_or_minus(
                  attr, lstat_result, getattr_result, 2)
        finally:
            self.source_tree_rep.stop()

    def test_getattr_with_directory_mid_point(self):
        filename = self.p('foo')
        real_path = join_path([self.test_dir, filename])
        self._create_file(real_path)

        try:
            self._init(PathMetaStore(), u'/%f/%f')
            fake_path = join_path_abs([self.p('foo')])
            fake_path_parent = os.path.dirname(fake_path)

            self.source_tree_rep.start()
            try:
                for test_path in (fake_path_parent, fake_path):
                    dir_lstat_result = os.lstat(self.test_dir)
                    file_lstat_result = os.lstat(real_path)
                    getattr_result = self.source_tree_rep.getattr(test_path)

                    self.assertTrue(isinstance(getattr_result, os.stat_result))
                    self.assertEqual(getattr_result.st_size, 0)

                    if test_path == fake_path:
                        # A directory containing one file has two links.
                        self.assertEqual(getattr_result.st_nlink, 2)
                    else:
                        # A directory containing one subdirectory has three links.
                        self.assertEqual(getattr_result.st_nlink, 3)

                    self.assertTrue(stat.S_ISDIR(getattr_result.st_mode))
                    self.assertEqual(
                      stat.S_IMODE(dir_lstat_result.st_mode),
                      stat.S_IMODE(getattr_result.st_mode),
                    )
                    
                    # Ownership should be the same as the source directory.
                    for attr in ('st_uid', 'st_gid'):
                        self._assert_lstat_getattr_attrs_are_equal(
                          attr, dir_lstat_result, getattr_result)
                    
                    # Times should be the same as the contained file.
                    for attr in ('st_atime', 'st_mtime', 'st_ctime'):
                        self._assert_lstat_getattr_attrs_are_equal_plus_or_minus(
                          attr, file_lstat_result, getattr_result, 2)
            finally:
                self.source_tree_rep.stop()

        finally:
            self._remove_file(real_path)

    def test_getattr_with_non_existent_path(self):
        self._init(PathMetaStore(), u'/%f/%f')
        fake_path = join_path_abs([self.p('foo')])
        self.source_tree_rep.start()
        try:
            self.assertRaises(
              PathNotFound, self.source_tree_rep.getattr, fake_path)
        finally:
            self.source_tree_rep.stop()

    def test_utime_with_file_end_point(self):
        filename = self.p('foo')
        real_path = join_path([self.test_dir, filename])
        self._create_file(real_path)

        self._init(PathMetaStore(), u'/%f/%f')
        fake_path = join_path_abs([filename, filename])

        self.source_tree_rep.start()
        try:
            times = (1, 2)
            self.source_tree_rep.utime(fake_path, times)
            lstat_result = os.lstat(real_path)
            self.assertEqual(lstat_result.st_atime, times[0])
            self.assertEqual(lstat_result.st_mtime, times[1])
        finally:
            self.source_tree_rep.stop()
        self._remove_file(real_path)

    def test_utime_with_directory_end_point(self):
        self._init(PathMetaStore(), u'/%f/%f')
        fake_path = join_path_abs([self.p('foo')])

        self.source_tree_rep.start()
        try:
            self.source_tree_rep.add_directory(fake_path)
            times = (1, 2)
            self.source_tree_rep.utime(fake_path, times)
            lstat_result = os.lstat(self.test_dir)
            self.assertEqual(lstat_result.st_atime, times[0])
            self.assertEqual(lstat_result.st_mtime, times[1])
        finally:
            self.source_tree_rep.stop()

    def test_utime_with_directory_mid_point(self):
        filename = self.p('foo')
        real_path = join_path([self.test_dir, filename])
        self._create_file(real_path)

        try:
            self._init(PathMetaStore(), u'/%f/%f')
            fake_path = join_path_abs([self.p('foo')])

            self.source_tree_rep.start()
            try:
                times = (1, 2)
                self.source_tree_rep.utime(fake_path, times)
                lstat_result = os.lstat(real_path)
                self.assertEqual(lstat_result.st_atime, times[0])
                self.assertEqual(lstat_result.st_mtime, times[1])
            finally:
                self.source_tree_rep.stop()

        finally:
            self._remove_file(real_path)

    def test_utime_with_non_existent_path(self):
        self._init(PathMetaStore(), u'/%f/%f')
        fake_path = join_path_abs([self.p('foo')])
        self.source_tree_rep.start()
        try:
            self.assertRaises(
              PathNotFound, self.source_tree_rep.utime, fake_path, (1, 2))
        finally:
            self.source_tree_rep.stop()

    def test_path_conflict_then_remove_first(self):
        self._init(PathMetaStore(), u'/%f')
        filename = self.p('foo')

        real_path1 = join_path([self.test_dir, self.p('bar'), filename])
        real_path2 = join_path([self.test_dir, self.p('baz'), filename])

        files = (real_path1, real_path2)
        dirs = [os.path.dirname(p) for p in files]

        fake_path = join_path_abs([filename])
        self.source_tree_rep.start()
        try:
            self._create_dirs(dirs)
            try:
                self._create_files(files)
                self.source_tree_rep.add_source_file(real_path1)
                self.source_tree_rep.add_source_file(real_path2)

                self._remove_file(real_path1)
                self.source_tree_rep.remove_source_file(real_path1)

                self.assertEqual(
                  self.source_tree_rep.get_real_path(fake_path),
                  real_path2,
                )

                self._remove_file(real_path2)
                self.source_tree_rep.remove_source_file(real_path2)
                self.assertRaises(
                  PathNotFound,
                  self.source_tree_rep.get_real_path,
                  fake_path,
                )
            finally:
                self._remove_dirs(dirs)
        finally:
            self.source_tree_rep.stop()

    def test_path_conflict_then_remove_second(self):
        self._init(PathMetaStore(), u'/%f')
        filename = self.p('foo')

        real_path1 = join_path([self.test_dir, self.p('bar'), filename])
        real_path2 = join_path([self.test_dir, self.p('baz'), filename])

        files = (real_path1, real_path2)
        dirs = [os.path.dirname(p) for p in files]

        fake_path = join_path_abs([filename])
        self.source_tree_rep.start()
        try:
            self._create_dirs(dirs)
            try:
                self._create_files(files)
                self.source_tree_rep.add_source_file(real_path1)
                self.source_tree_rep.add_source_file(real_path2)

                self._remove_file(real_path2)
                self.source_tree_rep.remove_source_file(real_path2)

                self.assertEqual(
                  self.source_tree_rep.get_real_path(fake_path),
                  real_path1,
                )

                self._remove_file(real_path1)
                self.source_tree_rep.remove_source_file(real_path1)
                self.assertRaises(
                  PathNotFound,
                  self.source_tree_rep.get_real_path,
                  fake_path,
                )
            finally:
                self._remove_dirs(dirs)
        finally:
            self.source_tree_rep.stop()

    def test_real_path_with_multiple_tag_values(self):
        real_path = join_path([self.test_dir, self.p('foo')])
        content = self.p('bar\nbaz\nqux\n')
        fake_path1 = join_path_abs([self.p('bar')])
        fake_path2 = join_path_abs([self.p('baz')])
        fake_path3 = join_path_abs([self.p('qux')])
        self._create_file(real_path, content)
        try:
            self._init(ContentMetaStore(), u'/%c')
            self.source_tree_rep.start()
            try:
                self.assertEqual(
                  self.source_tree_rep.get_real_path(fake_path1), real_path)
                self.assertEqual(
                  self.source_tree_rep.get_real_path(fake_path2), real_path)
                self.assertEqual(
                  self.source_tree_rep.get_real_path(fake_path3), real_path)
                self.assertEqual(
                  self.source_tree_rep.get_fake_paths(
                    real_path), [fake_path1, fake_path2, fake_path3])
            finally:
                self.source_tree_rep.stop()
        finally:
            self._remove_file(real_path)

manager.add_test_case_class(SourceTreeRepresentationTestCase)
manager.add_test_case_class(mixin_unicode(SourceTreeRepresentationTestCase))
manager.add_test_case_class(
  mixin_pathpropcache(SourceTreeRepresentationTestCase))
manager.add_test_case_class(
  mixin_unicode(mixin_pathpropcache(SourceTreeRepresentationTestCase)))


manager.add_doc_test_cases_from_module(__name__, 'pytagsfs.sourcetree')
