# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os.path

try:
    from functools import wraps
except ImportError:
    from sclapp.legacy_support import wraps

from sclapp.util import safe_encode

from pytagsfs.pathstore import PathStore
from pytagsfs.util import (
  last_unique,
  unicode_path_sep,
)
from pytagsfs.exceptions import (
  FakePathNotFound,
  RealPathNotFound,
  NotADirectory,
  IsADirectory,
  PathExists,
  PathNotFound,
  InvalidArgument,
  DirectoryNotEmpty,
  NoMetaDataExists,
  NotAnEndPoint,
  PathError,
)


class DictList(dict):
    def get_or_set_and_get(self, k):
        try:
            return self[k]
        except KeyError:
            pass
        try:
            self[k] = []
        except:
            del self[k]
            raise
        return self[k]

    def pop_and_clean(self, k):
        try:
            return self[k].pop()
        finally:
            self.clean(k)

    def clean(self, k):
        if not self[k]:
            del self[k]


class PathDoesNotExistInPathMapping(PathError):
    pass


class PathMapping(object):
    forward_mapping = None
    reverse_mapping = None

    def __init__(self):
        self.forward_mapping = DictList()
        self.reverse_mapping = DictList()

    def add_real_path(self, fake_path, real_path):
        self.forward_mapping.get_or_set_and_get(fake_path).append(real_path)
        try:
            self.reverse_mapping.get_or_set_and_get(real_path).append(fake_path)
        except:
            self.forward_mapping.pop_and_clean(fake_path)
            raise

    def remove_real_path(self, fake_path, real_path = None):
        if real_path is None:
            real_path = self.forward_mapping.pop_and_clean(fake_path)
        else:
            self.forward_mapping[fake_path].remove(real_path)
            self.forward_mapping.clean(fake_path)

        try:
            self.reverse_mapping[real_path].remove(fake_path)
            if not self.reverse_mapping[real_path]:
                del self.reverse_mapping[real_path]
        except:
            self.forward_mapping.get_or_set_and_get(fake_path).append(real_path)
            raise

    def get_real_path(self, fake_path):
        try:
            return self.forward_mapping[fake_path][-1]
        except (KeyError, IndexError):
            raise PathDoesNotExistInPathMapping(fake_path)

    def get_fake_paths(self, real_path):
        try:
            return self.reverse_mapping[real_path]
        except KeyError:
            raise PathDoesNotExistInPathMapping(real_path)

    def get_reverse_keys(self):
        return self.reverse_mapping.keys()


class Entry(unicode):
    def __init__(self, s):
        if not isinstance(s, unicode):
            raise TypeError(u'must be unicode: %s' % repr(s))
        super(Entry, self).__init__()

    def set_meta_data(self, meta_data):
        self.meta_data = meta_data

    def get_meta_data(self):
        try:
            return self.meta_data
        except AttributeError:
            raise NoMetaDataExists(self)

    def unset_meta_data(self):
        try:
            del self.meta_data
        except AttributeError:
            raise NoMetaDataExists(self)


class DirectoryAlreadyExistsInEntryStore(PathError):
    pass


class DirectoryDoesNotExistInEntryStore(PathError):
    pass


class EntryDoesNotExistInEntryStore(PathError):
    pass


class EntryStore(object):
    entries = None

    def __init__(self):
        self.entries = {}
        self.add_directory(unicode_path_sep)

    def add_directory(self, directory):
        if directory in self.entries:
            raise DirectoryAlreadyExistsInEntryStore(directory)
        self.entries[directory] = []

    def remove_directory(self, directory):
        if directory == unicode_path_sep:
            raise ValueError(unicode_path_sep)
        del self.entries[directory]

    def add_entry(self, directory, entry):
        if not isinstance(entry, Entry):
            entry = Entry(entry)
        try:
            self.entries[directory].append(entry)
        except KeyError:
            raise DirectoryDoesNotExistInEntryStore(directory)

    def add_entries(self, directory, entries):
        for entry in entries:
            self.add_entry(directory, entry)

    def remove_entry(self, directory, entry):
        directory, index = self._locate_entry(directory, entry)
        del self.entries[directory][index]

    def get_all_entries(self, directory):
        try:
            return self.entries[directory]
        except KeyError:
            raise DirectoryDoesNotExistInEntryStore(directory)

    def get_entries(self, directory):
        return last_unique(self.get_all_entries(directory))

    def get_entry(self, fake_path):
        directory, index = self._locate_entry_by_fake_path(fake_path)
        return self.get_all_entries(directory)[index]

    def _locate_entry_by_fake_path(self, fake_path):
        if fake_path.endswith(unicode_path_sep):
            raise ValueError(fake_path)
        directory, entry = os.path.split(fake_path)
        return self._locate_entry(directory, entry)

    def _locate_entry(self, directory, entry):
        reversed_entries = list(reversed(self.get_all_entries(directory)))
        try:
            reverse_index = reversed_entries.index(entry)
        except IndexError:
            raise EntryDoesNotExistInEntryStore(entry)
        index = len(reversed_entries) - reverse_index - 1
        return directory, index

    def replace_entry(self, directory, entry, new_entry):
        if not isinstance(new_entry, Entry):
            new_entry = Entry(new_entry)
        directory, index = self._locate_entry(directory, entry)
        self.entries[directory][index] = new_entry

    def iter_directories_and_entries_recursive_reversed(self, fake_path):
        if fake_path.endswith(unicode_path_sep):
            raise ValueError(fake_path)

        while True:
            fake_path, entry = os.path.split(fake_path)
            if not entry:
                break
            yield fake_path, entry

    def iter_directories_and_entries_recursive(self, fake_path):
        for fake_path, entry in reversed(list(
          self.iter_directories_and_entries_recursive_reversed(fake_path)
        )):
            yield fake_path, entry

    def add_entries_and_directories_recursive(self, fake_path):
        for fake_path, entry in (
          self.iter_directories_and_entries_recursive(fake_path)):
            try:
                entries = self.get_all_entries(fake_path)
            except DirectoryDoesNotExistInEntryStore:
                self.add_directory(fake_path)
            else:
                if (fake_path != unicode_path_sep) and (entries == []):
                    self.remove_entries_and_directories_recursive(fake_path)
            self.add_entry(fake_path, entry)

    def remove_entries_and_directories_recursive(self, fake_path):
        directories = []
        for fake_path, entry in self.iter_directories_and_entries_recursive_reversed(
          fake_path):
            self.remove_entry(fake_path, entry)
            directories.insert(0, fake_path)

        for directory in directories:
            if (
              (not self.get_all_entries(directory)) and
              (directory != unicode_path_sep)
            ):
                self.remove_directory(directory)


class PyTypesPathStore(PathStore):
    __doc__ = '''
    Path store implementation that stores path information in data types based
    on built-in Python types (dict, list, etc).

    >>> path_store = PyTypesPathStore()

    ''' + PathStore.__doc__

    path_mapping = None
    entries = None
    meta_data = None

    def __init__(self):
        super(PyTypesPathStore, self).__init__()
        self.path_mapping = PathMapping()
        self.entries = EntryStore()
        self.meta_data = {}

    def _assert_not_root(self, path):
        if path == unicode_path_sep:
            raise AssertionError(
              'old_fake_path must not be "%s"' % unicode_path_sep)

    def add_file(self, fake_path, real_path):
        try:
            if self.is_dir(fake_path):
                raise PathExists(fake_path)
        except PathNotFound:
            pass

        try:
            if real_path == self.get_real_path(fake_path):
                raise ValueError(u'duplicate path mapping: %s, %s' % (
                  repr(fake_path), repr(real_path)))
        except PathNotFound:
            pass

        self.path_mapping.add_real_path(fake_path, real_path)
        self.entries.add_entries_and_directories_recursive(fake_path)

    def add_directory(self, fake_path):
        self._must_not_exist(fake_path)
        self.entries.add_entries_and_directories_recursive(fake_path)
        self.entries.add_directory(fake_path)

    def rename(self, old_fake_path, new_fake_path):
        if self.is_dir(old_fake_path):
            return self._rename_directory(old_fake_path, new_fake_path)
        if self.is_file(old_fake_path):
            return self._rename_file(old_fake_path, new_fake_path)
        raise FakePathNotFound(old_fake_path)

    def _rename_file(self, old_fake_path, new_fake_path):
        real_path = self.get_real_path(old_fake_path)

        self._verify_rename(old_fake_path, new_fake_path)

        old_dir, old_entry = os.path.split(old_fake_path)
        new_dir, new_entry = os.path.split(new_fake_path)

        if old_dir == new_dir:
            self.entries.replace_entry(old_dir, old_entry, new_entry)
            self.path_mapping.remove_real_path(old_fake_path, real_path)
            self.path_mapping.add_real_path(new_fake_path, real_path)
        else:
            self._remove_file(old_fake_path, real_path)
            self.add_file(new_fake_path, real_path)

    def _rename_directory(self, old_fake_path, new_fake_path):
        self._must_be_empty_directory(old_fake_path)

        self._assert_not_root(old_fake_path)
        self._assert_not_root(new_fake_path)

        self._verify_rename(old_fake_path, new_fake_path)

        old_dir, old_entry = os.path.split(old_fake_path)
        new_dir, new_entry = os.path.split(new_fake_path)

        entries = self.entries.get_all_entries(old_fake_path)

        if old_dir == new_dir:
            self.entries.remove_directory(old_fake_path)
            self.entries.replace_entry(old_dir, old_entry, new_entry)
            self.entries.add_directory(new_fake_path)
        else:
            self._remove_directory(old_fake_path)
            self.add_directory(new_fake_path)

        self.entries.add_entries(new_fake_path, entries)

    def _verify_rename(self, old_fake_path, new_fake_path):
        if old_fake_path == new_fake_path:
            raise ValueError('old_fake_path and new_fake_path are the same')
        if old_fake_path.endswith(unicode_path_sep):
            raise ValueError(old_fake_path)
        if new_fake_path.endswith(unicode_path_sep):
            raise ValueError(new_fake_path)

    def remove(self, fake_path, real_path = None):
        if self.is_dir(fake_path):
            if real_path is not None:
                raise IsADirectory(fake_path)
            if self.is_empty_dir(fake_path):
                return self._remove_directory(fake_path)
            raise DirectoryNotEmpty(fake_path)
        if self.is_file(fake_path):
            return self._remove_file(fake_path, real_path)
        raise FakePathNotFound(fake_path)

    def _remove_file(self, fake_path, real_path = None):
        self.path_mapping.remove_real_path(fake_path, real_path)
        self.entries.remove_entries_and_directories_recursive(fake_path)

    def _remove_directory(self, fake_path):
        self._assert_not_root(fake_path)
        self._must_be_empty_directory(fake_path)
        self.entries.remove_directory(fake_path)
        self.entries.remove_entries_and_directories_recursive(fake_path)

    def get_real_path(self, fake_path):
        try:
            return self.path_mapping.get_real_path(fake_path)
        except PathDoesNotExistInPathMapping:
            if self.is_dir(fake_path):
                raise IsADirectory(fake_path)
            raise FakePathNotFound(fake_path)

    def get_fake_paths(self, real_path):
        try:
            return list(self.path_mapping.get_fake_paths(real_path))
        except PathDoesNotExistInPathMapping:
            raise RealPathNotFound(real_path)

    def get_real_subpaths(self, real_path):
        if real_path.endswith(unicode_path_sep):
            raise ValueError(u'real_path %s ends with %s' % (
              repr(real_path), repr(unicode_path_sep)))
        real_path = u'%s%s' % (real_path, unicode_path_sep)
        real_paths = self.path_mapping.get_reverse_keys()
        return [p for p in real_paths if p.startswith(real_path)]

    def get_entries(self, fake_path):
        self._must_be_dir(fake_path)
        return list(self.entries.get_entries(fake_path))

    def is_file(self, fake_path):
        try:
            self.path_mapping.get_real_path(fake_path)
        except PathDoesNotExistInPathMapping:
            return False
        return True

    def is_dir(self, fake_path):
        try:
            self.entries.get_entries(fake_path)
        except DirectoryDoesNotExistInEntryStore:
            return False
        return True

    def is_empty_dir(self, fake_path):
        return (
          self.is_dir(fake_path) and
          not self.entries.get_all_entries(fake_path)
        )

    def path_exists(self, fake_path):
        if self.is_file(fake_path):
            return True
        if self.is_dir(fake_path):
            return True
        return False

    def _must_exist(self, fake_path):
        if not self.path_exists(fake_path):
            raise FakePathNotFound(fake_path)

    def _must_not_exist(self, fake_path):
        if self.path_exists(fake_path):
            raise PathExists(fake_path)

    def _must_be_file(self, fake_path):
        self._must_exist(fake_path)
        if not self.is_file(fake_path):
            raise IsADirectory(fake_path)

    def _must_be_dir(self, fake_path):
        self._must_exist(fake_path)
        if not self.is_dir(fake_path):
            raise NotADirectory(fake_path)

    def _must_be_empty_directory(self, fake_path):
        self._must_exist(fake_path)
        if self.is_empty_dir(fake_path):
            return
        if self.is_file(fake_path):
            raise NotADirectory(fake_path)
        raise NotAnEndPoint(fake_path)

    def _must_be_end_point(self, fake_path):
        self._must_exist(fake_path)
        if self.is_file(fake_path):
            return
        if self.is_empty_dir(fake_path):
            return
        raise NotAnEndPoint(fake_path)

    def set_meta_data(self, fake_path, meta_data):
        self._must_be_end_point(fake_path)
        entry = self.entries.get_entry(fake_path)
        entry.set_meta_data(meta_data)

    def get_meta_data(self, fake_path):
        self._must_be_end_point(fake_path)
        entry = self.entries.get_entry(fake_path)
        return entry.get_meta_data()

    def unset_meta_data(self, fake_path):
        self._must_be_end_point(fake_path)
        entry = self.entries.get_entry(fake_path)
        entry.unset_meta_data()

    def supports_threads(self):
        return True
