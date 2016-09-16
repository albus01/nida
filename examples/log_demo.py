from __future__ import absolute_import, division, print_function,with_statement

import logging
import logging.config
import env
from nida.log import app_log,access_log, gen_log, define_logging_options
from nida.options import parse_command, options


if __name__ == '__main__':
    parse_command()
    app_log.info("test")
    access_log.debug("test")
    access_log.error("test")
    gen_log.warning("test")
