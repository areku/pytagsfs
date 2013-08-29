# Copyright (c) 2007-2009 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

# Import locale from sclapp before all other imports to work around bug in
# stdlib.
# See http://www.selenic.com/mercurial/wiki/index.cgi/Character_Encoding_On_OSX.
from sclapp import locale

import sys, os, re, platform

try:
    from functools import wraps
except ImportError:
    from sclapp.legacy_support import wraps

from optparse import OptParseError, SUPPRESS_HELP

from pytagsfs.fuselib import (
  TokenFuse,
  FileSystem,
)
from pytagsfs.optgroup import GroupingOptionParser
from pytagsfs.subspat import SubstitutionPattern
from pytagsfs.sourcetree import SourceTree
from pytagsfs.metastore import DelegateMultiMetaStore
from pytagsfs.sourcetreemon import (
  SOURCE_TREE_MONITORS,
  get_source_tree_monitor,
)
from pytagsfs.exceptions import ComponentError
from pytagsfs.pathpropcache import PathPropCache
from pytagsfs.debug import (
  log_debug,
  log_warning,
  set_log_level,
  DEBUG,
  INFO,
  WARNING,
  ERROR,
  CRITICAL,
  enable_stderr,
  set_logsize,
)
from pytagsfs.util import (
  get_obj_by_dotted_name,
  return_errno,
  split_path,
  unicode_path_sep,
  ftruncate_path,
)
from pytagsfs.file import ReadOnlyFile, ReadWriteFile
from pytagsfs.specialfile import SpecialFileFileSystemMixin
from pytagsfs.specialfile.logfile import VirtualLogFile
from pytagsfs.profiling import enable_profiling
from pytagsfs.multithreading import token_exchange
from pytagsfs import __version__ as version


DEFAULT_VERBOSITY = 'warning'


PLATFORM = platform.system()


if PLATFORM in ('FreeBSD', 'NetBSD', 'OpenBSD', 'Darwin'):
    READ_ONLY_MOUNT_OPTION = 'rdonly'
    UMOUNT_COMMAND = u'umount %s'
else:
    READ_ONLY_MOUNT_OPTION = 'ro'
    UMOUNT_COMMAND = u'fusermount -u %s'


def append_filter(option, opt_str, value, parser, *args, **kwargs):
    if not hasattr(parser.values, 'filters'):
        parser.values.filters = []
    if 'src' in opt_str:
        which = 'src'
    else:
        which = 'dst'
    parser.values.filters.append((which, value))


def operation_on_one_real_path(real_op):
    @return_errno
    @wraps(real_op)
    def wrapper(self, fake_path, *args, **kwargs):
        fake_path = self.decode_fake_path(fake_path)
        real_path = self.encode_real_path(self.get_real_path(fake_path))
        return real_op(real_path, *args, **kwargs)
    return wrapper


def operation_on_two_real_paths(real_op):
    @return_errno
    @wraps(real_op)
    def wrapper(self, fake_path1, fake_path2, *args, **kwargs):
        fake_path1 = self.decode_fake_path(fake_path1)
        fake_path2 = self.decode_fake_path(fake_path2)
        real_path1 = self.encode_real_path(self.get_real_path(fake_path1))
        real_path2 = self.encode_real_path(self.get_real_path(fake_path2))
        return real_op(real_path1, real_path2, *args, **kwargs)
    return wrapper


class FileSystemMappingToRealFilesOptionParser(GroupingOptionParser):
    DEFAULT_OPTIONS = {}
    DEFAULT_OPTIONS['-d'] = {
      'default': False,
      'action': 'store_true',
      'help': 'debug mode; implies -f',
    }
    DEFAULT_OPTIONS['-f'] = {
      'default': False,
      'action': 'store_true',
      'help': 'stay in foreground',
    }
    DEFAULT_OPTIONS['-s'] = {
      'default': False,
      'action': 'store_true',
      'help': 'disable multi-threaded operation',
    }
    DEFAULT_OPTIONS['-r'] = {
      'default': False,
      'action': 'store_true',
      'help': 'mount read-only',
    }

    DEFAULT_OPTION_ORDER = ('-f', '-d', '-s')

    DEFAULT_MOUNT_OPTIONS = {}
    DEFAULT_MOUNT_OPTIONS[READ_ONLY_MOUNT_OPTION] = dict(DEFAULT_OPTIONS['-r'])
    DEFAULT_MOUNT_OPTIONS['iocharset'] = {
      'default': 'utf-8',
      'metavar': 'ENCODING',
      'help':
        'set mounted tree character encoding to ENCODING (default: %default)',
    }
    DEFAULT_MOUNT_OPTIONS['source_iocharset'] = {
      'default': 'utf-8',
      'metavar': 'ENCODING',
      'help':
        'set source directory character encoding to ENCODING '
        '(default: %default)',
    }
    DEFAULT_MOUNT_OPTIONS['srcfilter'] = {
      'action': 'callback',
      'type': 'str',
      'callback': append_filter,
      'metavar': 'EXPR',
      'help': 'add a source path filter as specified by EXPR',
    }
    DEFAULT_MOUNT_OPTIONS['dstfilter'] = {
      'action': 'callback',
      'type': 'str',
      'callback': append_filter,
      'metavar': 'EXPR',
      'help': 'add a destination path filter as specified by EXPR',
    }
    DEFAULT_MOUNT_OPTIONS['debug'] = {
      'default': False,
      'action': 'store_true',
      'help': 'synonym for -d',
    }
    DEFAULT_MOUNT_OPTIONS['verbosity'] = {
      'default': 'warning',
      'help':
        'log file verbosity; one of debug, info, warning, error, critical '
        '(default: %default)',
    }
    DEFAULT_MOUNT_OPTIONS['logsize'] = {
      'type': 'int',
      'default': (1024 * 1024),
      'help': 'length of log file ring buffer, in bytes',
    }
    DEFAULT_MOUNT_OPTIONS['allow_other'] = {
      'action': 'store_true',
      'default': False,
      'help': 'allow access to other users',
    }
    DEFAULT_MOUNT_OPTIONS['allow_root'] = {
      'action': 'store_true',
      'default': False,
      'help': 'allow access to root',
    }
    DEFAULT_MOUNT_OPTIONS['nonempty'] = {
      'action': 'store_true',
      'default': False,
      'help': 'allow mounts over non-empty file/dir',
    }
    DEFAULT_MOUNT_OPTIONS['uid'] = {'help': 'set owner to UID (if supported)'}
    DEFAULT_MOUNT_OPTIONS['gid'] = {'help': 'set group to GID (if supported)'}
    DEFAULT_MOUNT_OPTIONS['profile'] = {
      'action': 'store_true',
      'default': False,
      'help': 'log profiling data',
    }

    DEFAULT_MOUNT_OPTION_ORDER = (
      'srcfilter',
      'dstfilter',
      'iocharset',
      'source_iocharset',
      READ_ONLY_MOUNT_OPTION,
      'allow_other',
      'allow_root',
      'nonempty',
      'uid',
      'gid',
      'verbosity',
      'logsize',
      'debug',
      'profile',
    )

    def __init__(self, *args, **kwargs):
        kwargs['usage'] = '%prog [OPTIONS] {source} {mountpoint}'
        kwargs['version'] = '%%prog version %s' % version
        GroupingOptionParser.__init__(self, *args, **kwargs)
        self.add_default_options()

    def add_default_options(self):
        for opt in self.DEFAULT_OPTION_ORDER:
            kwargs = self.DEFAULT_OPTIONS[opt]
            self.add_option(opt, **kwargs)

        for opt, kwargs in self.DEFAULT_OPTIONS.items():
            if opt not in self.DEFAULT_OPTION_ORDER:
                self.add_option(opt, **kwargs)

        self.add_group(
          '-o',
          title = 'Mount Options',
          help = "mount options (see `Mount Options')",
        )

        for opt in self.DEFAULT_MOUNT_OPTION_ORDER:
            kwargs = self.DEFAULT_MOUNT_OPTIONS[opt]
            self.add_mount_option(opt, **kwargs)

        for opt, kwargs in self.DEFAULT_MOUNT_OPTIONS.items():
            if opt not in self.DEFAULT_MOUNT_OPTION_ORDER:
                self.add_mount_option(opt, **kwargs)

    def add_mount_option(self, option, **kwargs):
        if 'group' in kwargs:
            raise AssertionError
        return self.add_option(option, group = '-o', **kwargs)

    def parse_args(self, *args, **kwargs):
        retval = GroupingOptionParser.parse_args(self, *args, **kwargs)
        if not hasattr(self.values.o, 'filters'):
            self.values.o.filters = []
        return retval


class FrozenPath(object):
    real_path = None
    count = None

    def __init__(self, real_path):
        self.real_path = real_path
        self.count = 0

    def increment(self):
        self.count = self.count + 1
        return self.count

    def decrement(self):
        if self.count == 0:
            raise AssertionError('Will not decrement count below zero.')
        self.count = self.count - 1
        return self.count


class FileSystemMappingToRealFiles(FileSystem):
    argv = None
    user_encoding = None
    cmdline_arguments = None
    cmdline_parser = None

    debug = None
    foreground = None
    verbosity = None
    allow_other = None
    allow_root = None
    nonempty = None
    uid = None
    gid = None
    readonly = None
    multithreaded = None
    logsize = None
    iocharset = None
    source_iocharset = None
    profile = None
    path_filters = None
    source_tree_path = None
    mount_point = None

    fuse_cmdline_arguments = None

    source_tree_rep = None
    truncated_paths = None
    frozen_path_mappings = None

    max_open_files = 1024
    open_files = None
    read_only_files_by_fake_path = None

    subtype = None

    verbosities = {
      'debug': DEBUG,
      'info': INFO,
      'warning': WARNING,
      'error': ERROR,
      'critical': CRITICAL,
    }

    def __init__(self):
        self.truncated_paths = {}
        self.frozen_path_mappings = {}

        self.open_files = (self.max_open_files + 1) * [None]
        self.read_only_files_by_fake_path = {}

        self.cmdline_parser = self.get_cmdline_parser()

        super(FileSystemMappingToRealFiles, self).__init__()

    def get_cmdline_parser(self):
        return FileSystemMappingToRealFilesOptionParser()

    def main(self, argv):
        self.argv = argv
        try:
            self.parse()
        except OptParseError, e:
            self.cmdline_parser.error(unicode(e))
        self.pre_init()
        fuse = TokenFuse(self)
        fuse.parse(self.fuse_cmdline_arguments)
        return fuse.main()

    def parse(self):
        # locale.getpreferredencoding is not necessarily thread-safe, so we
        # call it here before any threads might be forked:
        self.user_encoding = locale.getpreferredencoding()

        self.cmdline_arguments = self.argv[1:]
        opts, args = self.cmdline_parser.parse_args(self.cmdline_arguments)

        if len(args) < 2:
            raise OptParseError('too few arguments')
        if len(args) > 2:
            raise OptParseError('too many arguments')

        self.process_options(opts, args)
        self.build_fuse_cmdline_arguments()

    def build_fuse_cmdline_arguments(self):
        self.fuse_cmdline_arguments = [
          '-o', 'default_permissions',
          '-o', 'entry_timeout=0',
          '-o', 'negative_timeout=0',
          '-o', 'attr_timeout=0',
        ]

        if PLATFORM == 'Darwin':
            self.fuse_cmdline_arguments.extend([
              '-o', 'nolocalcaches',
              '-o', 'noreadahead',
              '-o', 'noubc',
              '-o', 'novncache',
            ])
        else:
            self.fuse_cmdline_arguments.extend([
              '-o', 'max_readahead=0',
            ])

        if self.subtype:
            self.fuse_cmdline_arguments.extend(
              ['-o', 'subtype=%s' % self.subtype])

        if self.readonly:
            self.fuse_cmdline_arguments.extend(['-o', READ_ONLY_MOUNT_OPTION])

        if self.debug:
            self.fuse_cmdline_arguments.append('-d')

        if self.foreground:
            self.fuse_cmdline_arguments.append('-f')

        if not self.multithreaded:
            self.fuse_cmdline_arguments.append('-s')

        if self.allow_other:
            self.fuse_cmdline_arguments.extend(['-o', 'allow_other'])

        if self.allow_root:
            self.fuse_cmdline_arguments.extend(['-o', 'allow_root'])

        if self.nonempty:
            self.fuse_cmdline_arguments.extend(['-o', 'nonempty'])

        if self.uid is not None:
            self.fuse_cmdline_arguments.extend(
              ['-o', 'uid=%s' % str(self.uid)])

        if self.gid is not None:
            self.fuse_cmdline_arguments.extend(
              ['-o', 'gid=%s' % str(self.gid)])

        self.fuse_cmdline_arguments.extend([
          '-o', 'fsname=%s' % self.source_tree_path.encode(self.user_encoding)])

        self.fuse_cmdline_arguments.append(
          self.mount_point.encode(self.user_encoding))

    def process_options(self, opts, args):
        self.debug = (opts.d or opts.o.debug)

        self.allow_other = opts.o.allow_other
        self.allow_root = opts.o.allow_root
        self.nonempty = opts.o.nonempty
        self.uid = opts.o.uid
        self.gid = opts.o.gid

        if not self.debug:
            self.foreground = opts.f
        else:
            self.foreground = True

        self.readonly = (opts.r or getattr(opts.o, READ_ONLY_MOUNT_OPTION))
        self.multithreaded = (not opts.s)

        if opts.o.verbosity is not None:
            if self.debug:
                log_warning(
                  u'warning: option debug overrides user-specified verbosity'
                )
                self.verbosity = self.verbosities['debug']
            else:
                try:
                    self.verbosity = self.verbosities[opts.o.verbosity]
                except KeyError:
                    raise OptParseError(
                      'verbosity should be one of %s' % ', '.join(
                        self.verbosities.keys())
                    )
        elif not self.debug:
            self.verbosity = self.verbosities[DEFAULT_VERBOSITY]

        self.logsize = opts.o.logsize

        self.iocharset = opts.o.iocharset
        self.source_iocharset = opts.o.source_iocharset

        self.profile = opts.o.profile

        self.path_filters = []
        for which, expr in opts.o.filters:
            real = (which == 'src')
            self.path_filters.append((expr, real))

        self.source_tree_path = os.path.abspath(
          unicode(args[0], self.user_encoding))
        self.mount_point = os.path.abspath(
          unicode(args[1], self.user_encoding))

    def pre_init(self):
        if self.profile:
            enable_profiling()

        set_logsize(self.logsize)

        set_log_level(self.verbosity)
        if self.foreground:
            enable_stderr()

        log_warning(u'pytagsfs version %s', version)
        log_warning(u'command-line arguments: %s', str(self.cmdline_arguments))
        log_warning(
          u'fuse command-line arguments: %s',
          unicode(self.fuse_cmdline_arguments),
        )

        self.source_tree_rep = self.build_source_tree_rep()
        self.multithreaded = (
          self.multithreaded and
          self.source_tree_rep.supports_threads()
        )
        log_warning(u'multithreaded = %s', self.multithreaded)

        # See note in init.
        if self.source_tree_rep.can_handle_fork():
            log_warning(
              u'source tree representation can handle fork, '
              u'calling source_tree_rep.start in pre_init'
            )
            self.source_tree_rep.start()

    def build_source_tree_rep(self):
        raise NotImplementedError

    def encode_fake_path(self, s):
        return s.encode(self.iocharset)

    def decode_fake_path(self, s):
        return s.decode(self.iocharset)

    def encode_real_path(self, s):
        return self.source_tree_rep.source_tree.encode(s)

    def decode_real_path(self, s):
        return self.source_tree_rep.source_tree.decode(s)

    def get_next_fh(self):
        for fh, file_instance in enumerate(self.open_files):
            if file_instance is None:
                return fh
        raise ValueError

    def post_process_stat_result(self, stat_result):
        # Set st_ino and st_dev to zero since they are meaningless for us.
        return os.stat_result((
          stat_result.st_mode,
          0,
          0,
          stat_result.st_nlink,
          stat_result.st_uid,
          stat_result.st_gid,
          stat_result.st_size,
          stat_result.st_atime,
          stat_result.st_mtime,
          stat_result.st_ctime,
        ))

    def post_process_statvfs_result(self, statvfs_result):
        return os.statvfs_result((
          statvfs_result.f_bsize,
          statvfs_result.f_frsize,
          statvfs_result.f_blocks,
          statvfs_result.f_bfree,
          statvfs_result.f_bavail,
          statvfs_result.f_files,
          statvfs_result.f_ffree,
          statvfs_result.f_favail,
          # f_flag
          0,
          statvfs_result.f_namemax,
        ))

    def get_real_path(self, fake_path):
        try:
            return self.frozen_path_mappings[fake_path].real_path
        except KeyError:
            return self.source_tree_rep.get_real_path(fake_path)

    def get_read_only_file_instance(self, fake_path, flags, truncate_to):
        return ReadOnlyFile(self, fake_path, flags, truncate_to = truncate_to)

    def get_read_write_file_instance(self, fake_path, flags, truncate_to):
        return ReadWriteFile(self, fake_path, flags, truncate_to = truncate_to)

################################################################################

    # access
    # bmap

    chmod = operation_on_one_real_path(token_exchange.token_released(os.chmod))

    chown = operation_on_one_real_path(token_exchange.token_released(os.chown))

    # create

    def destroy(self):
        self.source_tree_rep.stop()

    @return_errno
    def fgetattr(self, fake_path, fh):
        return self.post_process_stat_result(self.open_files[fh].fgetattr())

    @return_errno
    def flush(self, fake_path, fh):
        return self.open_files[fh].flush()

    @return_errno
    def fsync(self, fake_path, datasync, fh):
        return self.open_files[fh].fsync(datasync)

    # fsyncdir

    @return_errno
    def ftruncate(self, fake_path, len, fh):
        return self.open_files[fh].ftruncate(len)

    @return_errno
    def getattr(self, fake_path):
        fake_path = self.decode_fake_path(fake_path)
        try:
            real_path = self.frozen_path_mappings[fake_path].real_path
        except KeyError:
            # Path is not frozen.
            stat_result = self.source_tree_rep.getattr(fake_path)

            st_size = stat_result.st_size
            try:
                truncate_to = self.truncated_paths[fake_path]
            except KeyError:
                pass
            else:
                if st_size > truncate_to:
                    st_size = truncate_to

            stat_result = os.stat_result((
              stat_result.st_mode,
              stat_result.st_ino,
              stat_result.st_dev,
              stat_result.st_nlink,
              stat_result.st_uid,
              stat_result.st_gid,
              st_size,
              stat_result.st_atime,
              stat_result.st_mtime,
              stat_result.st_ctime,
            ))
        else:
            # Path is frozen.
            token_exchange.release_token()
            try:
                stat_result = os.lstat(real_path)
            finally:
                token_exchange.reacquire_token()

        return self.post_process_stat_result(stat_result)

    # getxattr

    def init(self):
        # We prefer to call source_tree_rep.start prior to the filesystem
        # process detaching from the user's shell, since the initial scan of
        # the source files can take some time and detaching before it is
        # complete leads to confusion as to whether the filesystem is hung or
        # not.  Some SourceTreeMonitor implementations can't carry across the
        # fork call, though, so this provides a mechanism for start to be called
        # after that transition occurs.  If this is not the case,
        # source_tree_rep.start is called at the end of pre_init, rather than
        # here.

        if not self.source_tree_rep.can_handle_fork():
            log_warning(
              u"source tree representation can't handle fork, "
              u'calling source_tree_rep.start in init'
            )
            self.source_tree_rep.start()

    # link
    # listxattr
    # lock

    @return_errno
    def mkdir(self, fake_path, mode):
        fake_path = self.decode_fake_path(fake_path)
        self.source_tree_rep.add_directory(fake_path)
        return 0

    # mknod

    @return_errno
    def open(self, fake_path, flags):
        # When opening a file for writing, the virtual path is "frozen" so
        # that, if a write will cause the path to change, the same source
        # file continues to be accessible via the same virtual path.  Once
        # the file is closed (i.e. is not open for writing by any processes),
        # the path is "thawed" and the virtual path may change at that point.

        fake_path = self.decode_fake_path(fake_path)
        is_writable = (os.O_RDWR | os.O_WRONLY) & flags

        if is_writable:
            truncate_to = self.truncated_paths.pop(fake_path, None)
            file_instance = self.get_read_write_file_instance(
              fake_path, flags, truncate_to)

            if truncate_to is not None:
                for _file_instance in (
                  self.read_only_files_by_fake_path.get(fake_path, ())
                ):
                    _file_instance.del_truncate_to()

        else:
            truncate_to = self.truncated_paths.get(fake_path, None)
            file_instance = self.get_read_only_file_instance(
              fake_path,
              flags,
              truncate_to,
            )

        fh = self.get_next_fh()
        self.open_files[fh] = file_instance

        if is_writable:
            if fake_path not in self.frozen_path_mappings:
                log_debug(
                  u'open: freezing path: %s, %s',
                  fake_path,
                  file_instance.real_path,
                )
                self.frozen_path_mappings[fake_path] = FrozenPath(
                  file_instance.real_path
                )

            log_debug(
              u'open: incrementing count for frozen path: %s, %s',
              fake_path,
              file_instance.real_path,
            )
            self.frozen_path_mappings[fake_path].increment()

        else:
            self.read_only_files_by_fake_path.setdefault(
              fake_path,
              [],
            ).append(file_instance)

        return fh

    # opendir

    @return_errno
    def read(self, fake_path, length, offset, fh):
        return self.open_files[fh].read(length, offset)

    @return_errno
    def readdir(self, fake_path, fh):
        fake_path = self.decode_fake_path(fake_path)
        entries = [
          self.encode_fake_path(e)
          for e in self.source_tree_rep.get_entries(fake_path)
        ]
        return entries

    # readlink

    @return_errno
    def release(self, fake_path, flags, fh):
        fake_path = self.decode_fake_path(fake_path)
        is_writable = (os.O_RDWR | os.O_WRONLY) & flags

        file_instance = self.open_files[fh]
        self.open_files[fh] = None

        if is_writable:
            log_debug(
              'release: decrementing count for frozen path: %s, %s',
              fake_path,
              file_instance.real_path,
            )
            if not self.frozen_path_mappings[fake_path].decrement():
                log_debug(
                  'release: thawing path: %s, %s',
                  fake_path,
                  file_instance.real_path,
                )
                del self.frozen_path_mappings[fake_path]

        else:
            self.read_only_files_by_fake_path[fake_path].remove(file_instance)
            if not self.read_only_files_by_fake_path[fake_path]:
                del self.read_only_files_by_fake_path[fake_path]

        file_instance.release(flags)
        return 0

    # releasedir
    # removexattr

    @return_errno
    def rename(self, old_fake_path, new_fake_path):
        old_fake_path = self.decode_fake_path(old_fake_path)
        new_fake_path = self.decode_fake_path(new_fake_path)
        self.source_tree_rep.rename_path(old_fake_path, new_fake_path)
        return 0

    @return_errno
    def rmdir(self, fake_path):
        fake_path = self.decode_fake_path(fake_path)
        self.source_tree_rep.remove_directory(fake_path)
        return 0

    # setxattr

    @return_errno
    def statfs(self):
        # Interestingly, os.statvfs seems to be converting unicode paths to
        # ASCII/sys.getdefaultencoding().  Other os.* functions seem to deal
        # with this differently, as they don't fail with unicode paths (but
        # os.statvfs does).  This may vary from one Python version to the next.
        statvfs_result = os.statvfs(
          self.source_tree_rep.source_tree.encode(
            self.source_tree_rep.source_tree.root))
        return self.post_process_statvfs_result(statvfs_result)

    # symlink

    @return_errno
    def truncate(self, fake_path, len):
        # truncate semantics are designed to accomodate programs that truncate
        # files before opening them for writing.  Generally speaking, this is
        # poor form (as it is better to open the file for writing and then use
        # ftruncate), but shell scripts (for instance) may not have a lot of
        # choice on the matter.  If the source file were immediately truncated,
        # the virtual file might change paths at once, and the program would
        # not have an opportunity to write the new file content.
        #
        # Thus, if a file that has not been opened for writing is truncated,
        # the truncation length is stored and filesystem operations behave as
        # though that is the file's length (if it is shorter than the real
        # length).  When the file has been opened for writing, the source file
        # is actually truncated (but note that the path is now "frozen", so
        # the file will continue to be accessible from the same virtual path
        # until it is closed -- see the open method).
        #
        # Note that if the file has already been opened for writing (even by a
        # different process), the source file is truncated immediately.  There
        # is one case that is not handled well due to an unavoidable race
        # condition.  If the file is opened for writing by process A,
        # process B truncates the file (preparing to write to it), but A closes
        # it before B can open it, the virtual path may no longer be
        # accessible by the time B finally does open the file.

        fake_path = self.decode_fake_path(fake_path)

        # If the path is frozen, we truncate the source file immediately.
        try:
            real_path = self.frozen_path_mappings[fake_path].real_path
        except KeyError:
            pass
        else:
            real_path_encoded = self.encode_real_path(real_path)
            token_exchange.release_token()
            try:
                ftruncate_path(real_path_encoded, len)
            finally:
                token_exchange.reacquire_token()
            return

        # Otherwise, save the new length (if shorter than the existing value).
        truncate_to = self.truncated_paths.get(fake_path, None)
        if (truncate_to is None) or (len < truncate_to):
            self.truncated_paths[fake_path] = len

            for file_instance in (
              self.read_only_files_by_fake_path.get(fake_path, ())
            ):
                file_instance.set_truncate_to(len)

    # unlink

    @return_errno
    def utimens(self, fake_path, times):
        fake_path = self.decode_fake_path(fake_path)
        self.source_tree_rep.utime(fake_path, times)
        return 0

    @return_errno
    def write(self, fake_path, buf, offset, fh):
        return self.open_files[fh].write(buf, offset)


################################################################################


class PyTagsFileSystemOptionParser(FileSystemMappingToRealFilesOptionParser):
    DEFAULT_MOUNT_OPTIONS = dict(
      FileSystemMappingToRealFilesOptionParser.DEFAULT_MOUNT_OPTIONS)

    DEFAULT_MOUNT_OPTIONS['sourcetreerep'] = {
      'default': 
        'pytagsfs.sourcetreerep.pollinline.PollInLineSourceTreeRepresentation',
      'help': SUPPRESS_HELP,
    }
    DEFAULT_MOUNT_OPTIONS['pathstore'] = {
      'default': 'pytagsfs.pathstore.pytypes.PyTypesPathStore',
      'help': SUPPRESS_HELP,
    }
    DEFAULT_MOUNT_OPTIONS['sourcetreemon'] = {
      'default': None,
      'help': SUPPRESS_HELP,
    }
    DEFAULT_MOUNT_OPTIONS['metastores'] = {
      'default': ';'.join([
        'pytagsfs.metastore.path.PathMetaStore',
        'pytagsfs.metastore.mutagen_.MutagenFileMetaStore',
      ]),
      'help': SUPPRESS_HELP,
    }
    DEFAULT_MOUNT_OPTIONS['format'] = {
      'default': u'%s%%f' % unicode_path_sep,
      'metavar': 'FORMAT',
      'help': 'set destination path format string (default: %default)',
    }
    DEFAULT_MOUNT_OPTIONS['nocache'] = {
      'action': 'store_true',
      'default': False,
      'help': 'disable path property caching',
    }

    DEFAULT_MOUNT_OPTION_ORDER = (
      'format',
      'srcfilter',
      'dstfilter',
      'iocharset',
      'source_iocharset',
      READ_ONLY_MOUNT_OPTION,
      'allow_other',
      'allow_root',
      'nonempty',
      'uid',
      'gid',
      'nocache',
      'verbosity',
      'logsize',
      'debug',
      'profile',
    )


class PyTagsFileSystem(
  SpecialFileFileSystemMixin,
  FileSystemMappingToRealFiles,
):
    special_file_classes = [VirtualLogFile]

    source_tree_rep_cls_dotted_name = None
    path_store_cls_dotted_name = None
    source_tree_mon_cls_dotted_name = None
    meta_store_cls_dotted_names = None
    nocache = None

    format_string = None
    format_string_parts = None

    subtype = 'pytagsfs'

    def get_cmdline_parser(self):
        return PyTagsFileSystemOptionParser()

    def process_options(self, opts, args):
        super(PyTagsFileSystem, self).process_options(opts, args)

        self.source_tree_rep_cls_dotted_name = opts.o.sourcetreerep
        self.path_store_cls_dotted_name = opts.o.pathstore
        self.source_tree_mon_cls_dotted_name = opts.o.sourcetreemon
        self.meta_store_cls_dotted_names = opts.o.metastores
        self.nocache = opts.o.nocache

        self.format_string = opts.o.format

        # format string must not end with a /
        self.format_string = self.format_string.rstrip(unicode_path_sep)

        # format_string must start with a /
        if not self.format_string.startswith(unicode_path_sep):
            self.format_string = '%s%s' % (
              unicode_path_sep, self.format_string)

        # format_string should not contain multiple consecutive /'s
        self.format_string = re.sub(
          ur'%s{2,}' % unicode_path_sep, unicode_path_sep, self.format_string)

        self.format_string_parts = split_path(self.format_string)

    @classmethod
    def get_meta_store(cls, meta_store_cls_dotted_names):
        meta_store_cls_dotted_names = meta_store_cls_dotted_names.split(';')
        meta_store_classes = [
          get_obj_by_dotted_name(cls_name)
          for cls_name in meta_store_cls_dotted_names
        ]
        if len(meta_store_classes) == 1:
            meta_store = meta_store_classes[0]()
        else:
            meta_store = DelegateMultiMetaStore([
              cls() for cls in meta_store_classes])
        return meta_store

    def build_source_tree_rep(self):
        substitution_patterns = [
          SubstitutionPattern(p) for p in self.format_string_parts
        ]

        source_tree_rep_cls = get_obj_by_dotted_name(
          self.source_tree_rep_cls_dotted_name)
        path_store_cls = get_obj_by_dotted_name(
          self.path_store_cls_dotted_name)

        if self.source_tree_mon_cls_dotted_name is not None:
            source_tree_mon_cls_dotted_names = [
              self.source_tree_mon_cls_dotted_name]
        else:
            source_tree_mon_cls_dotted_names = list(SOURCE_TREE_MONITORS)

        monitor = None
        for source_tree_mon_cls_dotted_name in (
          source_tree_mon_cls_dotted_names):
            log_debug(
              'trying source tree monitor class %s',
              source_tree_mon_cls_dotted_name,
            )
            try:
                monitor = get_source_tree_monitor(
                  source_tree_mon_cls_dotted_name)
            except ComponentError, e:
                log_warning(
                  u'WARNING: failed to initialize source tree monitor %s: %s',
                  source_tree_mon_cls_dotted_name,
                  unicode(e),
                )
            else:
                break

        if monitor is None:
            raise OptParseError('No supported source tree monitor found.')

        meta_store = self.get_meta_store(self.meta_store_cls_dotted_names)

        if self.nocache:
            cache = None
        else:
            cache = PathPropCache()

        log_warning(
          u'source_tree_rep_cls: %s.%s',
          source_tree_rep_cls.__module__,
          source_tree_rep_cls.__name__,
        )
        log_warning(
          u'path_store_cls: %s.%s',
          path_store_cls.__module__,
          path_store_cls.__name__,
        )
        log_warning(
          u'source_tree_mon_cls: %s.%s',
          monitor.__class__.__module__,
          monitor.__class__.__name__,
        )

        if not self.readonly:
            if not monitor.supports_writes():
                raise OptParseError(
                  ('Source tree monitor does not support writes. '
                   'You must mount read-only with -o %s.'
                  ) % READ_ONLY_MOUNT_OPTION
                )

        return source_tree_rep_cls(
          meta_store = meta_store,
          substitution_patterns = substitution_patterns,
          path_store = path_store_cls(),
          source_tree = SourceTree(
            root = self.source_tree_path,
            iocharset = self.source_iocharset,
          ),
          monitor = monitor,
          cache = cache,
          filters = self.path_filters,
          debug = self.debug,
        )
