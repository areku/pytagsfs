# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import re
from cStringIO import StringIO


class SegmentContainer(list):
    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self).decode()

    def __repr__(self):
        return '%s(%s)' % (
          self.__class__.__name__,
          super(SegmentContainer, self).__repr__(),
        )


class Regex(SegmentContainer):
    def __str__(self):
        return self.get_string().encode('utf-8')

    def __unicode__(self):
        return self.get_string()

    def get_string(self):
        context = Context()
        for segment in self:
            context.add(segment)
        return context.get_value()

    def get_regex(self):
        return re.compile(self.get_string())


class Context(object):
    encoding = 'utf-8'

    named_group_start_regex = re.compile(r'(?<!\\)\(\?P\<(?P<name>.*?[^\\])\>')
    group_start_regex = re.compile(r'(?<!\\)\((?!\?:)')

    _content = None

    def __init__(self, initial_content = ''):
        self._content = StringIO()
        self.write(initial_content)

    def __unicode__(self):
        return self.get_value()

    def __str__(self):
        return self._content.getvalue()

    def __repr__(self):
        value = self.get_value()
        if value:
            arg = repr(value)
        else:
            arg = ''
        return '%s(%s)' % (self.__class__.__name__, arg)

    def get_named_group_names(self):
        for mo in self.named_group_start_regex.finditer(self.get_value()):
            yield mo.group('name')

    def get_number_of_groups(self):
        return len(self.group_start_regex.findall(self.get_value()))

    def add(self, segment):
        segment.eval(self)

    def write(self, s):
        if isinstance(s, unicode):
            s = s.encode(self.encoding)
        self._content.write(s)

    def get_value(self):
        return self._content.getvalue().decode(self.encoding)


class Segment(object):
    def eval(self, context):
        raise NotImplementedError


class SimpleExpression(Segment):
    expression = None

    def __init__(self, expression):
        self.expression = expression

    def eval(self, context):
        context.write(self.expression)


class CompoundSegment(Segment, SegmentContainer):
    def eval(self, context):
        for segment in self:
            context.add(segment)


class Group(CompoundSegment):
    def eval(self, context):
        context.write('(')
        super(Group, self).eval(context)
        context.write(')')


class NamedGroup(CompoundSegment):
    name = None

    def __init__(self, name, *args):
        self.name = name
        super(NamedGroup, self).__init__(*args)

    def __str__(self):
        return repr(self)

    def __unicode__(self):
        return repr(self).decode()

    def __repr__(self):
        return '%s(%s, %s)' % (
          self.__class__.__name__,
          repr(self.name),
          super(SegmentContainer, self).__repr__(),
        )

    def eval(self, context):
        if self.name in context.get_named_group_names():
            context.write(r'(?P=%s)' % self.name)
        else:
            context.write(r'(?P<%s>' % self.name)
            super(NamedGroup, self).eval(context)
            context.write(')')
