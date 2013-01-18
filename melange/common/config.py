#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Routines for configuring Melange."""

import logging
import logging.config
import logging.handlers
import os
from paste import deploy
import sys


from melange.openstack.common import config as openstack_config


parse_options = openstack_config.parse_options
add_log_options = openstack_config.add_log_options
add_common_options = openstack_config.add_common_options
get_option = openstack_config.get_option


# We do this here to get Melange's logging configuration to some
# semblence of sanity. While it would be nice to just use
# openstack.common's log module, the version of the openstack.common
# code that Melange uses is very old, and the current versions of that
# code has changed signifigantly. Attempting to update the common code
# copied into melange breaks everything, as the utils, config and
# extensions modules have been replaced, and getting Melange to use the
# new API's  is an endless rabbit-hole of refactoring that is likely not
# worth it, given Melange's obsolecence. (mdragon)
def setup_logging(options, conf):
    """
    Sets up the logging options for a log with supplied name

    :param options: Mapping of typed option key/values
    :param conf: Mapping of untyped key/values from config file
    """

    log_config = (options.get('log_config') or
                  get_option(conf, 'log_config', default=None))
    default_log_levels = (options.get('default_log_levels') or
                          get_option(conf, 'default_log_levels',
                          default="sqlalchemy=WARN, "
                                  "keystone=INFO, "
                                  "eventlet.wsgi.server=WARN"))
    if log_config:
        # Use a logging configuration file for all settings...
        if os.path.exists(log_config):
            logging.config.fileConfig(log_config)
            return
        else:
            raise RuntimeError("Unable to locate specified logging "
                               "config file: %s" % log_config)

    # If either the CLI option or the conf value
    # is True, we set to True
    debug = (options.get('debug') or
             get_option(conf, 'debug', type='bool', default=False))
    verbose = (options.get('verbose') or
               get_option(conf, 'verbose', type='bool', default=False))

    root_logger = logging.getLogger('melange')
    if debug:
        root_logger.setLevel(logging.DEBUG)
    elif verbose:
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(logging.WARNING)

    # Set log configuration from options...
    # Note that we use a hard-coded log format in the options
    # because of Paste.Deploy bug #379
    # http://trac.pythonpaste.org/pythonpaste/ticket/379
    log_format = options.get('log_format',
                             openstack_config.DEFAULT_LOG_FORMAT)
    log_date_format = options.get('log_date_format',
                                  openstack_config.DEFAULT_LOG_DATE_FORMAT)
    formatter = logging.Formatter(log_format, log_date_format)

    logfile = options.get('log_file')
    if not logfile:
        logfile = conf.get('log_file')

    use_syslog = (options.get('use_syslog') or
                  get_option(conf, 'use_syslog', type='bool', default=False))

    if use_syslog:
        handler = logging.handlers.SysLogHandler(address='/dev/log')
    elif logfile:
        logdir = options.get('log_dir')
        if not logdir:
            logdir = conf.get('log_dir')
        if logdir:
            logfile = os.path.join(logdir, logfile)
        handler = logging.FileHandler(logfile)
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    loggers = [l.strip().split('=', 1) for l in default_log_levels.split(',')]
    for logger_name, level_name in loggers:
        level = logging.getLevelName(level_name)
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = 0
        for handler in root_logger.handlers:
            logger.addHandler(handler)
    root_logger.debug("Application Logging configured.")


class Config(object):

    instance = {}

    @classmethod
    def load_paste_app(cls, app_name, options, args, config_dir=None):
        # Loading code is here to call correct logging setup. (mdragon)
        conf_file, conf = openstack_config.load_paste_config(app_name,
                                                             options,
                                                             args,
                                                             config_dir=None)
        try:
            # Setup logging early, supplying both the CLI options and the
            # configuration mapping from the config file
            setup_logging(options, conf)

            # Log the options used when starting if we're in debug mode...
            if cls._setup_debug(options, conf):
                cls._show_debug_info(app_name, conf, conf_file)

            app = deploy.loadapp("config:%s" % conf_file, name=app_name)
        except (LookupError, ImportError) as e:
            raise RuntimeError("Unable to load %(app_name)s from "
                               "configuration file %(conf_file)s."
                               "\nGot: %(e)r" % {'app_name': app_name,
                                                 'conf_file': conf_file,
                                                 'e': e})
        cls.instance = conf
        return conf, app

    @classmethod
    def _setup_debug(cls, options, conf):
        # We only update the conf dict for the verbose and debug
        # flags. Everything else must be set up in the conf file...
        debug = (options.get('debug') or
                 get_option(conf, 'debug', type='bool', default=False))
        verbose = (options.get('verbose') or
                   get_option(conf, 'verbose', type='bool', default=False))
        conf['debug'] = debug
        conf['verbose'] = verbose
        return debug

    @classmethod
    def _show_debug_info(cls, app_name, conf, conf_file):
        logger = logging.getLogger(app_name)
        logger.debug("*" * 80)
        logger.debug("Configuration options gathered from config file:")
        logger.debug(conf_file)
        logger.debug("================================================")
        items = dict([(k, v) for k, v in conf.items()
                      if k not in ('__file__', 'here')])
        for key, value in sorted(items.items()):
            logger.debug("%(key)-30s %(value)s" % dict(key=key, value=value))
        logger.debug("*" * 80)

    @classmethod
    def load_paste_config(cls, app_name, options, args, config_dir=None):
        conf_file, conf = openstack_config.load_paste_config(app_name,
                                                             options,
                                                             args,
                                                             config_dir=None)
        cls.instance = conf
        return conf

    @classmethod
    def get(cls, key, default=None):
        return cls.instance.get(key, default)

    @classmethod
    def get_params_group(cls, group_key):
        group_key = group_key + "_"
        return dict((key.replace(group_key, "", 1), cls.instance.get(key))
                    for key in cls.instance
                    if key.startswith(group_key))


def load_app_environment(oparser):
    add_common_options(oparser)
    add_log_options(oparser)
    (options, args) = parse_options(oparser)
    conf = Config.load_paste_config('melange', options, args)
    setup_logging(options=options, conf=conf)
    return conf
