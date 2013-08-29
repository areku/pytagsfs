# Copyright (c) 2007-2008 Forest Bond.
# This file is part of the pytagsfs software package.
#
# pytagsfs is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License version 2 as published by the Free
# Software Foundation.
#
# A copy of the license has been included in the COPYING file.

import re, copy

from pytagsfs.regex import (
  Regex,
  Group,
  SimpleExpression,
  CompoundSegment,
  NamedGroup,
)
from pytagsfs.exceptions import ErrorSupportingUnicode
from pytagsfs.util import sorted_items


class Error(ErrorSupportingUnicode):
    pass


class PatternSyntaxError(Error):
    problem_area_length = 10
    problem_area_suffix = u'...'

    def __init__(self, pattern, offset):
        self.pattern = pattern
        self.offset = offset

    def __unicode__(self):
        problem_area = self.pattern[
          self.offset:self.offset + self.problem_area_length]
        if len(self.pattern) > (
          self.offset +
          self.problem_area_length +
          len(self.problem_area_suffix)
        ):
            problem_area = '%s%s' % (problem_area, self.problem_area_suffix)
        return u'syntax error in %s near %s' % (
          repr(self.pattern),
          repr(problem_area),
        )


class SplitError(Error):
    def __init__(self, regex_string, split_string):
        self.regex_string = regex_string
        self.split_string = split_string

    def __unicode__(self):
        return u'failed to split string %s with regex %s' % (
          repr(self.split_string), repr(self.regex_string))


class FillError(Error):
    def __init__(self, expression, substitutions, parameters = ()):
        self.expression = expression
        self.substitutions = substitutions
        self.parameters = list(parameters)

    def __unicode__(self):
        s = u'failed to fill expression %s with substitutions %s' % (
          repr(self.expression), repr(self.substitutions))
        if self.parameters is not None:
            s = u'%s (undefined parameters: %s)' % (s, ', '.join([
              repr(p) for p in self.parameters]))
        return s


class Node(object):
    expression = None

    def __init__(self, expression):
        self.expression = expression

    def fill(self, substitutions):
        raise NotImplementedError

    def get_regex_segment(self, substitutions):
        raise NotImplementedError

    @classmethod
    def consume(cls, s):
        raise NotImplementedError


class SectionNode(Node):
    # class attributes
    child_node_types = []

    # instance attributes
    child_nodes = None

    def __init__(self, expression):
        self.expression = expression
        self.child_nodes = self.get_child_nodes()
        super(SectionNode, self).__init__(expression)

    @classmethod
    def register_child_node_type(cls, child_node_type):
        if child_node_type not in cls.child_node_types:
            cls.child_node_types.append(child_node_type)

    def get_regex_segment(self, substitutions):
        segment = CompoundSegment()
        for child_node in self.child_nodes:
            segment.append(child_node.get_regex_segment(substitutions))
        return segment

    def get_contents(self):
        return self.expression

    def get_child_nodes(self):
        return self.get_nodes_from_expression(self.get_contents())

    def get_nodes_from_expression(self, s):
        orig_s = s

        child_nodes = []
        while True:
            if s == '':
                break

            previous_number_of_child_nodes = len(child_nodes)

            for child_node_type in self.child_node_types:
                child_node, s = child_node_type.consume(s)
                if child_node is not None:
                    child_nodes.append(child_node)
                    break
                if s == '':
                    break

            if len(child_nodes) == previous_number_of_child_nodes:
                raise PatternSyntaxError(orig_s, (len(orig_s) - len(s)))
        return child_nodes

    @classmethod
    def consume(cls, s):
        return cls(s), ''

    def fill(self, substitutions):
        return ''.join([
          child_node.fill(substitutions) for child_node in self.child_nodes])

    def get_split_regex(self, substitutions):
        regex = Regex()
        regex.append(SimpleExpression('^'))
        for child_node in self.child_nodes:
            regex.append(child_node.get_regex_segment(substitutions))
        regex.append(SimpleExpression('$'))
        return regex

    def get_splitter(self, substitutions):
        regex = self.get_split_regex(substitutions)
        return Splitter(regex.get_regex(), regex.get_string())

    def iter_child_nodes_recursive(self, nodes = None):
        if nodes is None:
            nodes = self.child_nodes
        for node in nodes:
            yield node
            if hasattr(node, 'iter_child_nodes_recursive'):
                for _node in node.iter_child_nodes_recursive():
                    yield _node


class Splitter(object):
    regex = None
    string = None

    def __init__(self, regex, string):
        self.regex = regex
        self.string = string

    def split(self, s):
        mo = self.regex.match(s)
        if mo is None:
            raise SplitError(self.string, s)
        return mo.groupdict()

    def __eq__(self, other):
        if hasattr(other, 'string'):
            return (self.string == other.string)
        return super(Splitter, self).__eq__(other)


class TextNode(Node):
    def fill(self, substitutions):
        if self.expression is None:
            raise AssertionError
        return self.expression

    def get_regex_segment(self, substitutions):
        return SimpleExpression(re.escape(self.expression))

    @classmethod
    def consume(cls, s):
        index = 0
        while True:
            try:
                char = s[index]
            except IndexError:
                break

            try:
                next_char = s[index + 1]
            except IndexError:
                next_char = None

            if (char == '%') and (next_char != '%'):
                break

            index = index + 1

            if (char == '%') and (next_char == '%'):
                index = index + 1

        if index == 0:
            return None, s

        return cls(s[:index]), s[index:]


class VariableNode(Node):
    # class attributes
    parse_regex_string = None
    parse_regex = None
    modifiers = {
      None: lambda s: s,
      '_': lambda s: s.lower(),
      '^': lambda s: s.upper(),
      '!': lambda s: s.title(),
    }

    # instance attributes
    match_object = None
    variable_name = None
    modifier = None

    def __init__(self, expression, match_object = False):
        super(VariableNode, self).__init__(expression)
        self.match_object = self.create_match_object(match_object)
        self.variable_name = self.parse_variable_name()
        self.modifier = self.parse_modifier()

    def create_match_object(self, match_object):
        if match_object is False:
            match_object = self.parse_regex.search(self.expression)
        return match_object

    @classmethod
    def consume(cls, s):
        mo = cls.parse_regex.search(s)
        if mo is not None:
            end = mo.end()
            if end > 0:
                return cls(mo.group(0), match_object = mo), s[end:]
        return None, s

    def parse_variable_name(self):
        if self.match_object is None:
            # FIXME
            raise PatternSyntaxError(self.expression)
        try:
            return self.match_object.group('name')
        except IndexError:
            # FIXME
            raise PatternSyntaxError(self.expression)

    def parse_modifier(self):
        if self.match_object is None:
            # FIXME
            raise PatternSyntaxError(self.expression)
        try:
            return self.match_object.group('modifier')
        except IndexError:
            return None

    def get_regex_segment(self, substitutions):
        return NamedGroup(self.variable_name, [SimpleExpression('.+?')])

    def fill(self, substitutions):
        value = substitutions.get(self.variable_name, None)
        if value is None:
            raise FillError(
              self.expression, substitutions, [self.variable_name])
        return self.modify(value)

    def modify(self, s):
        return self.modifiers[self.modifier](s)


class LongKeyVariableNode(VariableNode):
    parse_regex_string = r'^%(?P<modifier>[_^!])?{(?P<name>[^}]+?)}'
    parse_regex = re.compile(parse_regex_string)


class ShortKeyVariableNode(VariableNode):
    parse_regex_string = r'^%(?P<modifier>[_^!])?(?P<name>[A-Za-z])'
    parse_regex = re.compile(parse_regex_string)


class ConditionalNode(SectionNode):
    def get_regex_segment(self, substitutions):
        segment = CompoundSegment()
        segment.append(SimpleExpression('(?:'))
        for child_node in self.child_nodes:
            segment.append(child_node.get_regex_segment(substitutions))
        segment.append(SimpleExpression(')?'))
        return segment

    def get_contents(self):
        return self.expression[2:-2]

    @classmethod
    def consume(cls, s):
        if s.startswith('%?'):
            try:
                end_index = s.index('%?', 2) + 2
            except ValueError:
                pass
            else:
                return cls(s[:end_index]), s[end_index:]
        return None, s

    def fill(self, substitutions):
        try:
            return super(ConditionalNode, self).fill(substitutions)
        except FillError:
            return ''


class IfElseNode(SectionNode):
    left_side_child_nodes = None
    right_side_child_nodes = None

    def __init__(self, expression):
        self.expression = expression
        self.left_side_child_nodes = self.get_left_side_child_nodes()
        self.right_side_child_nodes = self.get_right_side_child_nodes()
        super(IfElseNode, self).__init__(expression)

    def get_regex_segment(self, substitutions):
        node_groups = (
          self.left_side_child_nodes, self.right_side_child_nodes)
        variable_node_groups = tuple(
          tuple(
            n for n in self.iter_child_nodes_recursive(node_group)
            if isinstance(n, VariableNode)
          )
          for node_group in node_groups
        )
        unknown_node_groups = tuple(
          tuple(n for n in node_group if n.variable_name not in substitutions)
          for node_group in variable_node_groups
        )
        number_of_unknowns = tuple(
          len(node_group) for node_group in unknown_node_groups)

        unknowns_left, unknowns_right = number_of_unknowns

        if unknowns_left < unknowns_right:
            regex_node_groups = (
              self.left_side_child_nodes, self.right_side_child_nodes)
        elif unknowns_left > unknowns_right:
            regex_node_groups = (
              self.right_side_child_nodes, self.left_side_child_nodes)
        else:
            number_of_variables = tuple(
              len(node_group) for node_group in variable_node_groups)
            variables_left, variables_right = number_of_variables
            if variables_left <= variables_right:
                regex_node_groups = (
                  self.left_side_child_nodes, self.right_side_child_nodes)
            elif variables_left > variables_right:
                regex_node_groups = (
                  self.right_side_child_nodes, self.left_side_child_nodes)

        regex_segments = tuple(
          CompoundSegment(
            [n.get_regex_segment(substitutions) for n in node_group])
          for node_group in regex_node_groups
        )

        segment = CompoundSegment()
        segment.append(SimpleExpression('(?:'))
        segment.append(regex_segments[0])
        segment.append(SimpleExpression('|'))
        segment.append(regex_segments[1])
        segment.append(SimpleExpression(')'))

        return segment

    def get_child_nodes(self):
        return self.right_side_child_nodes + self.left_side_child_nodes

    def get_left_side_child_nodes(self):
        return self.get_nodes_from_expression(self.get_left_side_expression())

    def get_right_side_child_nodes(self):
        return self.get_nodes_from_expression(self.get_right_side_expression())

    def get_left_side_expression(self):
        return self.expression[2:self.expression.index('%:')]

    def get_right_side_expression(self):
        return self.expression[self.expression.index('%:') + 2:-2]

    @classmethod
    def consume(cls, s):
        if s.startswith('%?'):
            try:
                end_index = s.index('%?', 2) + 2
            except ValueError:
                pass
            else:
                expression = s[:end_index]
                try:
                    middle_index = expression.index('%:') + 2
                except ValueError:
                    pass
                else:
                    return cls(s[:end_index]), s[end_index:]
        return None, s

    def fill(self, substitutions):
        try:
            return ''.join([
              child_node.fill(substitutions)
              for child_node in self.left_side_child_nodes
            ])
        except FillError, e1:
            pass

        try:
            return ''.join([
              child_node.fill(substitutions)
              for child_node in self.right_side_child_nodes
            ])
        except FillError, e2:
            pass

        raise FillError(
          self.expression, substitutions, e1.parameters + e2.parameters)


SectionNode.register_child_node_type(IfElseNode)
SectionNode.register_child_node_type(ConditionalNode)
SectionNode.register_child_node_type(TextNode)
SectionNode.register_child_node_type(LongKeyVariableNode)
SectionNode.register_child_node_type(ShortKeyVariableNode)


class SubstitutionPattern(SectionNode):
    pass
