#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""DOCSTRING goes here
"""


import os
import sys
import time
import configparser
import pickle
import subprocess
import logging


__author__ = "Bulak Arpat"
__copyright__ = "Copyright 2017-2018, Bulak Arpat"
__license__ = "GPLv3"
__version__ = "0.0.2"
__maintainer__ = "Bulak Arpat"
__email__ = "Bulak.Arpat@unil.ch"
__status__ = "Development"


APP_PATH = os.path.join(os.path.expanduser("~"), ".backupy")
SUCCESS, INCOMPLETE, FAILED = 0, 1, 2


class Cache(object):
    def __init__(self, cache_file, default_data=None):
        if default_data is None:
            default_data = {}
        try:
            self.cache_file = open(cache_file, 'rb+')
        except IOError:
            self.cache_file = open(cache_file, 'wb+')
        try:
            self._cache = pickle.load(self.cache_file)
        except (pickle.UnpicklingError, EOFError):
            self._cache = default_data

    def register(self):
        self.cache_file.seek(0)
        pickle.dump(self._cache, self.cache_file)
        self.cache_file.truncate()

    def update(self, *args, **kwargs):
        for arg in args:
            if isinstance(arg, dict):
                kwargs.update(arg)
            elif isinstance(arg, str):
                kwargs[arg] = True
            else:
                raise Exception("Can't accept {} as key".format(arg))
        for key, item in kwargs.items():
            self._cache[key] = item
        self.register()

    def has_var(self, var_name):
        return var_name in self._cache

    def var_list(self):
        return list(self._cache.keys())

    def get(self, var_name):
        return self._cache[var_name]

    def __repr__(self):
        return repr(self._cache)


def _get_rysnc_command(source, destination, options):
    rcommand = "rsync"
    for opt, opt_val in options.items():
        if opt_val:
            rcommand += ' {}="{}"'.format(opt, opt_val)
        else:
            rcommand += ' {}'.format(opt)
    rcommand += " {} {}".format(source, destination)
    return rcommand


class BackupyApp(object):

    def __init__(self, app_path):
        self._app_path = app_path
        self._log_file = os.path.join(app_path, "backupy.log")
        self._config_file = os.path.join(app_path, "backupy.conf")
        self._cache_file = os.path.join(app_path, ".backupy.cache")
        logging.basicConfig(
            filename=self._log_file, level=logging.DEBUG,
            format='%(levelname)s [%(asctime)s] %(message)s',
            datefmt='%m/%d/%Y %H:%M:%S')
        self.logger = logging.getLogger('backupy')
        self._config = self._set_config(default_config={})
        self.cache = Cache(self._cache_file,
                           default_data={'last_state': None,
                                         'last_source': None})
        self.logger.info('Initilizing...')
        self.logger.debug('Cache info: {}'.format(self.cache))
        if sys.version_info.minor < 5:
            self._process = self._process_3_4
        else:
            self._process = self._process_3_5

    @property
    def app_path():
        return self._app_path

    def _set_config(self, default_config):
        config = configparser.ConfigParser(allow_no_value=True)
        config.optionxform = str
        config.read_dict(default_config)
        try:
            config.read(self._config_file)
        except Exception as err:
            print(err)
        return config

    def get_config(self, section, option=None):
        conf_section = self._config[section]
        if option is None:
            return conf_section
        else:
            return conf_section.get(option)

    def _get_source_order(self):
        source_order = list(self.get_config('sources'))
        last_source = self.cache.get('last_source')
        if last_source in source_order:
            last_index = source_order.index(last_source)
            last_state = self.cache.get('last_state')
            if last_state == SUCCESS:
                pivot_index = last_index + 1
            else:
                pivot_index = last_index
        else:
            pivot_index = 0
        source_order = source_order[pivot_index:] + source_order[:pivot_index]
        return source_order

    def _process_3_4(self, r_command):
        try:
            r_process = subprocess.check_output(args=r_command, shell=True,
                                                stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.cache.update(last_state=FAILED)
            self.logger.error(
                'rsync returned non-zero exit code: {}'.format(
                    err.returncode))
            for line in err.output.splitlines():
                self.logger.error(
                    '[rsync] %s', line.decode("utf-8"))
        else:
            self.cache.update(last_state=SUCCESS)
            self.logger.info('backup successfully completed:')
            for line in r_process.splitlines():
                self.logger.info('[rsync] %s', line.decode("utf-8"))
    def _process_3_5(self, r_command):
        r_process = subprocess.run(args=r_command, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        if not r_process.returncode == 0:
            self.cache.update(last_state=FAILED)
            self.logger.error(
                'rsync returned non-zero exit code: {}'.format(
                    r_process.returncode))
            for line in r_process.stderr.splitlines():
                self.logger.error(
                    '[rsync] %s', line.decode("utf-8"))
        else:
            self.cache.update(last_state=SUCCESS)
            self.logger.info('backup successfully completed:')
            for line in r_process.stdout.splitlines():
                self.logger.info('[rsync] %s', line.decode("utf-8"))
    def backup_loop(self):
        source_order = self._get_source_order()
        sources = self.get_config('sources')
        time_limit = float(self.get_config('backup', 'time_limit'))
        finish_time = time.time() + time_limit * 3600
        for source in source_order:
            if time.time() > finish_time:
                self.logger.info('backup halted due to timelimit')
                break
            destination = os.path.join(
                self.get_config('backup', 'destination'), sources[source])
            self.logger.info(
                'Starting backup {} --> {}'.format(source, destination))
            self.cache.update(last_source=source, last_state=INCOMPLETE)
            r_command = _get_rysnc_command(source=source,
                                           destination=destination,
                                           options=self.get_config('rsync'))
            self._process(r_command)


def main():
    app = BackupyApp(app_path=APP_PATH)
    app.backup_loop()


if __name__ == '__main__':
    main()
