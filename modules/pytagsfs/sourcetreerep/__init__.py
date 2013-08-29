# Copyright (c) 2007-2011 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import os, re, stat
from itertools import chain

from pytagsfs.metastore import UnsettableKeyError
from pytagsfs.exceptions import (
  NotADirectory,
  IsADirectory,
  PathNotFound,
  InvalidArgument,
  UnrepresentablePath,
  WatchExistsError,
  NoSuchWatchError,
  SourceTreeMonitorError,
)
from pytagsfs.util import (
  split_path,
  join_path_abs,
  unicode_path_sep,
)
from pytagsfs.values import Values
from pytagsfs.subspat import Error as PatternError
from pytagsfs.debug import (
  log_debug,
  log_info,
  log_error,
  log_traceback,
)


def _make_filter(expr, real):
    if real:
        get_arg = lambda args: args[0]
    else:
        get_arg = lambda args: args[1]

    if expr.startswith('!'):
        trans_result = lambda x: not x
        regex = re.compile(expr[1:])
    else:
        trans_result = lambda x: x
        regex = re.compile(expr)
        
    def filtr(*args):
        return trans_result(regex.search(get_arg(args)))

    return filtr


STAT = object()
ENTRIES = object()


class SourceTreeRepresentation(object):
    meta_store = None
    substitution_patterns = None
    path_store = None
    source_tree = None
    monitor = None
    cache = None

    filters = None

    def __init__(
      self,
      meta_store,
      substitution_patterns,
      path_store,
      source_tree,
      monitor,
      cache = None,
      filters = (),
      debug = False,
    ):

        for substitution_pattern in substitution_patterns:
            if substitution_pattern.expression == '':
                raise ValueError('substitution pattern string cannot be empty')

        self.debug = debug

        self.meta_store = meta_store
        self.substitution_patterns = substitution_patterns
        self.path_store = path_store
        self.source_tree = source_tree

        self.monitor = monitor
        self.monitor.add_cb = self.add_cb
        self.monitor.remove_cb = self.remove_cb
        self.monitor.update_cb = self.update_cb

        self.cache = cache

        self.filters = []
        for expr, real in filters:
            self.add_filter(expr, real)

    def start(self):
        self.monitor.start(debug = self.debug)
        self.populate()

    def stop(self):
        self.monitor.stop()

    def populate(self):
        log_info('populating source tree representation...')
        self.add_source_dir(self.source_tree.root)

################################################################################

    def validate_source_path(self, real_path):
        self.validate_path(real_path)

    def validate_fake_path(self, fake_path):
        self.validate_path(fake_path)

    def validate_path(self, path):
        if type(path) is not unicode:
            raise AssertionError(
              u'path object %s is not a unicode string' % repr(path))

        if not path.startswith(unicode_path_sep):
            raise AssertionError(
              u'path %s does not start with "%s"' % (
                repr(path), unicode_path_sep))

        if path.endswith(unicode_path_sep) and (path != unicode_path_sep):
            raise AssertionError(
              u'path %s ends with "%s"' % (repr(path), unicode_path_sep))
        
    def fill_path(self, substitutions):
        log_debug(u'fill_path: substitutions = %r', substitutions)

        if isinstance(substitutions, Values):
            raise TypeError('substitutions must not be Values instance')

        fake_path_parts = []
        for substitution_pattern in self.substitution_patterns:
            try:
                fake_path_part = substitution_pattern.fill(substitutions)
            except PatternError, e:
                raise UnrepresentablePath(unicode(e))

            if fake_path_part == '':
                # This is potentially caused by a bad format string.  We
                # need to handle it here because it could be caused by a
                # format string directory segment that is a single
                # conditional expression (and that is valid).  If it is
                # caused by a segment that is empty ("//"), it is better to
                # handle the problem at initialization time by rejecting
                # the format string.
                raise UnrepresentablePath(
                  u'fake path would have a path segment with length zero')

            if unicode_path_sep in fake_path_part:
                # The tag value has a slash in it.  Proceeding would result
                # in a fake path that has too many levels of directories.
                raise UnrepresentablePath(
                  u'fake path would have a path segment with a slash')

            fake_path_parts.append(fake_path_part)

        return join_path_abs(fake_path_parts)

    def add_source_dir(self, real_path):
        '''
        Recursively add source directory ``real_path`` to the source tree
        representation.  Fail silently if:

         * Path corresponds with a file that is not a directory.
         * Directory does not exist.

        If a directory with the same real path already exists in the source
        tree representation, it will be silently removed from the
        representation before the add operation is executed.
        '''

        # We only remove the existing entry if it is a directory.  An existing
        # entry that is a file likely indicates a more serious problem.  That
        # should give us a traceback.
        try:
            self.remove_source_dir(real_path)
        except PathNotFound:
            pass

        try:
            self.monitor.add_source_dir(self.source_tree.encode(real_path))
        except (PathNotFound, NotADirectory, WatchExistsError), e:
            log_error('failed to add source directory %s: %s', real_path, e)
            return
        except SourceTreeMonitorError:
            # Log the error and ignore the directory.  If we can't monitor it
            # properly, we shouldn't present it at all.  That would violate the
            # user's assumptions about the exposed files.
            log_traceback()
            return

        for dirpath, dirnames, filenames in self.source_tree.walk(real_path):
            if dirpath != real_path:
                break
            for dirname in dirnames:
                real_path = os.path.join(dirpath, dirname)
                self.add_source_dir(real_path)
            for filename in filenames:
                real_path = os.path.join(dirpath, filename)
                self.add_source_file(real_path)

    def remove_source_dir(self, real_path):
        '''
        Recursively remove source directory ``real_path`` from the source tree
        representation.  Do nothing if:

         * ``real_path`` was never added to the source tree representation.
        '''
        # We remove source files only because any subdirectories should already
        # have been removed.
        for real_subpath in self.path_store.get_real_subpaths(real_path):
            self.remove_source_file(real_subpath)

        try:
            self.monitor.remove_source_dir(self.source_tree.encode(real_path))
        except NoSuchWatchError, e:
            log_error('failed to remove source directory %s: %s', real_path, e)
            return
        except SourceTreeMonitorError:
            log_traceback()
            return

    def add_source_file(self, real_path):
        '''
        Add source file ``real_path`` to the source tree representation.  Do
        nothing if:

         * The file does not exist.
         * The target file is a directory.
        '''

        # We want to filter out unreadable files and symlinks.  These checks
        # are racey, of course.  A symlink could be removed and replaced with
        # a real file immediately after our check.  Likewise, a file that is
        # unreadable because of permissions could have its mode changed.

        # However, in either of these cases a new source tree monitor event
        # will be received and another attempt to add the source file will
        # be made.  Thus, there is no serious consequence.

        # Note that if all MetaStore implementations pulled metadata from file
        # contents, the isreadable check would be unnecessary.  But some
        # (PathMetaStore, for instance) do not read the source file to obtain
        # metadata.

        # Also note that if we handled symlinks correctly everywhere (in
        # getattr, populate, and in SourceTreeMonitor implementations), the
        # issymlink check could be dropped.  Since we don't currently handle
        # them correctly, though, it is best to simply ignore them.

        if not self.source_tree.isreadable(real_path):
            log_debug(
              u'add_source_file: not readable, not adding: %s',
              real_path,
            )
            return

        if self.source_tree.issymlink(real_path):
            log_debug(
              u'add_source_file: not adding symlink: %s',
              real_path,
            )
            return

        # We only remove the existing entry if it is a file.  An existing entry
        # that is a directory likely indicates a more serious problem.  That
        # should give us a traceback.
        try:
            self.remove_source_file(real_path)
        except PathNotFound:
            pass

        values = self.meta_store.get(real_path)

        fake_paths = []
        splitter_groups = []

        for substitutions in values.iter_permutations():
            try:
                fake_path = self.fill_path(substitutions)
            except UnrepresentablePath, e:
                log_info(u'Unrepresentable file: %s', real_path)
                log_info(unicode(e))
                return

            if fake_path not in fake_paths:
                fake_paths.append(fake_path)
                splitters = self._create_splitters(fake_path, substitutions)
                splitter_groups.append(splitters)

        try:
            existing_fake_paths = set(self.get_fake_paths(real_path))
        except PathNotFound:
            pass
        else:
            index = 0
            for fake_path in list(fake_paths):
                if fake_path in existing_fake_paths:
                    log_debug(
                      u'Path mapping already exists, not adding: %s -> %s',
                      real_path,
                      fake_path,
                    )
                    del fake_paths[index]
                    del splitter_groups[index]
                else:
                    index = index + 1

        for fake_path, splitters in zip(fake_paths, splitter_groups):
            if not self.filter_path(
              self.source_tree.get_relative_path(real_path),
              fake_path
            ):
                log_debug(
                  u'Explicitly excluded fake path: %s; real path: %s',
                  fake_path,
                  real_path,
                )
                return

            try:
                self.monitor.add_source_file(self.source_tree.encode(real_path))
            except (PathNotFound, NotADirectory, WatchExistsError), e:
                log_error('failed to add source file %s: %s', real_path, e)
                return
            except SourceTreeMonitorError:
                # Log the error and ignore the file.  If we can't monitor it
                # properly, we shouldn't present it at all.  That would violate
                # the user's assumptions about the exposed files.
                log_traceback()
                return

            log_debug(u'add_source_file: adding %r, %r', fake_path, real_path)
            self.path_store.add_file(fake_path, real_path)
            self._set_splitters(fake_path, splitters)
            self._cache_prune_branch_to(fake_path)

    def remove_source_file(self, real_path):
        try:
            fake_paths = self.get_fake_paths(real_path)
        except PathNotFound:
            log_debug(u'remove_source_file: PathNotFound: %s', real_path)
            return

        for fake_path in fake_paths:
            log_debug(
              u'remove_source_file: removing %r, %r',
              fake_path,
              real_path,
            )
            try:
                self.path_store.remove(fake_path, real_path)
            except PathNotFound:
                log_traceback()

            self._cache_prune_branch_to(fake_path)

        try:
            self.monitor.remove_source_file(self.source_tree.encode(real_path))
        except NoSuchWatchError, e:
            log_error('failed to remove source file %s: %s', real_path, e)
            return
        except SourceTreeMonitorError:
            log_traceback()
            return

    def update_source_file(self, real_path):
        self.add_source_file(real_path)

    def add_source_path(self, real_path):
        self.add_source_file(real_path)
        self.add_source_dir(real_path)

    def remove_source_path(self, real_path):
        self.remove_source_file(real_path)
        self.remove_source_dir(real_path)

    def update_source_path(self, real_path):
        # Note: there is no update_source_dir.  Nobody cares if directory
        # permissions or timestamps change.  We only care about files.
        self.update_source_file(real_path)

################################################################################

    def add_filter(self, expr, real):
        self.filters.append(_make_filter(expr, real))

    def filter_path(self, real_path, fake_path):
        for filtr in self.filters:
            if not filtr(real_path, fake_path):
                return False
        return True

################################################################################

    def rename_path(self, old_fake_path, new_fake_path):
        self.validate_fake_path(old_fake_path)
        self.validate_fake_path(new_fake_path)
        log_info(
          u'SourceTreeRepresentation.rename_path: renaming %s to %s',
          old_fake_path,
          new_fake_path,
        )

        old_path_parts = split_path(old_fake_path)
        new_path_parts = split_path(new_fake_path)

        if len(old_path_parts) != len(new_path_parts):
            log_error(
              (
                u'rename_path: old path and new path have '
                u'differing directory depths: %s, %s'
              ),
              old_fake_path,
              new_fake_path,
            )
            raise InvalidArgument

        # Find the index of the path segment that changed:
        for index, (old_path_part, new_path_part) in enumerate(
          zip(old_path_parts, new_path_parts)):
            if old_path_part != new_path_part:
                break

        old_node_path = join_path_abs(old_path_parts[:index+1])

        # Here's our approach:
        # 1. Separate the affected end points into files and directories.
        # 2. For each directory end point, remove the old directory and add the
        #    new one.
        # 3. For each file end point:
        #     a. We know which path segment changed, so we can use that
        #        information to get old tag values for that segment and new tag
        #        values for that segment.  These values represent the total tag
        #        change for that particular end point.
        #     b. Group the values by real path and then combine each group.
        #     c. For each affected real path, use Values.diff3 to calculate a
        #        final values delta and apply it to the real path.

        end_points = self.path_store.get_end_points(old_fake_path)

        file_end_points = []
        directory_end_points = []
        for end_point in end_points:
            if self.is_file(end_point):
                file_end_points.append(end_point)
            else:
                directory_end_points.append(end_point)

        del end_points

        # Handle directory end points:
        for end_point in directory_end_points:
            self.remove_directory(end_point)
            end_point_parts = split_path(end_point)
            end_point_parts[index] = new_path_parts[index]
            self.add_directory_with_parents(join_path_abs(end_point_parts))

        del directory_end_points

        # Get old values, new values for each file end point:
        old_values_by_end_point = {}
        new_values_by_end_point = {}
        for end_point in file_end_points:
            meta_data = self.path_store.get_meta_data(end_point)
            end_point_splitters = meta_data['splitters']
            splitter = end_point_splitters[index]

            old_values = Values.from_flat_dict(splitter.split(old_path_part))

            try:
                new_values = Values.from_flat_dict(
                  splitter.split(new_path_part))
            except PatternError, e:
                log_error(u'rename_path: %s', e)
                raise InvalidArgument

            old_values_by_end_point[end_point] = old_values
            new_values_by_end_point[end_point] = new_values

        # Group file end points by real path:
        end_points_by_real_path = {}
        for end_point in file_end_points:
            real_path = self.get_real_path(end_point)
            try:
                l = end_points_by_real_path[real_path]
            except KeyError:
                l = []
                end_points_by_real_path[real_path] = l
            l.append(end_point)

        # Combine old values and new values for each real path:
        old_values_by_real_path = {}
        new_values_by_real_path = {}
        for real_path, end_points in end_points_by_real_path.items():
            old_values_by_real_path[real_path] = Values.combine([
              old_values_by_end_point[end_point] for end_point in end_points])
            new_values_by_real_path[real_path] = Values.combine([
              new_values_by_end_point[end_point] for end_point in end_points])

        # Calculate a final values delta for each real path and apply it:
        for real_path in end_points_by_real_path.keys():
            current_values = self.meta_store.get(real_path)
            old_values = old_values_by_real_path[real_path]
            new_values = new_values_by_real_path[real_path]
            apply_values = Values.diff3(current_values, old_values, new_values)

            log_debug(u'rename: real_path = %r', real_path)
            log_debug(u'rename: current_values = %r', current_values)
            log_debug(u'rename: old_values = %r', old_values)
            log_debug(u'rename: new_values = %r', new_values)
            log_debug(u'rename: apply_values = %r', apply_values)

            try:
                self.meta_store.set(real_path, apply_values)
            except UnsettableKeyError:
                log_debug(u'rename: %r', UnsettableKeyError)
                raise InvalidArgument

    def add_directory_with_parents(self, fake_path):
        parts = split_path(fake_path)
        path = unicode_path_sep
        for part in parts:
            path = os.path.join(path, part)
            if not self.is_dir(path):
                self.add_directory(path)

    def add_directory(self, fake_path):
        self.validate_fake_path(fake_path)

        parts = split_path(fake_path)
        len_parts = len(parts)

        if len_parts >= len(self.substitution_patterns):
            log_error(
              'add_directory: too many directories: %r',
              fake_path,
            )
            raise InvalidArgument

        splitters = self._create_splitters(fake_path, {})
        splitter = splitters[-1]

        try:
            splitter.split(parts[-1])
        except PatternError, e:
            log_info(u'add_directory: %s', e)
            raise InvalidArgument

        self.path_store.add_directory(fake_path)
        self._set_splitters(fake_path, splitters)
        self._cache_prune_branch_to(fake_path)

    def remove_directory(self, fake_path):
        self.validate_fake_path(fake_path)
        self.path_store.remove(fake_path)
        self._cache_prune_branch_to(fake_path)

    def get_real_path(self, fake_path):
        self.validate_fake_path(fake_path)
        return self.path_store.get_real_path(fake_path)

    def get_fake_paths(self, real_path):
        self.validate_source_path(real_path)
        return self.path_store.get_fake_paths(real_path)

    def get_entries(self, fake_path):
        self.validate_fake_path(fake_path)
        try:
            return self._cache_get(fake_path, ENTRIES)
        except KeyError:
            pass
        entries = self.path_store.get_entries(fake_path)
        self.cache_put(fake_path, ENTRIES, entries)
        return entries

    def path_exists(self, fake_path):
        self.validate_fake_path(fake_path)
        return self.path_store.path_exists(fake_path)

    def is_file(self, fake_path):
        self.validate_fake_path(fake_path)
        return self.path_store.is_file(fake_path)

    def is_dir(self, fake_path):
        self.validate_fake_path(fake_path)
        return self.path_store.is_dir(fake_path)

    def is_empty_dir(self, fake_path):
        return self.is_dir(fake_path) and not self.get_entries(fake_path)

    def supports_threads(self):
        return (
          self.path_store.supports_threads() and (
            self.monitor is None or
            self.monitor.supports_threads()
          )
        )

    def can_handle_fork(self):
        return self.monitor.can_handle_fork()

    def getattr(self, fake_path):
        self.validate_fake_path(fake_path)
        try:
            return self._cache_get(fake_path, STAT)
        except KeyError:
            pass
        stat_result = self._getattr(fake_path)
        self.cache_put(fake_path, STAT, stat_result)
        return stat_result

    def _getattr(self, fake_path):
        try:
            real_path = self.get_real_path(fake_path)
        except (IsADirectory, PathNotFound):
            pass
        else:
            return self.source_tree.lstat(real_path)

        # Files should've been handled above.  Now we're just dealing with
        # directories and non-existent paths.

        # If fake_path doesn't exist, the exception will be raised here and
        # caught be our caller.
        subdirs = self._get_subdirectories(fake_path)

        source_root_statinfo = self.source_tree.lstat(self.source_tree.root)

        if not isinstance(source_root_statinfo, os.stat_result):
            # FIXME: I don't think this is being handled correctly.  Should we
            # be negating the value before returning it?  Identify when and
            # where this actually happens and write a test for it.  I think I
            # only saw this once or twice when testing on OSX.  It may be a bug
            # in os.lstat.

            # source_root_statinfo is actually an integer indicating an error.
            log_error(
              u'SourceTreeRepresentation._getattr: source_root_statinfo = %r',
              source_root_statinfo,
            )
            return source_root_statinfo

        st_mode = stat.S_IFDIR | (stat.S_IMODE(source_root_statinfo.st_mode))
        st_ino = 0
        st_dev = 0
        st_nlink = 2 + len(subdirs)
        st_uid = source_root_statinfo.st_uid
        st_gid = source_root_statinfo.st_gid
        st_size = 0
        st_atime = self._get_directory_atime(fake_path)
        st_mtime = self._get_directory_mtime(fake_path)
        st_ctime = self._get_directory_ctime(fake_path)

        if st_atime == 0:
            st_atime = source_root_statinfo.st_atime
        if st_mtime == 0:
            st_mtime = source_root_statinfo.st_mtime
        if st_ctime == 0:
            st_ctime = source_root_statinfo.st_ctime

        return os.stat_result((
          st_mode,
          st_ino,
          st_dev,
          st_nlink,
          st_uid,
          st_gid,
          st_size,
          st_atime,
          st_mtime,
          st_ctime,
        ))

    def utime(self, fake_path, times):
        self.validate_fake_path(fake_path)
        if self.is_file(fake_path):
            log_debug(u'utime: updating source file')
            real_path = self.get_real_path(fake_path)
            self.source_tree.utime(real_path, times)
            self._cache_prune_branch_to(fake_path, STAT)
        elif self.is_empty_dir(fake_path):
            log_debug(u'utime: updating source tree root')
            self.source_tree.utime(self.source_tree.root, times)
        else:
            log_debug(u'utime: updating all end-points')
            # May raise FakePathNotFound:
            for end_point in self.path_store.get_end_points(fake_path):
                self.utime(end_point, times)

    def _get_subdirectories(self, fake_path):
        entries = self.get_entries(fake_path)
        subdirs = []

        for entry in entries:
            entry_path = os.path.join(fake_path, entry)
            try:
                if self.is_dir(entry_path):
                    subdirs.append(entry_path)
            except PathNotFound:
                log_traceback()
                log_error(
                  u'PathNotFound calling is_dir on previously known entry'
                )
                pass
        return subdirs

    def _get_file_time_attr(self, fake_path, attr_name):
        return getattr(self.getattr(fake_path), attr_name)

    def _get_directory_time_attr(self, fake_path, attr_name):
        entries = self.get_entries(fake_path)
        entry_paths = [os.path.join(fake_path, e) for e in entries]

        # FIXME: This could be more efficient.
        subdirs = [
          entry_path for entry_path in entry_paths if self.is_dir(entry_path)
        ]
        files = [
          entry_path for entry_path in entry_paths if self.is_file(entry_path)
        ]

        subdir_times = []
        for subdir in subdirs:
            try:
                time_attr = self._get_directory_time_attr(subdir, attr_name)
            except OSError, e:
                log_error(
                  (
                    u'_get_directory_time_attr: '
                    u'caught %r getting %r for subdir %r'
                  ),
                  e,
                  attr_name,
                  subdir,
                )
            else:
                subdir_times.append(time_attr)

        file_times = []
        for file in files:
            try:
                time_attr = self._get_file_time_attr(file, attr_name)
            except OSError, e:
                log_error(
                  (
                    u'_get_directory_time_attr: '
                    u'caught %r getting %r for file %r'
                  ),
                  e,
                  attr_name,
                  file,
                )
            else:
                file_times.append(time_attr)

        times = list(chain(subdir_times, file_times))

        if not times:
            return 0

        return max(times)

    def _get_file_atime(self, fake_path):
        return self._get_file_time_attr(fake_path, 'st_atime')

    def _get_directory_atime(self, fake_path):
        return self._get_directory_time_attr(fake_path, 'st_atime')

    def _get_file_mtime(self, fake_path):
        return self._get_file_time_attr(fake_path, 'st_mtime')

    def _get_directory_mtime(self, fake_path):
        return self._get_directory_time_attr(fake_path, 'st_mtime')

    def _get_file_ctime(self, fake_path):
        return self._get_file_time_attr(fake_path, 'st_ctime')

    def _get_directory_ctime(self, fake_path):
        return self._get_directory_time_attr(fake_path, 'st_ctime')

################################################################################

    def _create_splitters(self, fake_path, values):
        fake_path_parts = split_path(fake_path)
        splitters = [
          sp.get_splitter(values)
          for sp in self.substitution_patterns[:len(fake_path_parts)]
        ]
        return splitters

    def _set_splitters(self, fake_path, splitters):
        self.path_store.set_meta_data(fake_path, {'splitters': splitters})

################################################################################

    def add_cb(self, event_path, is_dir = None):
        real_path = self.source_tree.decode(event_path).rstrip(unicode_path_sep)
        self.validate_source_path(real_path)
        if is_dir is None:
            self.add_source_path(real_path)
        elif is_dir:
            self.add_source_dir(real_path)
        else:
            self.add_source_file(real_path)

    def remove_cb(self, event_path, is_dir = None):
        real_path = self.source_tree.decode(event_path).rstrip(unicode_path_sep)
        self.validate_source_path(real_path)
        if is_dir is None:
            self.remove_source_path(real_path)
        elif is_dir:
            self.remove_source_dir(real_path)
        else:
            self.remove_source_file(real_path)

    def update_cb(self, event_path, is_dir = None):
        real_path = self.source_tree.decode(event_path).rstrip(unicode_path_sep)
        self.validate_source_path(real_path)
        if is_dir is None:
            self.update_source_path(real_path)
        elif is_dir:
            return
        else:
            self.update_source_file(real_path)

################################################################################

    def cache_put(self, fake_path, key, value):
        if self.cache is not None:
            return self.cache.put(fake_path, key, value)

    def _cache_get(self, fake_path, key):
        if self.cache is not None:
            return self.cache.get(fake_path, key)
        raise KeyError('no cache to get from')

    def _cache_prune(self, fake_path = None, key = None):
        if self.cache is not None:
            return self.cache.prune(fake_path, key)
        raise KeyError('no cache to prune')

    def _cache_prune_branch_to(self, fake_path, key = None):
        while True:
            try:
                self._cache_prune(fake_path, key)
            except KeyError:
                pass
            if fake_path == unicode_path_sep:
                break
            fake_path = os.path.dirname(fake_path)
