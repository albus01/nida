"""
datetime: 2016.08.01
author: shawnsha@tencent.com

A command line parsing module that lets module define own options.

Every module can define its own options to the global option namespace,e.g.::
    from nida.options import define,options

    define("mymodule_host",default="127.0.0.1:8080",help="host to connect")

    def connect():
        host = mymodule_obj.connect(options.mymodule_host)
        ...
    
    your main() should parse the command line like this::
        nida.options.parse_command()

"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import sys
import os
from nida.util.util import string_compatible,Error
from nida.log import define_logging_options

class OptionParser(object):
    """A Dictionary of options.

    nida.options module has a global OptionParser instance(options) to collect every
    module's options.
    """
    def __init__(self):
        self.__dict__['_options'] = {}
        self.__dict__['_option_callback'] = []
        self.define("help", type=bool, help="show help information", 
                    callback=self._help_callback)

    def _canonical_name(self, name):
        return name.replace('_','-')
    
    def __getattr__(self, name):
        #To get a option from instance.
        name = self._canonical_name(name)
        if isinstance(self._options.get(name), _Option):
            return self._options[name].value()
        raise AttributeError("Unknown option:%s" % name)

    def __setattr__(self, name, value):
        #To set a option to the instance.
        name = self._canonical_name(name)
        if isinstance(self._options.get(name), _Option):
            return self._options[name].set(value)
        raise AttributeError("Unknown option:%s" % name)

    def __iter__(self):
        return (option.name for option in self._options.values())

    def define(self, name, var=None, default=None, type=None, help=None,
               callback=None,group=None):
        """
        Define a new option in options instance from command line.

        Any module can define its own options on the global options instance with this define
        function.

        INPUT:
            @name, str : option's unique name, required.
            @default, type.__class__ : option's default value.
            @type, int or str : option's type, need a given type like int, str etc. If not
            give, will return default.type if default is not None else return str.
            @var, type.__class__ : option's 
            @callback, func : If ``callback`` is given, the callback will be called when the option's
        value is changed.
            @help, str : ``help`` will tell user how to set the options, the help message is
        formatted like this:

            --`name`=`var` : `help` string
        OUTPUT:
            None
        """
        if name in self._options:
            raise AttributeError("Option %r has alread defined in module:%s" %
                                (name, self._options[name].file_name))
        #call directly
        frame = sys._getframe(0)
        option_file = frame.f_code.co_filename

        #if through top level define() called, should look for real caller. 
        if (frame.f_back.f_code.co_filename == option_file and
            frame.f_back.f_code.co_name == 'define'):
            frame = frame.f_back

        file_name = frame.f_back.f_code.co_filename
        if file_name == option_file:
            file_name = ""
        if type is None:
            if default is not None:
                type = default.__class__
            else:
                type = str

        if group is None:
            group = file_name
        canonical_name = self._canonical_name(name)
        option = _Option(name, var=var, file_name=file_name,
                         default=default, type=type, group_name=group, help=help,
                         callback=callback)
        self._options[canonical_name] = option

    def parse_command(self, args=None):
        """
        Parse all options from the command line.

        This method will parse options to the instance, and return the unparsed
        command.

        INPUT:
            @args : list, sys.argv default
        OUTPUT:
            None
        """
        remaining = []
        if args is None:
            args = sys.argv
        for i in range(1, len(args)):
            if not args[i].startswith('-'):
                remaining = args[i:]
                break
            if args[i] == "--":
                remaining = args[i+1:]
            arg = args[i].lstrip('-')
            name, equal, value = arg.partition('=')
            name = self._canonical_name(name)
            if name not in self._options:
                self.print_help()
                raise Error('Unkown command option: %r' % name)
            option = self._options[name]
            if not equal:
                if option.type == bool:
                    value = "true"
                else:
                    raise Error("option require a value: %r" % name)
            option.parse_value(value)

        self._run_parse_callback()

        return remaining

    def print_help(self, file=None):
        """
        Print help info when type --help in the command line.
        """
        if file is None:
            file = sys.stderr
        print("USAGE %s [OPTIONS]:\r\n" % sys.argv[0], file = file)
        group={}
        for opt in self._options.values():
            group.setdefault(opt.group_name, []).append(opt)
        for (group, opts) in group.items():
            if group:
                print("%s OPTIONS:\r\n" % os.path.normpath(group),file = file)
            opts.sort(key=lambda op:op.name)
            for opt in opts:
                info = opt.name
                if opt.var:
                    info = opt.name + ' = ' + opt.var
                description = opt.help or ''
                print("    --%-30s : %s\r\n" % (info, description), file = file)

    def _help_callback(self, value):
        """
        The help option's callback.Called when type --help to change the help
        option value.
        """
        if value:
            self.print_help()
            sys.exit(0)

    def add_parse_callback(self, callback):
        """
        Add callback to the instance's callback collection.
        """
        self._option_callback.append(callback)

    def _run_parse_callback(self):
        """
        Run all instance's callback.
        """
        for callback in self._option_callback:
            callback()

class _Option(object):
    """
    The option object for OptionParser's options collections.
    """

    def __init__(self, name, default=None, type=string_compatible, help=None,
                 var=None, file_name=None, group_name=None, callback=None):
        """
        Init a option instance.

        See OptionParser.define.
        """
        self.name       = name
        self.default    = default
        self.type       = type
        self.help       = help
        self.var        = var
        self.file_name  = file_name
        self.group_name = group_name
        self.callback   = callback
        self._value     = None

    def value(self):
        """
        return the value if parsed else default.
        """
        return self.default if self._value is None else self._value

    def parse_value(self, value):
        """
        parse input value base on option's `type`.
        Now support string and bool types parse.
        """
        _parser = {
            string_compatible : self._parse_string,
            bool : self._parse_bool,
        }.get(self.type, self.type)

        self._value = _parser(value)
        if self.callback is not None:
            self.callback(self._value)
        return self.value()

    def _parse_bool(self, value):
        return value.lower() not in ('false', '0')

    def _parse_string(self, value):
        return _unicode(value)

    def set(self, value):
        if value is not None and not isinstance(value, self.type):
            raise TypeError("Option %r require type %r" % (self.name,
                                                           self.type))
        self._value = value
        if self.callback is not None:
            self.callback(self._value)

def define(name, default=None, type=None, help=None, var=None, callback=None):
    """
    Define a option in the global options instance.

    See OptionParser.define.
    """
    return options.define(name, default=default, type=type, help=help, var=var,
                          callback=callback)

def parse_command(args=None):
    """
    Parse options from command line.

    See OptionParser.parse_command.
    """
    return options.parse_command(args)

def print_help(file=None):
    """
    Print how to use command line to the file(stderr default).

    See OptionParser.print_help.
    """
    return options.print_help(file)

def add_parse_callback(callback):
    """
    Add a parse callback to the global options instance.

    See OptionParser.add_parse_callback.
    """
    options.add_parse_callback(callback)


#Global options instance.
options = OptionParser()

define_logging_options(options)
