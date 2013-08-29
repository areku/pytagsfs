# Copyright (c) 2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import sys
from optparse import (
  Option,
  OptionParser,
  OptionContainer,
  OptParseError,
  BadOptionError,
  HelpFormatter,
  IndentedHelpFormatter,
)

class GroupingOption(Option):
    '''
    An option that establishes a group, i.e. `-o' in `-o foo=bar'.
    '''
    group_parser = None
    title = None

    def __init__(self, *args, **kwargs):
        self.group_parser = kwargs['group_parser']
        del kwargs['group_parser']

        self.title = kwargs['title']
        del kwargs['title']

        if 'metavar' not in kwargs:
            kwargs['metavar'] = 'opt,opt,...'

        Option.__init__(self, *args, **kwargs)

        self._check_dest()

    def take_action(self, action, dest, opt, value, values, parser):
        self.group_parser.take_grouping_option_action(
          self, action, dest, opt, value, values, parser)

class GroupOption(Option):
    '''
    An option within a group, i.e. `foo' in `-o foo=bar'.
    '''
    group = None

    def __init__(self, opt, *args, **kwargs):
        if 'dest' not in kwargs:
            # Override default dest, which would strip first two characters:
            kwargs['dest'] = opt.replace('-', '_')

        self.group = kwargs['group']
        del kwargs['group']

        Option.__init__(self, opt, *args, **kwargs)

    # FIXME: Overriding a private method; may be fragile.
    def _set_opt_strings(self, opts):
        for opt in opts:
            if len(opt) < 1:
                raise OptionError('invalid option string %r: ' % opt, self)
            else:
                self._long_opts.append(opt)

class GroupingOptionParser(OptionParser):
    '''
    An option parser capable of having grouping options.

    >>> class NonExitingGroupingOptionParser(GroupingOptionParser):
    ...     def error(self, msg):
    ...         raise OptParseError(msg)

    >>> p = NonExitingGroupingOptionParser(prog = 'optgroup')

    >>> o = p.add_group(
    ...   '-o',
    ...   help = "see `Grouped Options' below",
    ...   title = 'Grouped Options'
    ... )

    >>> o = p.add_option(
    ...   'foo',
    ...   group = '-o',
    ...   help = 'set foo value (default %default)',
    ...   default = 'default_foo',
    ... )

    >>> o = p.add_option(
    ...   'bar',
    ...   group = '-o',
    ...   action = 'store_true',
    ...   default = False,
    ...   help = 'enable bar',
    ... )

    >>> opts, args = p.parse_args([])
    >>> opts.o.foo
    'default_foo'
    >>> opts.o.bar
    False

    >>> opts, args = p.parse_args(['boink'])
    >>> opts.o.foo
    'default_foo'
    >>> opts.o.bar
    False
    >>> args
    ['boink']

    >>> opts, args = p.parse_args(['-o', 'foo=boink'])
    >>> opts.o.foo
    'boink'

    >>> opts, args = p.parse_args(['-o', 'foo'])
    Traceback (most recent call last):
    ...
    OptParseError: option foo requires an argument

    >>> opts, args = p.parse_args(['-o', 'foo', 'boink'])
    Traceback (most recent call last):
    ...
    OptParseError: option foo requires an argument

    >>> opts, args = p.parse_args(['-o', 'foo,bar'])
    Traceback (most recent call last):
    ...
    OptParseError: option foo requires an argument

    '''

    # Python 2.5's OptionParser module introduced some new formatting (note
    # capitilization), so we have to test conditionally:
    if sys.version_info[0:2] >= (2, 5):
        __doc__ = __doc__ + '''
        >>> print p.format_help()
        Usage: optgroup [options]
        <BLANKLINE>
        Options:
          -h, --help      show this help message and exit
          -o opt,opt,...  see `Grouped Options' below
        <BLANKLINE>
        Grouped Options:
          foo=FOO         set foo value (default default_foo)
          bar             enable bar
        <BLANKLINE>
        '''
    else:
        __doc__ = __doc__ + '''
        >>> print p.format_help()
        usage: optgroup [options]
        <BLANKLINE>
        options:
          -h, --help      show this help message and exit
          -o opt,opt,...  see `Grouped Options' below
        <BLANKLINE>
        Grouped Options:
          foo=FOO         set foo value (default default_foo)
          bar             enable bar
        <BLANKLINE>
        '''

    groups = None
    group_args = None

    def __init__(self, *args, **kwargs):
        self.groups = {}

        if 'formatter' not in kwargs:
            kwargs['formatter'] = IndentedGroupingOptionHelpFormatter()

        OptionParser.__init__(self, *args, **kwargs)

    def parse_args(self, *args, **kwargs):
        self.group_args = {}
        for group in self.groups:
            self.group_args[group] = []

        values, final_args = OptionParser.parse_args(self, *args, **kwargs)

        for group, args in self.group_args.items():
            # Make a copy of args because it will be modified by the following
            # call and we want to save self.group_args so the caller can get
            # information about what command-line options were used.
            args = list(args)

            group_values, group_args = self.groups[group].parse_args(args)
            assert not group_args
            setattr(
              values, self.groups[group].grouping_option.dest, group_values)

        return values, final_args

    def add_group(self, group, **kwargs):
        assert 'type' not in kwargs

        self.groups[group] = OptionGroupParser(parent_parser = self)

        kwargs['type'] = 'str'
        kwargs['group_parser'] = self.groups[group]

        option = GroupingOption(group, **kwargs)

        self.groups[group].grouping_option = option

        return OptionParser.add_option(self, option)

    def add_option(self, *args, **kwargs):
        if isinstance(args[0], GroupingOption):
            raise OptParseError('use add_group to add GroupingOptions')

        try:
            group = kwargs['group']
        except KeyError:
            return OptionParser.add_option(self, *args, **kwargs)

        opt_str = args[0]

        if group not in self.groups:
            raise OptParseError(
              'GroupingOption must be added before GroupOptions can be')

        option = GroupOption(opt_str, **kwargs)
        option = self.groups[group].add_option(option)

        return option

    def take_grouping_option_action(
      self, option, action, dest, opt, value, values, parser):
        if value is None:
            raise ValueError('value must not be None')
        self.group_args[opt].append(value)

    def format_option_help(self, formatter = None):
        if formatter is None:
            formatter = self.formatter

        help_sections = [
          OptionParser.format_option_help(self, formatter = formatter)]

        for group in self.groups:
            old_parser = formatter.parser
            formatter.set_parser(self.groups[group])
            try:
                help_sections.append(
                  self.groups[group].format_option_help(formatter = formatter))
            finally:
                formatter.set_parser(old_parser)

        return '\n'.join(help_sections)

class OptionGroupParser(OptionParser):
    '''
    An option parser that parses group options for a single grouping option.
    '''

    parent_parser = None
    grouping_option = None

    def __init__(self, *args, **kwargs):
        self.parent_parser = kwargs['parent_parser']
        del kwargs['parent_parser']

        kwargs['add_help_option'] = False

        OptionParser.__init__(self, *args, **kwargs)

    def error(self, msg):
        return self.parent_parser.error(msg)

    def parse_args(self, args, values = None):
        if values is None:
            values = self.get_default_values()

        self.values = values

        # We're deliberately not handling exceptions here:
        stop = self._process_args(args, values)

        # We never have args left over, so pass [] as args:
        return self.check_values(values, [])

    def _process_args(self, args, values):
        while args:
            self._process_long_opt(args, values)

    def _process_long_opt(self, args, values):
        for arg in args.pop(0).split(','):
            try:
                opt, value = arg.split('=')
            except ValueError:
                opt, value = arg, None

            try:
                option = self._long_opt[opt]
            except KeyError:
                raise BadOptionError(opt)

            if option.takes_value():
                if option.nargs != 1:
                    raise OptParseError(
                      'grouped options must only take a single argument')
                if value is None:
                    self.error('option %s requires an argument' % opt)

            option.process(opt, value, values, self)

    # FIXME: Overriding a private method; may be fragile.
    def _check_conflict(self, option):
        conflict_opts = []
        for opt in option._short_opts:
            if self._short_opt.has_key(opt):
                conflict_opts.append((opt, self._short_opt[opt]))
        for opt in option._long_opts:
            if self._long_opt.has_key(opt):
                conflict_opts.append((opt, self._long_opt[opt]))

        if conflict_opts:
            handler = self.conflict_handler
            if handler == "error":
                raise OptionConflictError(
                    "conflicting option string(s): %s"
                    % ", ".join([co[0] for co in conflict_opts]),
                    option)
            elif handler == "resolve":
                for (opt, c_option) in conflict_opts:
                    # This is the part where we differ from the method being
                    # overridden.  We do this because our options don't start
                    # with "--", so we have to force the use of _long_opts.
                    c_option._long_opts.remove(opt)
                    del self._long_opt[opt]
                    if not (c_option._short_opts or c_option._long_opts):
                        c_option.container.option_list.remove(c_option)

    def take_grouping_option_action(
      self, option, action, dest, opt, value, values, parser):
        self.parent_parser.take_grouping_option_action(
          option, action, dest, opt, value, values, parser)

    def format_option_help(self, formatter = None):
        if formatter is None:
            formatter = self.formatter
        formatter.store_option_strings(self)
        result = []
        result.append(formatter.format_heading(self.grouping_option.title))
        formatter.indent()
        if self.option_list:
            result.append(OptionContainer.format_option_help(self, formatter))
            result.append("\n")
        for group in self.option_groups:
            result.append(group.format_help(formatter))
            result.append("\n")
        formatter.dedent()
        # Drop the last "\n", or the header if no options or option groups:
        return "".join(result[:-1])

class GroupingOptionHelpFormatter(HelpFormatter):
    def __init__(self, *args, **kwargs):
        HelpFormatter.__init__(self, *args, **kwargs)
        self.help_position = 0

    def format_option_strings(self, option):
        if isinstance(option, GroupOption):
            if option.takes_value():
                metavar = option.metavar or option.dest.upper()
                return '%s=%s' % (
                  option._long_opts[0],
                  metavar,
                )
            else:
                return option._long_opts[0]
        else:
            return HelpFormatter.format_option_strings(self, option)

    def store_option_strings(self, parser):
        old_help_position = self.help_position
        HelpFormatter.store_option_strings(self, parser)
        new_help_position = self.help_position

        if new_help_position < old_help_position:
            self.help_position = old_help_position

class IndentedGroupingOptionHelpFormatter(
  IndentedHelpFormatter, GroupingOptionHelpFormatter):
    def __init__(self, *args, **kwargs):
        IndentedHelpFormatter.__init__(self, *args, **kwargs)
        self.help_position = 0

    format_option_strings = GroupingOptionHelpFormatter.format_option_strings
    store_option_strings = GroupingOptionHelpFormatter.store_option_strings
