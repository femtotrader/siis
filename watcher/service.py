# @date 2018-08-07
# @author Frederic SCHERMA
# @license Copyright (c) 2018 Dream Overflow
# service worker

import time
import threading

from importlib import import_module

from config import utils
from common.service import Service

from notifier.signal import Signal


class WatcherService(Service):

    def __init__(self, options):
        super().__init__("watcher", options)

        self._watchers = {}

        self._identity = options.get('identity', 'demo')
        self._backtesting = options.get('backtesting', False)

        # fetchers config
        self._fetchers_config = utils.fetchers(options.get('config-path')) or {}

        # watchers config
        self._watchers_config = utils.watchers(options.get('config-path')) or {}

        # user identities
        self._identities_config = utils.identities(options.get('config-path')) or {}
        self._profile = options.get('profile', 'default')
        self._profile_config = utils.profiles(options.get('config-path')) or {}

        # backtesting options
        self._backtesting = options.get('backtesting', False)
        self._start_timestamp = options['from'].timestamp() if options.get('from') else 0
        self._end_timestamp = options['to'].timestamp() if options.get('to') else 0

        # read-only, means to do not write to the market DB
        self._read_only = options.get('read-only', False)

    def create_fetcher(self, watcher_name):
        fetcher = self._fetchers_config.get(watcher_name)
        if not fetcher:
            logger.error("Fetcher %s not found !" % watcher_name)
            return None

        # retrieve the classname and instanciate it
        parts = fetcher.get('classpath').split('.')

        module = import_module('.'.join(parts[:-1]))
        Clazz = getattr(module, parts[-1])

        return Clazz(self)

    def start(self):
        from watcher.connector.dummywatcher.watcher import DummyWatcher
        
        for k, watcher in self._watchers_config.items():
            ignore = False

            if k == "default":
                continue

            profile_watcher_config = self.profile(k)
            if not profile_watcher_config or not profile_watcher_config.get('status', None) or profile_watcher_config['status'] != 'enabled':
                # ignore watcher missing or disabled from the profile
                continue

            if self._watchers.get(k) is not None:
                logger.error("Watcher %s already started" % k)
                continue

            if watcher.get("status") is not None and watcher.get("status") == "load":
                # retrieve the classname and instanciate it
                parts = watcher.get('classpath').split('.')

                module = import_module('.'.join(parts[:-1]))
                Clazz = getattr(module, parts[-1])

                # dummy watcher in backtesting
                if self.backtesting:
                    inst_watcher = DummyWatcher(self, k)
                else:
                    inst_watcher = Clazz(self)

                if inst_watcher.start():
                    self._watchers[k] = inst_watcher

    def terminate(self):
        for k, watcher in self._watchers.items():
            # stop workers
            if watcher.running:
                watcher.stop()

        for k, watcher in self._watchers.items():
            # join them
            if watcher.thread.is_alive():
                watcher.thread.join()

        self._watchers = {}

    def notify(self, signal_type, source_name, signal_data):
        if signal_data is None:
            return

        signal = Signal(Signal.SOURCE_WATCHER, source_name, signal_type, signal_data)

        self._mutex.acquire()
        self._notifier.notify(signal)
        self._mutex.release()

    def find_author(self, watcher_name, author_id):
        watcher = self._watchers.get(watcher_name)
        if watcher:
            author = watcher.find_author(author_id)
            if author:
                return author

        return None

    def identity(self, name):
        return self._identities_config.get(name, {}).get(self._identity)

    def watcher(self, name):
        return self._watchers.get(name)

    @property
    def backtesting(self):
        return self._backtesting

    def watcher_config(self, name):
        """
        Get the configurations for a watcher as dict.
        """
        return self._watchers_config.get(name, {})

    def command(self, command_type, data):
        for k, watcher in self._watchers.items():
            watcher.command(command_type, data)

    def ping(self):
        self._mutex.acquire()
        for k, watcher, in self._watchers.items():
            watcher.ping()
        self._mutex.release()

    @property
    def read_only(self):
        return self._read_only

    def profile(self, name):
        """
        Get the profile configuration for a specific watcher name.
        """
        profile = self._profile_config.get(self._profile, {'watchers': {}}).get('watchers', {})
        return profile.get(name, {})
