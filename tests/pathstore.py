# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

from unittest import TestCase

from pytagsfs.exceptions import (
  PathNotFound,
  NotADirectory,
  IsADirectory,
  PathExists,
  NoMetaDataExists,
  NotAnEndPoint,
)

from common import _UnicodePathsMixin
from manager import manager


# Note: We don't actually run any tests in this module.  We only define a base
# class for specific implementations to sub-class test cases from.

class _PathStoreTestCase(TestCase):
    path_store_class = None

    def p(self, s):
        if not isinstance(s, unicode):
            s = unicode(s)
        return s

    def test_add_file_end_point_flat(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        self.assertEqual(store.get_real_path(self.p('/foo')), self.p('/bar'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('foo')])

    def test_add_file_end_point_deep(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar/baz'), self.p('/klink/klank'))
        self.assertEqual(store.get_real_path(self.p('/foo/bar/baz')), self.p('/klink/klank'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('foo')])
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('bar')])
        self.assertEqual(store.get_entries(self.p('/foo/bar')), [self.p('baz')])

    def test_add_directory_end_point_flat(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('foo')])
        self.assertEqual(store.get_entries(self.p('/foo')), [])

    def test_add_directory_end_point_deep(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo/bar/baz'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('foo')])
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('bar')])
        self.assertEqual(store.get_entries(self.p('/foo/bar')), [self.p('baz')])
        self.assertEqual(store.get_entries(self.p('/foo/bar/baz')), [])

    def test_add_file_with_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertRaises(PathExists, store.add_file, self.p('/foo'), self.p('/bar'))

    def test_add_directory_with_file_end_point(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        self.assertRaises(PathExists, store.add_directory, self.p('/foo'))

    def test_add_directory_with_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertRaises(PathExists, store.add_directory, self.p('/foo'))

    def test_get_real_path_with_non_existent_fake_path(self):
        store = self.path_store_class()
        self.assertRaises(PathNotFound, store.get_real_path, self.p('/foo'))

    def test_get_fake_paths_with_non_existent_real_path(self):
        store = self.path_store_class()
        self.assertRaises(PathNotFound, store.get_fake_paths, self.p('/foo'))

    def test_get_entries_with_non_existent_fake_path(self):
        store = self.path_store_class()
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))

    def test_get_real_path_with_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertRaises(IsADirectory, store.get_real_path, self.p('/foo'))

    def test_remove_file_end_point_flat(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        store.remove(self.p('/foo'))
        self.assertRaises(PathNotFound, store.get_real_path, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [])

    def test_remove_file_end_point_deep(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar/baz'), self.p('/klink/bonk'))
        store.remove(self.p('/foo/bar/baz'))
        self.assertRaises(PathNotFound, store.get_real_path, self.p('/foo/bar/baz'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [])

    def test_remove_directory_end_point_flat(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        store.remove(self.p('/foo'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [])

    def test_remove_directory_end_point_deep(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo/bar/baz'))
        store.remove(self.p('/foo/bar/baz'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo/bar/baz'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [])

    def test_rename_file_end_point_flat_to_flat(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        store.rename(self.p('/foo'), self.p('/baz'))
        self.assertEqual(store.get_real_path(self.p('/baz')), self.p('/bar'))
        self.assertRaises(PathNotFound, store.get_real_path, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('baz')])

    def test_rename_file_end_point_deep_to_deep(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar/baz'), self.p('/bink/bonk'))
        store.rename(self.p('/foo/bar/baz'), self.p('/klink/klank/klonk'))
        self.assertEqual(
          store.get_real_path(self.p('/klink/klank/klonk')), self.p('/bink/bonk'))
        self.assertRaises(PathNotFound, store.get_real_path, self.p('/foo/bar/baz'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('klink')])
        self.assertEqual(store.get_entries(self.p('/klink')), [self.p('klank')])
        self.assertEqual(store.get_entries(self.p('/klink/klank')), [self.p('klonk')])

    def test_rename_file_end_point_flat_to_deep(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bink/bonk'))
        store.rename(self.p('/foo'), self.p('/klink/klank/klonk'))
        self.assertEqual(
          store.get_real_path(self.p('/klink/klank/klonk')), self.p('/bink/bonk'))
        self.assertRaises(PathNotFound, store.get_real_path, self.p('/foo/bar/baz'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('klink')])
        self.assertEqual(store.get_entries(self.p('/klink')), [self.p('klank')])
        self.assertEqual(store.get_entries(self.p('/klink/klank')), [self.p('klonk')])

    def test_rename_file_end_point_deep_to_flat(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar/baz'), self.p('/klank/klonk'))
        store.rename(self.p('/foo/bar/baz'), self.p('/klink'))
        self.assertEqual(store.get_real_path(self.p('/klink')), self.p('/klank/klonk'))
        self.assertRaises(PathNotFound, store.get_real_path, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('klink')])

    def test_rename_directory_end_point_within_root(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        store.rename(self.p('/foo'), self.p('/bar'))
        self.assertEqual(store.get_entries(self.p('/bar')), [])
        self.assertEqual(store.get_entries(self.p('/')), [self.p('bar')])
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))

    def test_rename_directory_end_point_within_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        store.add_directory(self.p('/foo/bar'))
        store.rename(self.p('/foo/bar'), self.p('/foo/baz'))
        self.assertEqual(store.get_entries(self.p('/foo/baz')), [])
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('baz')])
        self.assertEqual(store.get_entries(self.p('/')), [self.p('foo')])
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo/bar'))

    def test_rename_directory_containing_file_end_point(self):
        # Only end-points can be renamed.
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar/baz'), self.p('/klink/klank'))
        self.assertRaises(
          NotAnEndPoint, store.rename, self.p('/foo/bar'), self.p('/foo/klonk'))

    def test_rename_directory_containing_directory_end_point(self):
        # Only end-points can be renamed.
        store = self.path_store_class()
        store.add_directory(self.p('/foo/bar/baz'))
        self.assertRaises(
          NotAnEndPoint, store.rename, self.p('/foo/bar'), self.p('/foo/klink'))

    def test_rename_directory_containing_non_empty_directory(self):
        # Only end-points can be renamed.
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar/baz'), self.p('/klink/klank'))
        self.assertRaises(
          NotAnEndPoint, store.rename, self.p('/foo'), self.p('/klonk'))

    def test_add_file_with_file_end_point(self):
        # This creates a simple path collision.
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar'), self.p('/klink/klank'))
        store.add_file(self.p('/foo/bar'), self.p('/biz/baz'))
        self.assertEqual(store.get_real_path(self.p('/foo/bar')), self.p('/biz/baz'))
        store.remove(self.p('/foo/bar'))
        self.assertEqual(store.get_real_path(self.p('/foo/bar')), self.p('/klink/klank'))

    def test_order_of_entries_matches_order_added(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar'), self.p('/klink/klank'))
        store.add_file(self.p('/foo/baz'), self.p('/klink/klonk'))
        store.add_file(self.p('/foo/qux'), self.p('/klink/klonk'))
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('bar'), self.p('baz'), self.p('qux')])

    def test_order_of_entries_with_collision(self):
        # Order of entries must still match the order added, even after a
        # collision has been created and subsequently resolved.
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar'), self.p('/klink/klank'))
        store.add_file(self.p('/foo/qux'), self.p('/klink/klonk'))
        store.add_file(self.p('/foo/bar'), self.p('/klink/klunk'))
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('qux'), self.p('bar')])
        store.remove(self.p('/foo/bar'))
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('bar'), self.p('qux')])

    def test_order_of_entries_with_rename(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar'), self.p('/klink/klank'))
        store.add_file(self.p('/biz/baz'), self.p('/klink/boink'))
        store.add_file(self.p('/foo/qux'), self.p('/klink/klonk'))
        store.add_file(self.p('/foo/clunk'), self.p('/klink/klunk'))
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('bar'), self.p('qux'), self.p('clunk')])
        store.rename(self.p('/foo/bar'), self.p('/foo/point'))
        self.assertEqual(store.get_entries(self.p('/foo')), [self.p('point'), self.p('qux'), self.p('clunk')])

    def test_remove_directory(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [self.p('foo')])
        self.assertEqual(store.get_entries(self.p('/foo')), [])
        store.remove(self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [])

    def test_add_file_in_empty_directory_and_then_removing_removes_directory(
      self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        store.add_file(self.p('/foo/bar'), self.p('/baz'))
        store.remove(self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.get_entries, self.p('/foo'))
        self.assertEqual(store.get_entries(self.p('/')), [])

    def test_removing_file_removes_real_paths(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        store.remove(self.p('/foo'))
        self.assertRaises(PathNotFound, store.get_fake_paths, self.p('/bar'))

    def test_is_dir_with_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertTrue(store.is_dir(self.p('/foo')))

    def test_is_dir_with_directory_containing_file_end_point(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo/bar'), self.p('/klink/klank'))
        self.assertTrue(store.is_dir(self.p('/foo')))

    def test_is_dir_with_directory_containing_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo/bar'))
        self.assertTrue(store.is_dir(self.p('/foo')))

    def test_is_dir_with_nonexistent_path(self):
        store = self.path_store_class()
        self.assertFalse(store.is_dir(self.p('/foo')))

    def test_is_file_with_file_end_point(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        self.assertTrue(store.is_file(self.p('/foo')))

    def test_is_file_with_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertFalse(store.is_file(self.p('/foo')))

    def test_path_exists_with_file_end_point(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        self.assertTrue(store.path_exists(self.p('/foo')))

    def test_path_exists_with_directory_end_point(self):
        store = self.path_store_class()
        store.add_directory(self.p('/foo'))
        self.assertTrue(store.path_exists(self.p('/foo')))

    def test_path_exists_with_non_existent_path(self):
        store = self.path_store_class()
        self.assertFalse(store.path_exists(self.p('/foo')))

    def test_get_entries_with_file_end_point(self):
        store = self.path_store_class()
        store.add_file(self.p('/foo'), self.p('/bar'))
        self.assertRaises(NotADirectory, store.get_entries, self.p('/foo'))

    def test_get_entries_with_empty_path_store(self):
        store = self.path_store_class()
        self.assertEqual(store.get_entries(self.p('/')), [])

    def test_get_real_subpaths(self):
        store = self.path_store_class()
        store.add_file(self.p('/klink'), self.p('/foo/bar/baz'))
        store.add_file(self.p('/klank'), self.p('/foo/bar/qux'))
        self.assertEqual(
          store.get_real_subpaths(self.p('/foo')),
          [self.p('/foo/bar/baz'), self.p('/foo/bar/qux')],
        )

    def test_meta_data_with_file_end_point(self):
        store = self.path_store_class()
        a = {1: 2, 3: 4}
        b = {5: 6, 7: 8}
        store.add_file(self.p('/foo/bar'), self.p('/bink/bonk'))
        self.assertRaises(NoMetaDataExists, store.get_meta_data, self.p('/foo/bar'))
        store.set_meta_data(self.p('/foo/bar'), a)
        self.assertEqual(store.get_meta_data(self.p('/foo/bar')), a)
        store.set_meta_data(self.p('/foo/bar'), b)
        self.assertEqual(store.get_meta_data(self.p('/foo/bar')), b)
        store.unset_meta_data(self.p('/foo/bar'))
        self.assertRaises(NoMetaDataExists, store.get_meta_data, self.p('/foo/bar'))

    def test_meta_data_with_directory_end_point(self):
        store = self.path_store_class()
        a = {1: 2, 3: 4}
        b = {5: 6, 7: 8}
        store.add_directory(self.p('/foo/bar'))
        self.assertRaises(NoMetaDataExists, store.get_meta_data, self.p('/foo/bar'))
        store.set_meta_data(self.p('/foo/bar'), a)
        self.assertEqual(store.get_meta_data(self.p('/foo/bar')), a)
        store.set_meta_data(self.p('/foo/bar'), b)
        self.assertEqual(store.get_meta_data(self.p('/foo/bar')), b)
        store.unset_meta_data(self.p('/foo/bar'))
        self.assertRaises(NoMetaDataExists, store.get_meta_data, self.p('/foo/bar'))

    def test_meta_data_with_directory_containing_file_end_point(self):
        store = self.path_store_class()
        a = {1: 2, 3: 4}
        store.add_file(self.p('/foo/bar/baz'), self.p('/bink/bonk'))
        self.assertRaises(NotAnEndPoint, store.get_meta_data, self.p('/foo/bar'))
        self.assertRaises(NotAnEndPoint, store.set_meta_data, self.p('/foo/bar'), a)
        self.assertRaises(NotAnEndPoint, store.get_meta_data, self.p('/foo/bar'))
        self.assertRaises(NotAnEndPoint, store.unset_meta_data, self.p('/foo/bar'))
        self.assertRaises(NotAnEndPoint, store.get_meta_data, self.p('/foo/bar'))

    def test_meta_data_with_directory_containing_directory_end_point(self):
        store = self.path_store_class()
        a = {1: 2, 3: 4}
        store.add_directory(self.p('/foo/bar/baz'))
        self.assertRaises(NotAnEndPoint, store.get_meta_data, self.p('/foo/bar'))
        self.assertRaises(NotAnEndPoint, store.set_meta_data, self.p('/foo/bar'), a)
        self.assertRaises(NotAnEndPoint, store.get_meta_data, self.p('/foo/bar'))
        self.assertRaises(NotAnEndPoint, store.unset_meta_data, self.p('/foo/bar'))
        self.assertRaises(NotAnEndPoint, store.get_meta_data, self.p('/foo/bar'))

    def test_meta_data_with_non_existent_path(self):
        store = self.path_store_class()
        a = {1: 2, 3: 4}
        self.assertRaises(PathNotFound, store.get_meta_data, self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.set_meta_data, self.p('/foo/bar'), a)
        self.assertRaises(PathNotFound, store.get_meta_data, self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.unset_meta_data, self.p('/foo/bar'))
        self.assertRaises(PathNotFound, store.get_meta_data, self.p('/foo/bar'))

    def test_meta_data_with_overridden_file_end_point(self):
        store = self.path_store_class()
        a = {1: 2, 3: 4}
        b = {5: 6, 7: 8}

        store.add_file(self.p('/foo/bar'), self.p('/bink/bonk'))
        store.set_meta_data(self.p('/foo/bar'), a)

        # Add a new end point that overrides the first.  Conceptually, this end
        # point is a blank slate.
        store.add_file(self.p('/foo/bar'), self.p('/klink/klank'))
        self.assertRaises(
          NoMetaDataExists, store.get_meta_data, self.p('/foo/bar'))

        store.set_meta_data(self.p('/foo/bar'), b)
        self.assertEqual(store.get_meta_data(self.p('/foo/bar')), b)

        # Removing the new end point gives us the old end point back, including
        # meta-data.
        store.remove(self.p('/foo/bar'))
        self.assertEqual(store.get_meta_data(self.p('/foo/bar')), a)

        store.add_file(self.p('/foo/bar'), self.p('/klink/klank'))
        self.assertRaises(
          NoMetaDataExists, store.get_meta_data, self.p('/foo/bar'))

        store.set_meta_data(self.p('/foo/bar'), b)
        store.unset_meta_data(self.p('/foo/bar'))

        store.remove(self.p('/foo/bar'))
        self.assertEqual(store.get_meta_data(self.p('/foo/bar')), a)

    def test_supports_threads(self):
        store = self.path_store_class()
        self.assertTrue(store.supports_threads() in (True, False))
