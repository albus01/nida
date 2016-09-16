"""
date : 2016.08.01
author : shawnsha@tencent.com

logging support for Nida.

Nida uses three log stream:
    1.access.
    2.application.
    3.general.
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division
import logging
import sys
from nida.util.util import Error

# Logger objects for Nida to use.
access_log = logging.getLogger("Nida.access")
app_log    = logging.getLogger("Nida.application")
gen_log    = logging.getLogger("Nida.general")

def define_logging_options(options=None):
    """
    Define log module's options to global namespcae.See options module.
    INPUT:
        @options, OptionParser : The OptionParser instance.
    OUTPUT:
        None
    """
    if options is None:
        from nida.options import options
    options.define("log_level", default="info", help="Set your logging level,"
                   "info default.", var="debug|info|warning|error|none")
    options.define("log_to_stderr", type=bool, help="Send log to stderr")
    options.define("log_rotate_mode", type=str, help="time or size to rotate"
                   "log file", default='size')
    options.define("log_file_prefix", type=str, var="PATH", help="prefix for"
                   "log file")
    options.define("log_file_max_size", type=int, help="max file size",
                   default=1000 * 1000 * 128)
    options.define("log_file_num_backups", type=int, help="number of log files"
                   "to keep", default=20)
    options.define("log_rotate_interval", type=int, help="The interval of timed"
                   "rotated", default=1)
    options.define("log_rotate_when", type=str, default="midnight", help="the"
                   "TimedRotatingFileHandler interval,for more details"
                   "see:TimedRotatingFileHandler's doc")

    options.add_parse_callback(lambda: enable_logging(options))

def enable_logging(options=None, logger=None):
    """
    Set handler,formatter to logger if logger not None, else set root logger.
    INPUT:
        @options, OptionParser : The OptionParser instance.
        @logger, logging.Logger : logging.Logger instance.
    OUTPUT:
        None
    """
    if options is None:
        import options
        options = options.options
    if options.log_level is None or options.log_level.lower() == 'none':
        return
    if logger is None:
        logger = logging.getLogger()
    logger.setLevel(getattr(logging, options.log_level.upper()))
    
    format = '[%(levelname)s %(asctime)s %(module)s:%(lineno)d %(name)s] %(message)s'
    formatter = logging.Formatter(format)
    
    if options.log_file_prefix:
        rotate_mode = options.log_rotate_mode
        if rotate_mode == 'time':
            handler = logging.handlers.TimedRotatingFileHandler(
                filename=options.log_file_prefix,
                when=options.log_rotate_when,
                interval=options.log_rotate_interval,
                backupCount=options.log_file_num_backups
            )
        elif rotate_mode == 'size':
            handler = logging.handlers.RotatingFileHandler(
                filename = options.log_file_prefix,
                maxBytes = options.log_file_max_size,
                backupCount = options.log_file_num_backups
            )
        else:
            raise Error("Unexpected log_rotate_mode: %r" %
                        options.log_rotate_mode)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    if options.log_to_stderr or (options.log_to_stderr is None and not
                                 logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)


